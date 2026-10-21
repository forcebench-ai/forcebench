"""The MCP study: the same model on the same tasks, in opencode without and with an MCP server.

Two parts (docs/mcp-study.md). **Everyday** work, the lite subset: opencode alone against opencode
with an MCP server's tools through its Code Mode (forcebench.agent.mcp), and, as a check, the same
tools as tools of their own (the study's first setting). **Org context**, the study tasks
(status: study), whose answers depend on what is already in the org: opencode alone, opencode
with the org's metadata in its workspace (forcebench.agent.org_source), and opencode with an MCP
server connected to an org with the same metadata. A model's arms answer side by side through the
same proxy and the same route to the model, so what differs is what the agent has, and the one
sentence of the note that tells it.

Per arm: the pass rate (a task's score is the mean over its answers; the rate is the mean over
tasks), with a 95% bootstrap interval over tasks, stratified by suite; output and input tokens,
model requests and time per session; sessions that ended without an answer. Per model, for each
pair of arms (with the server against without; in part 2 also the metadata against without, and
the server against the metadata): the difference, paired by task over the tasks both arms
answered, with a 95% bootstrap interval over those tasks; the same per suite, without an interval.
Across the models: the mean of their differences, tasks resampled jointly.

For the arm with the server: sessions that called one of its tools, calls per session and by
tool, calls the server failed, time spent waiting for it, and the pass rate of sessions that
called a tool against those that did not. That last split is an observation, not an effect: a
model reaches for a tool on the tasks it finds hard.

Sessions come from the runs' raw summaries (raw/agent/<task>#<sample>/summary.json), which stay
on the machine that made them; only these aggregates are published (studies/mcp.json).
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any

from forcebench import BENCHMARK_VERSION
from forcebench.agent.harness_study import _quantile, wilson
from forcebench.stats import mean, paired_difference_ci, stratified_bootstrap_ci


def _median(xs: list[float]) -> float | None:
    m = _quantile(xs, 0.5)
    return None if m is None else round(m, 1)


# The study's parts, by the subset their runs answer.
PARTS = (("everyday", "lite"), ("org-context", "study"))
# Pairs of arms compared within a model (a minus b), where the model has both: the server against
# nothing, the org's metadata against nothing, and the server against the metadata.
PAIRS = (
    ("mcp", "none"), ("org", "none"), ("mcp", "org"),
    ("mcp-tools", "none"), ("mcp", "mcp-tools"),
    ("mcp-index", "none"), ("mcp", "mcp-index"),
)  # fmt: skip
# Part 2's first Clientell manifest: the server's metadata index, without its live reads.
INDEX_ONLY = "clientell-org"


def arm_of(meta: dict[str, Any]) -> str:
    """A run's arm: ``mcp``, ``mcp-tools``, ``mcp-index``, ``org`` or ``none``.

    ``mcp`` has an MCP server through opencode's Code Mode, its default; ``mcp-tools`` the same
    server's tools as tools of their own, the study's first setting, kept as a check;
    ``mcp-index`` part 2's first runs, with Clientell's metadata index but not its live reads of
    the org, also kept as a check; ``org`` the org's metadata in its workspace; ``none`` neither.
    """
    h = meta.get("agent") or {}
    if h.get("mcp"):
        if not h["mcp"].get("codemode"):
            return "mcp-tools"
        return "mcp-index" if h["mcp"].get("id") == INDEX_ONLY else "mcp"
    return "org" if h.get("org_source") else "none"


def collect(
    runs_dirs: Path | list[Path], since: str = "", subset: str = "lite"
) -> dict[tuple[str, str], dict[str, Any]]:
    """Every graded session of one part's runs, grouped by arm (configuration, arm).

    A part's runs are opencode runs of its subset, without skills, through a proxy (``via``),
    started at or after ``since`` (a run id prefix). Runs of one arm add up.
    """
    dirs = runs_dirs if isinstance(runs_dirs, list) else [runs_dirs]
    arms: dict[tuple[str, str], dict[str, Any]] = {}
    for meta_path in sorted(p for d in dirs for p in d.glob("*/run.json")):
        run = meta_path.parent
        meta = json.loads(meta_path.read_text())
        h = meta.get("agent") or {}
        if h.get("name") != "opencode" or h.get("skills") or meta.get("subset") != subset:
            continue
        if not meta.get("via") or meta["run_id"] < since or not (run / "cases.jsonl").exists():
            continue
        cases = [json.loads(x) for x in (run / "cases.jsonl").read_text().splitlines()]
        cases = [c for c in cases if c.get("passed") is not None and not c.get("infra_error")]
        if not cases:
            continue
        key = (meta["config_id"], arm_of(meta))
        arm = arms.setdefault(key, {"meta": meta, "runs": [], "sessions": []})
        arm["runs"].append(meta["run_id"])
        for c in cases:
            path = run / "raw" / "agent" / f"{c['task_id']}#{c['sample']}" / "summary.json"
            summary = json.loads(path.read_text()) if path.exists() else {}
            arm["sessions"].append({"case": c, "summary": summary})
    return arms


def _scores(sessions: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, str]]:
    """Each task's score (the mean over its answers), and its suite."""
    passed: dict[str, list[bool]] = {}
    suites: dict[str, str] = {}
    for s in sessions:
        c = s["case"]
        passed.setdefault(c["task_id"], []).append(bool(c["passed"]))
        suites[c["task_id"]] = c["suite"]
    return {t: mean([float(x) for x in xs]) for t, xs in passed.items()}, suites


