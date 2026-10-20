"""The MCP study's aggregates (forcebench.agent.mcp_study), from made-up runs."""

import json
from pathlib import Path

import pytest

from forcebench.agent.mcp_study import arm_of, collect, part, study


CLIENTELL = {"name": "clientell", "label": "Clientell MCP", "url": "https://x", "tools": ["a"]}
ORG = {"profile": "base", "sha256": "0" * 64}


def _run(
    runs: Path,
    run_id: str,
    passed: dict[str, list[bool]],
    mcp: dict | None = None,
    org: dict | None = None,
    **meta,
) -> None:
    """A graded agent run: per task, one case per answer; with a server, each session's summary."""
    d = runs / run_id
    d.mkdir(parents=True)
    agent = {"name": "opencode", "version": "2.0.21", **({"mcp": mcp} if mcp else {}),
             **({"org_source": org} if org else {})}  # fmt: skip
    (d / "run.json").write_text(json.dumps({
        "run_id": run_id, "config_id": "m@high", "subset": "lite", "via": "local",
        "model": {"display": "M"}, "effort": "high", "agent": agent, **meta,
    }))  # fmt: skip
    cases = []
    for task, results in passed.items():
        for i, ok in enumerate(results):
            cases.append({"task_id": task, "suite": task.split("-")[0], "sample": i, "passed": ok,
                          "finish_reason": "stop", "output_tokens": 100, "input_tokens": 1000,
                          "latency_s": 10.0})  # fmt: skip
            if mcp:
                k = d / "raw" / "agent" / f"{task}#{i}"
                k.mkdir(parents=True)
                calls = {"a": 2} if task.endswith("1") else {}
                k.joinpath("summary.json").write_text(json.dumps({
                    "usage": {"requests": 3},
                    "mcp": {"listed": True, "calls": calls, "failed": 0, "refused": 0,
                            "latency_s": 4.0 if calls else 0.0,
                            "server": {"name": "clientell", "version": "1"}},
                }))  # fmt: skip
    (d / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases))


def _everyday(out: dict) -> dict:
    return next(p for p in out["parts"] if p["id"] == "everyday")


def test_the_difference_is_paired_by_task_and_runs_of_an_arm_add_up(tmp_path):
    without = {"apex-1": [False], "apex-2": [True], "soql-1": [False]}
    _run(tmp_path, "20261020T100000Z_m@high", without)
    with_ = {"apex-1": [True], "apex-2": [True], "soql-1": [True]}
    _run(tmp_path, "20261020T100005Z_m@high", with_, mcp=CLIENTELL)
    # A second run of the arm with the server: two more answers to apex-1.
    _run(tmp_path, "20261020T200000Z_m@high", {"apex-1": [True, False]}, mcp=CLIENTELL)
    p = _everyday(study(tmp_path))
    [c] = p["comparisons"]
    assert (c["a"], c["b"]) == ("mcp", "none")
    # apex-1 with the server: 2 of 3 answers; apex-2 the same; soql-1 1 - 0.
    assert c["tasks"] == 3
    assert c["d"] == pytest.approx((2 / 3 + 0 + 1) / 3, abs=1e-3)
    assert (c["tasks_better"], c["tasks_worse"]) == (2, 0)
    assert c["by_suite"] == {"apex": pytest.approx(1 / 3, abs=1e-3), "soql": 1.0}
    with_mcp = next(a for a in p["arms"] if a["arm"] == "mcp")
    assert with_mcp["sessions"] == 5
    assert len(with_mcp["runs"]) == 2
    use = with_mcp["mcp_use"]
    # Sessions of tasks ending in 1 call the tool twice; apex-2's session does not.
    assert (use["sessions"], use["sessions_with_calls"], use["calls_by_tool"]) == (5, 4, {"a": 8})
    assert use["with_calls"]["passed"] == 3
    assert use["without_calls"] == {**use["without_calls"], "sessions": 1, "passed": 1}
    assert use["servers"] == ["clientell 1"]
    assert p["all_models"] == [], "one model: nothing to pool"


def test_part_two_compares_three_arms_on_the_study_tasks(tmp_path):
    tasks = {"org-1": [False, False], "org-2": [False, True]}
    _run(tmp_path, "20261021T100000Z_m@high", tasks, subset="study")
    _run(tmp_path, "20261021T100005Z_m@high", {"org-1": [True, True], "org-2": [True, True]},
         org=ORG, subset="study")  # fmt: skip
    _run(tmp_path, "20261021T100010Z_m@high", {"org-1": [True, False], "org-2": [True, True]},
         mcp=CLIENTELL, subset="study")  # fmt: skip
    p = part(tmp_path, "org-context", "study")
    assert [a["arm"] for a in p["arms"]] == ["mcp", "none", "org"]
    d = {(c["a"], c["b"]): c["d"] for c in p["comparisons"]}
    assert d == {
        ("mcp", "none"): pytest.approx((0.5 + 0.5) / 2),
        ("org", "none"): pytest.approx((1 + 0.5) / 2),
        ("mcp", "org"): pytest.approx((-0.5 + 0) / 2),
    }
    assert next(a for a in p["arms"] if a["arm"] == "org")["org_source"] == "base"
    assert _everyday(study(tmp_path))["arms"] == [], "study runs are not part 1's"


def test_only_the_study_s_runs_count(tmp_path):
    _run(tmp_path, "20261020T100000Z_m@high", {"apex-1": [True]})
    _run(tmp_path, "20261001T100000Z_m@high", {"apex-1": [False]}, mcp=CLIENTELL)  # before --since
    _run(tmp_path, "20261020T110000Z_m@high", {"apex-1": [False]}, mcp=CLIENTELL, subset="full")
    _run(tmp_path, "20261020T120000Z_m@high", {"apex-1": [False]}, mcp=CLIENTELL, via=None)
    assert set(collect(tmp_path, since="20261020")) == {("m@high", "none")}
    assert _everyday(study(tmp_path, since="20261020"))["comparisons"] == []


def test_an_arm_is_read_from_the_run_s_agent_record():
    assert arm_of({"agent": {"name": "opencode", "mcp": CLIENTELL}}) == "mcp"
    assert arm_of({"agent": {"name": "opencode", "org_source": ORG}}) == "org"
    assert arm_of({"agent": {"name": "opencode"}}) == "none"


def test_runs_in_several_directories_add_up(tmp_path):
    a, b = tmp_path / "main", tmp_path / "worktree"
    _run(a, "20261020T100000Z_m@high", {"apex-1": [False]})
    _run(b, "20261020T100005Z_m@high", {"apex-1": [True]}, mcp=CLIENTELL)
    [c] = _everyday(study([a, b]))["comparisons"]
    assert c["d"] == 1.0
