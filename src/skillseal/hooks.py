"""Runtime enforcement through each agent's hook system.

Rule enforced everywhere: while any skill the agent can load is unsigned,
tampered or signed by an untrusted signer, no tool call may run (and in
Claude Code no prompt or slash command expands either). This holds even for
agents that inject skills without a tool call (Copilot, Codex, OpenClaw).

Every hook command is wrapped so that a crash or a missing skillseal binary
also blocks (exit 2) instead of silently allowing the action.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .cache import cache_path
from .discover import discover
from .policy import Policy, load_policy
from .verify import Result, verify_skill

BLOCKING_EVENTS = {
    "claude": {"PreToolUse", "UserPromptSubmit", "UserPromptExpansion"},
    "codex": {"PreToolUse"},
    "copilot": {"preToolUse", "PreToolUse"},
    "gemini": {"BeforeTool"},
    "openclaw": {"before_tool_call"},
}


def check(agent: str, cwd: Path, policy: Policy) -> list[Result]:
    skills = discover([agent], cwd, policy.skill_roots)
    return [r for r in (verify_skill(s, policy) for s in skills) if not r.ok]


def explain(failures: list[Result], limit: int = 8) -> str:
    n = len(failures)
    lines = [f"skillseal: {n} skill{'s' if n != 1 else ''} not approved (unsigned, changed or untrusted signer):"]
    for r in failures[:limit]:
        why = r.reasons[0] if r.reasons else r.status
        lines.append(f"  - {r.path}: {r.status}: {why}")
    if n > limit:
        lines.append(f"  ... and {n - limit} more")
    lines.append("Remove the skill or get it approved and signed. Details: skillseal check")
    return "\n".join(lines)


def _audit(entry: dict) -> None:
    try:
        path = cache_path().parent / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _block(agent: str, event: str, message: str) -> int:
    if agent == "gemini":
        print(json.dumps({"decision": "deny", "reason": message}))
        return 0
    if agent == "copilot":
        print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": message}))
    if agent == "claude" and event == "UserPromptExpansion":
        print(json.dumps({"decision": "block", "reason": message}))
    print(message, file=sys.stderr)
    return 2


def run_hook(agent: str, event: str, stdin_text: str) -> int:
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    event = event or str(data.get("hook_event_name") or "")
    cwd = Path(str(data.get("cwd") or os.environ.get("SKILLSEAL_CWD") or os.getcwd()))
    blocking = event in BLOCKING_EVENTS.get(agent, set())

    try:
        policy = load_policy(project=cwd)
        failures = check(agent, cwd, policy)
    except Exception as exc:  # noqa: BLE001 - fail closed
        msg = f"skillseal: cannot verify skills ({type(exc).__name__}: {exc}); blocking until fixed"
        _audit({"at": int(time.time()), "agent": agent, "event": event, "cwd": str(cwd), "error": msg})
        return _block(agent, event, msg) if blocking else 0

    _audit({
        "at": int(time.time()), "agent": agent, "event": event, "cwd": str(cwd), "mode": policy.mode,
        "failures": [r.to_dict() for r in failures],
    })
    if not failures:
        return 0
    message = explain(failures)
    if not blocking:
        if agent == "claude" and event == "SessionStart":
            print(message + "\n(Tool calls are blocked by skillseal until this is fixed.)" if policy.mode == "enforce" else message)
        else:
            print(message, file=sys.stderr)
        return 0
    if policy.mode == "enforce":
        return _block(agent, event, message)
    if policy.mode == "warn":
        print(message, file=sys.stderr)
    return 0