def _rate(scores: dict[str, float], suites: dict[str, str]) -> dict[str, Any]:
    by_suite: dict[str, list[float]] = {}
    for t, x in scores.items():
        by_suite.setdefault(suites[t], []).append(x)
    lo, hi = stratified_bootstrap_ci(by_suite)
    return {
        "tasks": len(scores),
        "pass_rate": round(mean(list(scores.values())), 3),
        "ci_low": round(lo, 3),
        "ci_high": round(hi, 3),
    }


def _mcp_use(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """How the arm's sessions used the server, from their summaries."""
    with_mcp = [s for s in sessions if s["summary"].get("mcp")]
    used, unused = [], []
    for s in with_mcp:
        (used if sum(s["summary"]["mcp"]["calls"].values()) else unused).append(s)
    by_tool: dict[str, int] = {}
    for s in with_mcp:
        for tool, n in s["summary"]["mcp"]["calls"].items():
            by_tool[tool] = by_tool.get(tool, 0) + n
    calls = [float(sum(s["summary"]["mcp"]["calls"].values())) for s in with_mcp]
    waits = [float(s["summary"]["mcp"].get("latency_s") or 0) for s in used]
    servers = sorted(
        {
            f"{(s['summary']['mcp'].get('server') or {}).get('name')} "
            f"{(s['summary']['mcp'].get('server') or {}).get('version')}"
            for s in with_mcp
            if s["summary"]["mcp"].get("server")
        }
    )

    def passed(xs: list[dict[str, Any]]) -> dict[str, Any]:
        k = sum(bool(s["case"]["passed"]) for s in xs)
        lo, hi = wilson(k, len(xs))
        return {"sessions": len(xs), "passed": k, "ci_low": round(lo, 3), "ci_high": round(hi, 3)}

    return {
        "sessions": len(with_mcp),
        "sessions_with_calls": len(used),
        "calls_mean": round(mean(calls), 2) if calls else None,
        "calls_by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1])),
        "calls_failed": sum(int(s["summary"]["mcp"].get("failed") or 0) for s in with_mcp),
        "calls_refused": sum(int(s["summary"]["mcp"].get("refused") or 0) for s in with_mcp),
        "wait_s_median": _median(waits),
        "servers": servers,
        "with_calls": passed(used),
        "without_calls": passed(unused),
    }


def _arm_stats(key: tuple[str, str], arm: dict[str, Any]) -> dict[str, Any]:
    meta, sessions = arm["meta"], arm["sessions"]
    scores, suites = _scores(sessions)
    summaries = [s["summary"] for s in sessions if s["summary"]]
    out_tokens = [float(s["case"].get("output_tokens") or 0) for s in sessions]
    in_tokens = [float(s["case"].get("input_tokens") or 0) for s in sessions]
    latency = [float(s["case"].get("latency_s") or 0) for s in sessions]
    requests = [float((x.get("usage") or {}).get("requests") or 0) for x in summaries]
    mcp = (meta.get("agent") or {}).get("mcp")
    org = (meta.get("agent") or {}).get("org_source")
    return {
        "config_id": key[0],
        "arm": key[1],
        "model": (meta.get("model") or {}).get("display"),
        "effort": meta.get("effort"),
        "harness": f"{meta['agent']['name']} {meta['agent']['version']}",
        "mcp": {"label": mcp["label"], "tools": mcp["tools"]} if mcp else None,
        "org_source": org["profile"] if org else None,
        "via": meta.get("via"),
        "runs": arm["runs"],
        "sessions": len(sessions),
        **_rate(scores, suites),
        "output_tokens_mean": round(mean(out_tokens), 1) if out_tokens else None,
        "input_tokens_median": _median(in_tokens),
        "requests_median": _median(requests),
        "latency_s_median": _median(latency),
        "no_answer": sum(s["case"].get("finish_reason") != "stop" for s in sessions),
        "summaries": len(summaries),
        **({"mcp_use": _mcp_use(sessions)} if mcp else {}),
    }


def _difference(a: dict[str, float], b: dict[str, float], suites: dict[str, str]) -> dict[str, Any]:
    """Arm a minus arm b, paired by task, overall and per suite."""
    shared = sorted(set(a) & set(b))
    d, lo, hi = paired_difference_ci({t: a[t] for t in shared}, {t: b[t] for t in shared})
    per_suite: dict[str, list[float]] = {}
    for t in shared:
        per_suite.setdefault(suites[t], []).append(a[t] - b[t])
    return {
        "tasks": len(shared),
        "d": round(d, 3),
        "ci_low": round(lo, 3),
        "ci_high": round(hi, 3),
        "by_suite": {s: round(mean(xs), 3) for s, xs in sorted(per_suite.items())},
        "tasks_better": sum(a[t] > b[t] for t in shared),
        "tasks_worse": sum(a[t] < b[t] for t in shared),
    }


def part(runs_dirs: Path | list[Path], name: str, subset: str, since: str = "") -> dict[str, Any]:
    """One part's arms and comparisons."""
    arms = collect(runs_dirs, since, subset)
    scores = {k: _scores(a["sessions"]) for k, a in arms.items()}
    comparisons, pooled = [], []
    for a, b in PAIRS:
        configs = sorted({c for c, _ in arms if (c, a) in arms and (c, b) in arms})
        by_model: list[tuple[dict[str, float], dict[str, float]]] = []
        suites: dict[str, str] = {}
        for config in configs:
            (sa, ua), (sb, ub) = scores[(config, a)], scores[(config, b)]
            suites |= ua | ub
            comparisons.append({"config_id": config, "a": a, "b": b,
                                **_difference(sa, sb, ua | ub)})  # fmt: skip
            by_model.append((sa, sb))
        # Across the models: tasks every model answered in both arms, each the mean over them.
        shared = (
            set.intersection(*(set(sa) & set(sb) for sa, sb in by_model)) if by_model else set()
        )
        if len(by_model) > 1 and shared:
            pooled.append({
                "a": a, "b": b, "models": len(by_model),
                **_difference(
                    {t: mean([sa[t] for sa, _ in by_model]) for t in shared},
                    {t: mean([sb[t] for _, sb in by_model]) for t in shared},
                    suites,
                ),
            })  # fmt: skip
    return {
        "id": name,
        "subset": subset,
        "arms": [_arm_stats(k, a) for k, a in sorted(arms.items())],
        "comparisons": comparisons,
        "all_models": pooled,
    }


def study(runs_dirs: Path | list[Path], since: str = "") -> dict[str, Any]:
    """The study's published aggregates."""
    return {
        "study": "mcp",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "method": {
            "task_score": "the mean over a task's answers",
            "pass_interval": "95% bootstrap over tasks, stratified by suite (10,000 resamples)",
            "comparison": (
                "arm a minus arm b, paired by task, 95% bootstrap over the shared tasks "
                "(10,000 resamples)"
            ),
            "split_interval": "Wilson 95%",
        },
        "parts": [part(runs_dirs, name, subset, since) for name, subset in PARTS],
    }
