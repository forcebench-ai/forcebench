"""MCP servers for agent runs: a remote server whose tools the agent may use.

A server is a manifest, docker/agent/mcp/<name>.json: its name (opencode shows its tools to the
model as ``<name>_<tool>``), the label runs are shown with, its URL, the .env variable that holds
its token, the tools the agent gets (and any argument a tool is held to), and the sentence that
tells the agent about them. The agent reaches the server only through the model proxy, which adds
the token (the agent's container never has it), shows the agent only those tools and refuses any
other call, and logs every exchange
(forcebench.agent.proxy). A run records the server and its tools, never the token, and is never
resumed with another server, or none.

A hosted server is someone else's and cannot be pinned the way a skill pack is, so each session
records what the server said it was (its name and version) and every tool it offered.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forcebench import REPO_ROOT


SERVERS_DIR = REPO_ROOT / "docker" / "agent" / "mcp"
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
_ENV = re.compile(r"FORCEBENCH_[A-Z0-9_]+")


@dataclass(frozen=True)
class McpServer:
    """A remote MCP server and the tools of it a run gives the agent."""

    name: str
    label: str
    url: str
    token_env: str
    tools: tuple[str, ...]
    # Replaces the agent note's "no network, no org" sentence (harness.agent_note).
    note: str
    # The manifest's file name, when it is not the server's name: two manifests may give one
    # server with different notes (docs/mcp-study.md, part 2).
    id: str = ""
    # The tools through opencode's Code Mode (its default: the model writes JavaScript that calls
    # them through one `execute` tool) instead of as tools of their own.
    codemode: bool = False
    # Arguments a tool may only be called with, by tool: the proxy refuses a call with any other
    # value (e.g. a connector tool held to one read-only provider).
    fixed_args: dict[str, dict[str, str]] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        """What a run records about its server (a resume must match it)."""
        return {
            "name": self.name, "label": self.label, "url": self.url, "tools": list(self.tools),
            **({"id": self.id} if self.id and self.id != self.name else {}),
            **({"codemode": True} if self.codemode else {}),
            **({"fixed_args": self.fixed_args} if self.fixed_args else {}),
        }  # fmt: skip

    def token(self) -> str:
        """The server's token, from the environment (.env); a RuntimeError names its variable."""
        token = os.environ.get(self.token_env) or ""
        if not token:
            raise RuntimeError(f"no token for {self.label}: set {self.token_env} in .env")
        return token


def load_server(name: str, servers: Path = SERVERS_DIR) -> McpServer:
    """The server docker/agent/mcp/<name>.json describes, or a ValueError naming the known ones."""
    path = servers / f"{name}.json"
    if not _NAME.fullmatch(name) or not path.is_file():
        known = sorted(p.stem for p in servers.glob("*.json"))
        raise ValueError(f"no MCP server {name!r} (known: {', '.join(known) or 'none'})")
    d = json.loads(path.read_text())
    tools = tuple(d["tools"])
    if not str(d["url"]).startswith("https://"):
        raise ValueError(f"{path.name}: the server's url must be https")
    if not _ENV.fullmatch(d["token_env"]):
        raise ValueError(f"{path.name}: token_env must be a FORCEBENCH_ variable")
    if not tools or any(not _NAME.fullmatch(t) for t in tools) or len(set(tools)) < len(tools):
        raise ValueError(f"{path.name}: tools must be distinct tool names")
    if not _NAME.fullmatch(d["name"]):
        raise ValueError(f"{path.name}: name must be a tool prefix (lowercase, digits, - and _)")
    codemode = d.get("codemode", False)
    if codemode is not True and codemode is not False:
        raise ValueError(f"{path.name}: codemode must be true or false")
    fixed = d.get("fixed_args", {})
    if not isinstance(fixed, dict) or any(
        t not in tools
        or not isinstance(a, dict)
        or not a
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in a.items())
        for t, a in fixed.items()
    ):
        raise ValueError(f"{path.name}: fixed_args maps the run's tools to string arguments")
    return McpServer(
        d["name"], d["label"], d["url"], d["token_env"], tools, d["note"], name, codemode, fixed
    )  # fmt: skip


def tools_in_request(request: dict[str, Any], server: McpServer) -> int:
    """How many of the server's tools a model request gives the model.

    As tools of their own, they are the request's tools named ``<server>_<tool>``. Through Code
    Mode, they are listed in the system prompt's catalog as ``tools.<server>.<tool>(``.
    """
    if not server.codemode:
        prefix = f"{server.name}_"
        return sum(
            1
            for t in request.get("tools") or []
            if str((t.get("function") or {}).get("name") or "").startswith(prefix)
        )
    text = ""
    for m in request.get("messages") or []:
        content = m.get("content")
        parts = content if isinstance(content, list) else [{"text": content}]
        text += "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    return sum(f"tools.{server.name}.{t}(" in text for t in server.tools)


def mcp_usage(log: Path) -> dict[str, Any]:
    """Totals of the proxy's MCP log for one session.

    ``listed`` is whether the server gave its tools; ``calls`` counts tool calls by tool;
    ``failed`` counts calls the server failed or answered with an error.
    """
    out: dict[str, Any] = {
        "listed": False, "server": None, "offered": None, "calls": {}, "failed": 0,
        "refused": 0, "latency_s": 0.0, "result_chars": 0,
    }  # fmt: skip
    if not log.exists():
        return out
    for line in log.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("server_info") and out["server"] is None:
            out["server"] = r["server_info"]
        if r.get("offered") is not None:
            out["listed"] = True
            out["offered"] = r["offered"]
        if r.get("refused"):
            out["refused"] += 1
        elif r.get("tool"):
            out["calls"][r["tool"]] = out["calls"].get(r["tool"], 0) + 1
            out["latency_s"] = round(out["latency_s"] + float(r.get("latency_s") or 0), 3)
            out["result_chars"] += int(r.get("result_chars") or 0)
            if r.get("is_error") or r.get("rpc_error") or int(r.get("status") or 0) >= 400:
                out["failed"] += 1
    return out
