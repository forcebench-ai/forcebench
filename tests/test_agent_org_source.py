"""The org's metadata in an agent's workspace (forcebench.agent.org_source)."""

import hashlib

import pytest

from forcebench.agent.harness import (
    AGENT_NOTE,
    NO_NETWORK,
    Opencode,
    agent_note,
    assemble_answer,
    label,
    write_workspace,
)
from forcebench.agent.mcp import load_server
from forcebench.agent.org_source import load_org_source


PERMSET = "force-app/main/default/permissionsets/ForceBench_Base_Data.permissionset-meta.xml"


def test_the_base_profile_is_an_sfdx_project():
    org = load_org_source("base")
    files = org.files()
    assert "sfdx-project.json" in files
    assert PERMSET in files
    assert all(p == "sfdx-project.json" or p.startswith("force-app/") for p in files)
    d = org.describe()
    assert d["profile"] == "base"
    assert len(d["sha256"]) == 64
    with pytest.raises(ValueError, match=r"known: .*base"):
        load_org_source("../base")


def test_the_note_says_where_the_metadata_is():
    note = agent_note(org=load_org_source("base"))
    assert NO_NETWORK not in note
    assert "sfdx-project.json and force-app/" in note
    assert agent_note() == AGENT_NOTE


def test_a_run_with_the_org_s_metadata_records_and_shows_it():
    org = load_org_source("base")
    d = Opencode(org_source=org).describe("sha256:abc")
    assert d["org_source"] == org.describe()
    assert label(d) == "opencode 2.0.21 + org metadata"
    assert d["note_sha"] == hashlib.sha256(agent_note(org=org).encode()).hexdigest()[:12]
    assert "org_source" not in Opencode().describe("sha256:abc")


def test_the_workspace_is_the_project_with_the_task_s_files_on_top(make_task, tmp_path):
    org = load_org_source("base")
    task = make_task(
        {"format": "files", "files": [PERMSET]}, context_files={"force-app/x.txt": "the task's"}
    )
    work = write_workspace(task, tmp_path, {**org.files(), "force-app/x.txt": "the org's"})
    assert (work / PERMSET).read_text() == org.files()[PERMSET]
    assert (work / "sfdx-project.json").is_file()
    assert (work / "force-app/x.txt").read_text() == "the task's"


def test_an_untouched_org_file_is_not_the_answer_and_an_edited_one_is(make_task, tmp_path):
    org = load_org_source("base")
    task = make_task({"format": "files", "files": [PERMSET]})
    work = write_workspace(task, tmp_path, org.files())
    assert assemble_answer(task, "Done.", work, org.files()) == ("Done.", [])
    (work / PERMSET).write_text((work / PERMSET).read_text().replace("Base Data", "Base Access"))
    text, added = assemble_answer(task, "Done.", work, org.files())
    assert added == [PERMSET]
    assert "Base Access" in text


def test_the_part_two_clientell_manifest_says_the_org_is_the_task_s():
    s = load_server("clientell-org")
    assert s.name == "clientell", "the same server, so the same tool names"
    assert "the org this task is about" in s.note
    assert s.describe()["id"] == "clientell-org"
    assert "id" not in load_server("clientell").describe(), "part 1 runs keep their record"
    assert s.tools == load_server("clientell").tools
    assert s.codemode, "through Code Mode, as part 1's arm"
    assert load_server("clientell-codemode").codemode


def test_part_two_s_clientell_arm_adds_its_live_reads_held_to_salesforce():
    live, index = load_server("clientell-org-live"), load_server("clientell-org")
    assert (live.name, live.note, live.codemode) == (index.name, index.note, True)
    assert set(live.tools) - set(index.tools) == {"use_connector", "list_connector_capabilities"}
    assert live.fixed_args == {"use_connector": {"provider": "salesforce"}}
    assert live.describe()["fixed_args"] == live.fixed_args
    assert "fixed_args" not in index.describe(), "the index-only runs keep their record"


def test_an_mcp_session_waits_for_the_server_s_tools():
    run = Opencode(mcp=load_server("clientell")).command()
    assert "done; sleep 5; exec opencode run" in run
