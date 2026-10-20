"""MCP servers for agent runs (forcebench.agent.mcp) and how a harness gives one to the agent.

The server is reached only through the model proxy (tests/test_agent_proxy.py has the relay).
"""

import hashlib
import json

import pytest

from forcebench.agent.harness import AGENT_NOTE, NO_NETWORK, Opencode, agent_note, label
from forcebench.agent.mcp import load_server, mcp_usage
from forcebench.models import load_registry


def test_the_clientell_manifest_loads_and_names_its_token_variable():
    s = load_server("clientell")
    assert (s.name, s.label, s.url) == (
        "clientell",
        "Clientell MCP",
        "https://mcp.clientell.ai/mcp",
    )
    assert s.token_env == "FORCEBENCH_CLIENTELL_TOKEN"
    assert "search_salesforce_metadata" in s.tools
    # Tools that change the Clientell account or propose writes are never offered to an
    # unattended agent.
    never = {
        "clientell_upgrade", "clientell_delete_my_data", "use_connector", "sf_confirm_write",
        "sf_propose_update", "clientell_connect_salesforce", "clientell_set_active_org",
    }  # fmt: skip
    assert not never & set(s.tools)


def test_a_bad_manifest_is_refused(tmp_path):
    good = {"name": "x", "label": "X", "url": "https://x.test/mcp", "token_env": "FORCEBENCH_X",
            "tools": ["a"], "note": "n"}  # fmt: skip
    for bad in ({"url": "http://x.test/mcp"}, {"token_env": "HOME"}, {"tools": ["a", "a"]},
                {"tools": []}):  # fmt: skip
        (tmp_path / "x.json").write_text(json.dumps(good | bad))
        with pytest.raises(ValueError, match=r"x\.json"):
            load_server("x", tmp_path)
    with pytest.raises(ValueError, match="known: x"):
        load_server("../x", tmp_path)


def test_a_missing_token_names_its_variable(monkeypatch):
    monkeypatch.delenv("FORCEBENCH_CLIENTELL_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="FORCEBENCH_CLIENTELL_TOKEN"):
        load_server("clientell").token()


def test_the_note_says_what_the_server_reaches_and_nothing_else_changes():
    s = load_server("clientell")
    note = agent_note(s)
    assert NO_NETWORK in AGENT_NOTE
    assert NO_NETWORK not in note
    assert note == AGENT_NOTE.replace(NO_NETWORK, s.note)
    # Runs without a server keep the note, and its hash, they always had.
    assert hashlib.sha256(agent_note().encode()).hexdigest()[:12] == "dd7d4b565f51"


def test_opencode_reaches_the_server_only_through_the_proxy():
    m = load_registry().get("qwen3.8-27b-awq-int4")
    s = load_server("clientell")
    cfg = json.loads(Opencode(mcp=s).files(m)["/cfg/opencode.json"])
    server = cfg["mcp"]["servers"]["clientell"]
    assert server["url"] == "http://fbproxy:8080/mcp"
    assert "headers" not in server, "the token stays in the proxy"
    assert server["oauth"] is False
    assert server["codemode"] is False, "its tools are tools of their own, not Code Mode's"
    assert server["timeout"]["execution"] == 180_000
    assert "mcp" not in json.loads(Opencode().files(m)["/cfg/opencode.json"])


def test_a_session_with_a_server_starts_once_opencode_has_connected_it():
    run = Opencode(mcp=load_server("clientell")).command()
    assert "GET /api/mcp" in run
    assert '"status":"connected"' in run
    assert run.endswith('--server http://127.0.0.1:4096 --auto --format json -m bench/model '
                        '--title task "$(cat)"')  # fmt: skip
    # Runs without a server start as they always have.
    assert Opencode().command() == (
        'exec opencode run --standalone --auto --format json -m bench/model --title task "$(cat)"'
    )


def test_a_run_with_a_server_records_it_and_shows_it(monkeypatch):
    monkeypatch.setenv("FORCEBENCH_CLIENTELL_TOKEN", "tok-secret-123")
    s = load_server("clientell")
    d = Opencode(mcp=s).describe("sha256:abc")
    assert d["mcp"] == s.describe()
    m = load_registry().get("qwen3.8-27b-awq-int4")
    assert "tok-secret-123" not in json.dumps(d) + json.dumps(Opencode(mcp=s).files(m))
    assert d["note_sha"] != Opencode().describe("sha256:abc")["note_sha"]
    assert label(d) == "opencode 2.0.21 + Clientell MCP"
    assert "mcp" not in Opencode().describe("sha256:abc")


def test_mcp_usage_totals_the_proxy_s_mcp_log(tmp_path):
    log = tmp_path / "mcp.jsonl"
    records = [
        {"http": "POST", "methods": ["initialize"], "status": 200,
         "server_info": {"name": "clientell", "version": "2"}},
        {"http": "POST", "methods": ["tools/list"], "status": 200, "offered": ["a", "b", "c"]},
        {"http": "POST", "tool": "a", "status": 200, "is_error": False, "latency_s": 1.5,
         "result_chars": 100},
        {"http": "POST", "tool": "a", "status": 200, "is_error": True, "latency_s": 0.5},
        {"http": "POST", "tool": "b", "status": 502, "error": "TimeoutError"},
        {"http": "POST", "tool": "c", "refused": "c"},
    ]  # fmt: skip
    log.write_text("\n".join(json.dumps(r) for r in records))
    u = mcp_usage(log)
    assert u["listed"]
    assert u["offered"] == ["a", "b", "c"]
    assert u["server"] == {"name": "clientell", "version": "2"}
    assert u["calls"] == {"a": 2, "b": 1}
    assert (u["failed"], u["refused"], u["latency_s"], u["result_chars"]) == (2, 1, 2.0, 100)
    assert not mcp_usage(tmp_path / "missing.jsonl")["listed"]
