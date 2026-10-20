"""The MCP study: the same model on the same tasks, in opencode without and with an MCP server.

Two arms per model: opencode alone, and opencode with an MCP server's tools
(forcebench.agent.mcp). Both answer the lite subset side by side through the same proxy and the
same route to the model, so what differs is the server's tools and the one sentence of the note
that tells the agent about them.

Per arm: the pass rate (a task's score is the mean over its answers; the rate is the mean over
tasks), with a 95% bootstrap interval over tasks, stratified by suite; output and input tokens,
model requests and time per session; sessions that ended without an answer. Per model: the
difference with the server minus without, paired by task over the tasks both arms answered, with
a 95% bootstrap interval over those tasks; the same per suite, without an interval (four tasks
each). Across the models: the mean of their differences, tasks resampled jointly.

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


def _arm_key(meta: dict[str, Any]) -> tuple[str, str]:
    return meta["config_id"], ((meta.get("agent") or {}).get("mcp") or {}).get("name", "")


def collect(runs_dir: Path, since: str = "") -> dict[tuple[str, str], dict[str, Any]]:
    """Every graded session of the study's runs, grouped by arm (configuration, MCP server or "").

    The study's runs are opencode runs of the lite subset, without skills, through a proxy
    (``via``), started at or after ``since`` (a run id prefix). Runs of one arm add up.
    """
    arms: dict[tuple[str, str], dict[str, Any]] = {}
    for meta_path in sorted(runs_dir.glob("*/run.json")):
        run = meta_path.parent
        meta = json.loads(meta_path.read_text())
        h = meta.get("agent") or {}
        if h.get("name") != "opencode" or h.get("skills") or meta.get("subset") != "lite":
            continue
        if not meta.get("via") or meta["run_id"] < since or not (run / "cases.jsonl").exists():
            continue
        cases = [json.loads(x) for x in (run / "cases.jsonl").read_text().splitlines()]
        cases = [c for c in cases if c.get("passed") is not None and not c.get("infra_error")]
        if not cases:
            continue
        arm = arms.setdefault(_arm_key(meta), {"meta": meta, "runs": [], "sessions": []})
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
        "wait_s_median": _quantile(waits, 0.5),
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
    return {
        "config_id": key[0],
        "model": (meta.get("model") or {}).get("display"),
        "effort": meta.get("effort"),
        "harness": f"{meta['agent']['name']} {meta['agent']['version']}",
        "mcp": {"label": mcp["label"], "tools": mcp["tools"]} if mcp else None,
        "via": meta.get("via"),
        "runs": arm["runs"],
        "sessions": len(sessions),
        **_rate(scores, suites),
        "output_tokens_mean": round(mean(out_tokens), 1) if out_tokens else None,
        "input_tokens_median": _quantile(in_tokens, 0.5),
        "requests_median": _quantile(requests, 0.5),
        "latency_s_median": _quantile(latency, 0.5),
        "no_answer": sum(s["case"].get("finish_reason") != "stop" for s in sessions),
        "summaries": len(summaries),
        **({"mcp_use": _mcp_use(sessions)} if mcp else {}),
    }


def _difference(
    with_: dict[str, float], without: dict[str, float], suites: dict[str, str]
) -> dict[str, Any]:
    """With the server minus without, paired by task, overall and per suite."""
    shared = sorted(set(with_) & set(without))
    d, lo, hi = paired_difference_ci({t: with_[t] for t in shared}, {t: without[t] for t in shared})
    per_suite: dict[str, list[float]] = {}
    for t in shared:
        per_suite.setdefault(suites[t], []).append(with_[t] - without[t])
    return {
        "tasks": len(shared),
        "d": round(d, 3),
        "ci_low": round(lo, 3),
        "ci_high": round(hi, 3),
        "by_suite": {s: round(mean(xs), 3) for s, xs in sorted(per_suite.items())},
        "tasks_better": sum(with_[t] > without[t] for t in shared),
        "tasks_worse": sum(with_[t] < without[t] for t in shared),
    }


def study(runs_dir: Path, since: str = "") -> dict[str, Any]:
    """The study's published aggregates."""
    arms = collect(runs_dir, since)
    stats = [_arm_stats(k, a) for k, a in sorted(arms.items())]
    comparisons = []
    pooled_with: dict[str, list[float]] = {}
    pooled_without: dict[str, list[float]] = {}
    all_suites: dict[str, str] = {}
    for config in sorted({k[0] for k in arms}):
        servers = sorted(k[1] for k in arms if k[0] == config and k[1])
        if (config, "") not in arms or not servers:
            continue
        without, suites = _scores(arms[(config, "")]["sessions"])
        for server in servers:
            with_, more = _scores(arms[(config, server)]["sessions"])
            suites |= more
            all_suites |= suites
            comparisons.append({"config_id": config, "mcp": server,
                                **_difference(with_, without, suites)})  # fmt: skip
            for t in set(with_) & set(without):
                pooled_with.setdefault(t, []).append(with_[t])
                pooled_without.setdefault(t, []).append(without[t])
    models = len(comparisons)
    # Tasks every compared model answered in both arms, each the mean over the models.
    full = {t for t, xs in pooled_with.items() if len(xs) == models}
    pooled = (
        _difference(
            {t: mean(pooled_with[t]) for t in full},
            {t: mean(pooled_without[t]) for t in full},
            all_suites,
        )
        if models > 1 and full
        else None
    )
    return {
        "study": "mcp",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "subset": "lite",
        "method": {
            "task_score": "the mean over a task's answers",
            "pass_interval": "95% bootstrap over tasks, stratified by suite (10,000 resamples)",
            "comparison": (
                "with the server minus without, paired by task, 95% bootstrap over the shared "
                "tasks (10,000 resamples)"
            ),
            "split_interval": "Wilson 95%",
        },
        "arms": stats,
        "comparisons": comparisons,
        "all_models": pooled,
    }
