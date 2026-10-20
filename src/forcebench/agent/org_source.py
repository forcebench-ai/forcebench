"""The org's metadata in the agent's workspace: a coding agent in its team's SFDX project.

A grader org profile (orgs/<profile>/) holds the metadata its org is set up from: sfdx-project.json
and force-app/. With ``--org-source <profile>``, each task's workspace starts as that project, with
the task's own files on top, and the agent's note says the org's metadata is there. It is how an
engineer usually has an org's metadata, and it gives the agent no way into the org itself: the
fair counterpart of an MCP server that reads the same org (docs/mcp-study.md).

A run records the profile and the hash of its files, and is never resumed with another one, or none.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forcebench import REPO_ROOT


ORGS_DIR = REPO_ROOT / "orgs"
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
# Replaces the agent note's "no network, no org" sentence (harness.agent_note).
NOTE = (
    "There is no network access and no Salesforce org; the metadata of the org this task is "
    "about, as retrieved from it, is in your working directory (an SFDX project: "
    "sfdx-project.json and force-app/)."
)


@dataclass(frozen=True)
class OrgSource:
    """A grader org profile's metadata, given to the agent as its working directory."""

    profile: str
    root: Path

    @property
    def note(self) -> str:
        return NOTE

    def files(self) -> dict[str, str]:
        """The project's files by their path in the workspace."""
        paths = [self.root / "sfdx-project.json", *sorted((self.root / "force-app").rglob("*"))]
        out: dict[str, str] = {}
        for p in paths:
            if p.is_symlink():
                raise ValueError(f"symlink in the org's metadata: {p.relative_to(self.root)}")
            if p.is_file():
                out[p.relative_to(self.root).as_posix()] = p.read_text(encoding="utf-8")
        return out

    def sha256(self) -> str:
        h = hashlib.sha256()
        for path, content in sorted(self.files().items()):
            h.update(f"{path}\0{hashlib.sha256(content.encode()).hexdigest()}\n".encode())
        return h.hexdigest()

    def describe(self) -> dict[str, Any]:
        """What a run records about it (a resume must match it)."""
        return {"profile": self.profile, "sha256": self.sha256()}


def load_org_source(profile: str, orgs: Path = ORGS_DIR) -> OrgSource:
    """The profile orgs/<profile>/ (an SFDX project), or a ValueError naming the known ones."""
    root = orgs / profile
    if not _NAME.fullmatch(profile) or not (root / "force-app").is_dir():
        known = sorted(p.name for p in orgs.iterdir() if (p / "force-app").is_dir())
        raise ValueError(f"no org profile {profile!r} (known: {', '.join(known) or 'none'})")
    if not (root / "sfdx-project.json").is_file():
        raise ValueError(f"orgs/{profile} has no sfdx-project.json")
    return OrgSource(profile, root)
