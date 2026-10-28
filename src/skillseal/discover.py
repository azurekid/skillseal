"""Where each agent loads skills from (verified against vendor docs, 2026-10).

Project roots are searched in the working directory and every parent up to
the repository root. Every folder that contains SKILL.md is a skill; skillseal
does not descend into a skill once found, so nested files belong to it.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import SKILL_FILE

AGENTS = ("claude", "copilot", "codex", "gemini", "opencode", "openclaw")

PROJECT_DIRS: dict[str, tuple[str, ...]] = {
    "claude": (".claude/skills",),
    "copilot": (".github/skills", ".claude/skills", ".agents/skills"),
    "codex": (".agents/skills",),
    "gemini": (".gemini/skills", ".agents/skills"),
    "opencode": (".opencode/skills", ".claude/skills", ".agents/skills"),
    "openclaw": ("skills", ".agents/skills"),
}

USER_DIRS: dict[str, tuple[str, ...]] = {
    "claude": ("~/.claude/skills", "~/.claude/plugins"),
    "copilot": ("~/.copilot/skills", "~/.claude/skills", "~/.agents/skills"),
    "codex": ("~/.agents/skills", "/etc/codex/skills"),
    "gemini": ("~/.gemini/skills", "~/.agents/skills", "~/.gemini/extensions"),
    "opencode": ("~/.config/opencode/skills", "~/.claude/skills", "~/.agents/skills"),
    "openclaw": ("~/.agents/skills", "~/.openclaw/skills"),
}

MAX_DEPTH = 8
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def project_chain(cwd: Path) -> list[Path]:
    """cwd and its parents up to (and including) the git repository root."""
    cwd = cwd.resolve()
    chain = []
    for p in (cwd, *cwd.parents):
        chain.append(p)
        if (p / ".git").exists():
            return chain
    return [cwd]


def roots_for(agents: list[str], cwd: Path, extra: list[str] | None = None) -> list[Path]:
    seen: dict[str, Path] = {}
    home_chain = project_chain(cwd)
    for agent in agents:
        for base in home_chain:
            for rel in PROJECT_DIRS[agent]:
                p = base / rel
                seen.setdefault(str(p), p)
        for raw in USER_DIRS[agent]:
            p = Path(os.path.expanduser(raw))
            seen.setdefault(str(p), p)
    for raw in extra or []:
        p = Path(os.path.expanduser(raw))
        if not p.is_absolute():
            p = cwd / p
        seen.setdefault(str(p), p)
    return [p for p in seen.values() if p.is_dir()]


def find_skills(root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(d: Path, depth: int) -> None:
        if (d / SKILL_FILE).is_file():
            found.append(d)
            return
        if depth >= MAX_DEPTH:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for e in entries:
            if e.name in SKIP_DIRS:
                continue
            try:
                # Skill installers (for example `npx skills`) symlink skill folders into agent dirs.
                if e.is_dir(follow_symlinks=True):
                    walk(Path(e.path), depth + 1)
            except OSError:
                continue

    walk(root, 0)
    return found


def discover(agents: list[str], cwd: Path, extra: list[str] | None = None) -> list[Path]:
    skills: dict[str, Path] = {}
    for root in roots_for(agents, cwd, extra):
        for s in find_skills(root):
            try:
                key = str(s.resolve())
            except OSError:
                key = str(s)
            skills.setdefault(key, s)
    return list(skills.values())
