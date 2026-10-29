"""Opt-in AgentLens file scanning. No repository content is uploaded by default."""

from __future__ import annotations

import json
import uuid
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import SIGNATURE_FILE, SKILL_FILE
from .scan import Finding, ScanError
from .verify import _walk


def scan_agentlens(skill_dir: Path, url: str) -> list[Finding]:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ScanError("AgentLens URL must be an HTTPS base URL without credentials, query or fragment")
    if not (skill_dir / SKILL_FILE).is_file():
        raise ScanError(f"{skill_dir} has no {SKILL_FILE}")

    paths, problems = _walk(skill_dir)
    if problems:
        raise ScanError("; ".join(problems))
    paths = sorted(path for path in paths if Path(path).name != SIGNATURE_FILE
                   and ".git" not in Path(path).parts)
    if not paths or len(paths) > 500:
        raise ScanError("AgentLens requires between 1 and 500 files per skill")

    boundary = "skillseal-" + uuid.uuid4().hex
    parts = []
    for name, value in (("discover", "true"), ("include_workflows", "false")):
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    submitted: dict[str, Path] = {}
    total = 0
    for relative in paths:
        path = skill_dir / relative
        name = f"{skill_dir.resolve().name}/{relative}"
        if any(char in name for char in ('"', "\r", "\n", "\\")):
            raise ScanError(f"unsupported AgentLens upload filename: {relative!r}")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ScanError(f"cannot read {path}: {exc}") from exc
        total += len(content)
        if len(content) > 256 * 1024 or total > 5 * 1024 * 1024:
            raise ScanError("AgentLens accepts at most 256 KiB per file and 5 MiB per skill")
        submitted[name] = path
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    request = Request(
        url.rstrip("/") + "/api/scan/files", data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            report = json.load(response)
    except (URLError, OSError, ValueError, HTTPException) as exc:
        raise ScanError(f"AgentLens scan failed: {exc}") from exc
    if not isinstance(report, dict) or report.get("status") != "complete" or report.get("skipped") != []:
        raise ScanError("AgentLens did not return a complete scan with no skipped files")
    files = report.get("files")
    if not isinstance(files, list):
        raise ScanError("AgentLens response has no file results")
    seen: set[str] = set()
    findings: list[Finding] = []
    for file in files:
        if not isinstance(file, dict):
            raise ScanError("AgentLens returned an invalid file result")
        name = file.get("path")
        hits = file.get("findings")
        if not isinstance(name, str) or name not in submitted or name in seen or not isinstance(hits, list):
            raise ScanError("AgentLens returned unexpected, duplicate or invalid file results")
        seen.add(name)
        for hit in hits:
            if not isinstance(hit, dict):
                raise ScanError("AgentLens returned an invalid finding")
            severity, line, rule, message = (hit.get(key) for key in ("severity", "line", "rule", "message"))
            if (severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
                    or type(line) is not int or line < 1
                    or not isinstance(rule, str) or not rule
                    or not isinstance(message, str) or not message):
                raise ScanError("AgentLens returned an invalid finding")
            findings.append(Finding(submitted[name], line, severity, f"{rule}: {message}"))
    if seen != submitted.keys():
        raise ScanError("AgentLens did not inspect every submitted file")
    return findings
