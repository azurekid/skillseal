"""Small heuristic checks for common risky skill instructions and commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class ScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    severity: str
    description: str


_RULES = (
    ("HIGH", "instruction override", re.compile(
        r"\bignore\s+(?:all|any|the)\s+(?:previous|prior|above|earlier)\s+instructions\b", re.I
    )),
    ("HIGH", "system prompt disclosure", re.compile(
        r"\b(?:reveal|print|display|show|output|expose)\s+(?:the\s+)?(?:system|developer)\s+prompt\b", re.I
    )),
    ("HIGH", "secret exfiltration", re.compile(
        r"\b(?:send|upload|exfiltrate|transmit)\b.{0,100}\b(?:passwords?|secrets?|credentials?|api keys?|tokens?|environment variables?)\b",
        re.I,
    )),
    ("MEDIUM", "download piped to shell", re.compile(
        r"\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.I
    )),
    ("MEDIUM", "PowerShell download piped to execution", re.compile(
        r"\b(?:Invoke-WebRequest|iwr)\b[^\n]*\|\s*(?:Invoke-Expression|iex)\b", re.I
    )),
    ("MEDIUM", "recursive deletion from filesystem root", re.compile(
        r"\brm\s+-rf\s+/(?:\s|[*?]|$)", re.I
    )),
    ("MEDIUM", "world-writable recursive permissions", re.compile(
        r"\bchmod\s+-R\s+777\b", re.I
    )),
)

_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def scan_skill(skill_dir: Path) -> list[Finding]:
    if not skill_dir.is_dir():
        raise ScanError(f"not a directory: {skill_dir}")
    if not (skill_dir / "SKILL.md").is_file():
        raise ScanError(f"{skill_dir} has no SKILL.md")

    findings: list[Finding] = []
    files = sorted(
        path for path in skill_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
        and "skill.oms.sig" != path.name
        and ".git" not in path.relative_to(skill_dir).parts
    )
    for path in files:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ScanError(f"cannot read {path}: {exc}") from exc
        if b"\0" in content[:8192]:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScanError(f"cannot scan non-UTF-8 text file {path}") from exc
        for line_number, line in enumerate(text.splitlines(), start=1):
            for severity, description, pattern in _RULES:
                if pattern.search(line):
                    findings.append(Finding(path, line_number, severity, description))
    return findings


def scan_exceeds_threshold(findings: list[Finding], fail_on: str) -> bool:
    threshold = _SEVERITY_RANK[fail_on]
    return any(_SEVERITY_RANK[finding.severity] >= threshold for finding in findings)
