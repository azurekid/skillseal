"""Write skillseal hooks into each agent's own configuration (merging, idempotent)."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

MARK = "skillseal hook"
TIMEOUT = 60


def _cmd(exe: str, agent: str, event: str, guard: bool) -> str:
    base = f"{shlex.quote(exe) if exe != 'skillseal' else exe} hook {agent} {event}"
    # A crash or missing binary must block, not allow: map any failure to exit 2.
    return f"{base} || exit 2" if guard else base


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_groups(data: dict, event: str, group: dict) -> None:
    hooks = data.setdefault("hooks", {})
    groups = [g for g in hooks.get(event, []) if not any(MARK in str(h.get("command", "")) for h in g.get("hooks", []))]
    groups.append(group)
    hooks[event] = groups


def _group(command: str, matcher: str | None, timeout: int, name: str | None = None) -> dict:
    handler: dict = {"type": "command", "command": command, "timeout": timeout}
    if name:
        handler = {"name": name, **handler}
    group: dict = {"hooks": [handler]}
    if matcher is not None:
        group = {"matcher": matcher, **group}
    return group


def install_claude(base: Path, exe: str) -> list[Path]:
    path = base / ".claude" / "settings.json"
    data = _load_json(path)
    _merge_groups(data, "SessionStart", _group(_cmd(exe, "claude", "SessionStart", False), None, TIMEOUT))
    for event in ("UserPromptSubmit", "UserPromptExpansion"):
        _merge_groups(data, event, _group(_cmd(exe, "claude", event, True), None, TIMEOUT))
    _merge_groups(data, "PreToolUse", _group(_cmd(exe, "claude", "PreToolUse", True), "*", TIMEOUT))
    _write_json(path, data)
    return [path]


def install_codex(base: Path, exe: str) -> list[Path]:
    path = base / ".codex" / "hooks.json"
    data = _load_json(path)
    _merge_groups(data, "SessionStart", _group(_cmd(exe, "codex", "SessionStart", False), None, TIMEOUT))
    _merge_groups(data, "PreToolUse", _group(_cmd(exe, "codex", "PreToolUse", True), "*", TIMEOUT))
    _write_json(path, data)
    return [path]


def install_gemini(base: Path, exe: str) -> list[Path]:
    path = base / ".gemini" / "settings.json"
    data = _load_json(path)
    ms = TIMEOUT * 1000
    _merge_groups(data, "SessionStart", _group(_cmd(exe, "gemini", "SessionStart", False), None, ms, "skillseal-session"))
    _merge_groups(data, "BeforeTool", _group(_cmd(exe, "gemini", "BeforeTool", True), "*", ms, "skillseal"))
    _write_json(path, data)
    return [path]


def install_copilot(base: Path, exe: str, user: bool) -> list[Path]:
    path = (base / ".copilot" / "hooks" if user else base / ".github" / "hooks") / "skillseal.json"
    ps = lambda event: f"& {_cmd(exe, 'copilot', event, False)}; if (-not $?) {{ exit 2 }}"  # noqa: E731
    ours = {
        "sessionStart": {"type": "command", "bash": _cmd(exe, "copilot", "sessionStart", False),
                         "powershell": "& " + _cmd(exe, "copilot", "sessionStart", False), "timeoutSec": TIMEOUT},
        "preToolUse": {"type": "command", "bash": _cmd(exe, "copilot", "preToolUse", True),
                       "powershell": ps("preToolUse"), "timeoutSec": TIMEOUT},
    }
    data = _load_json(path)
    data["version"] = 1
    hooks = data.setdefault("hooks", {})
    for event, handler in ours.items():
        kept = [h for h in hooks.get(event, []) if MARK not in str(h.get("bash", "")) + str(h.get("command", ""))]
        hooks[event] = kept + [handler]
    _write_json(path, data)
    return [path]


OPENCLAW_PLUGIN = """\
// skillseal guard for OpenClaw. OpenClaw plugin APIs are experimental: pin your host version.
import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const SKILLSEAL = process.env.SKILLSEAL_BIN ?? __EXE__;
const WORKSPACE = process.env.SKILLSEAL_OPENCLAW_WORKSPACE ?? `${homedir()}/.openclaw/workspace`;

function verify(signal?: AbortSignal): Promise<string | undefined> {
  return new Promise((resolve) => {
    const child = execFile(
      SKILLSEAL,
      ["hook", "openclaw", "before_tool_call"],
      { timeout: 12_000, signal },
      (err, _stdout, stderr) => {
        if (!err) return resolve(undefined);
        resolve(String(stderr).trim() || `skillseal could not verify skills: ${err.message}`);
      },
    );
    child.stdin?.end(JSON.stringify({ cwd: WORKSPACE }));
  });
}

export default definePluginEntry({
  id: "skillseal-guard",
  name: "skillseal guard",
  description: "Blocks tool calls while an unsigned or changed skill can be loaded.",
  register(api) {
    api.on("before_tool_call", async (_event, ctx) => {
      const reason = await verify(ctx.abortSignal);
      return reason ? { block: true, blockReason: reason } : undefined;
    });
  },
});
"""

OPENCLAW_CONFIG_HINT = """\
Add this to ~/.openclaw/openclaw.json, then run: openclaw plugins reload skillseal-guard
  plugins: {
    load: { paths: ["%s"] },
    entries: { "skillseal-guard": { enabled: true } },
  },"""


def install_openclaw(home: Path, exe: str) -> tuple[list[Path], str]:
    path = home / ".openclaw" / "policies" / "skillseal-guard.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OPENCLAW_PLUGIN.replace("__EXE__", json.dumps(exe)), encoding="utf-8")
    return [path], OPENCLAW_CONFIG_HINT % path


def install(agent: str, scope: str, project: Path, exe: str = "skillseal") -> tuple[list[Path], str]:
    home = Path(os.path.expanduser("~"))
    base = home if scope == "user" else project
    if agent == "claude":
        return install_claude(base, exe), ""
    if agent == "codex":
        note = "Codex asks you to review new hooks once: run /hooks in Codex and trust the skillseal hooks."
        return install_codex(base, exe), note
    if agent == "gemini":
        note = "Gemini CLI shows a warning for new project hooks; accept it once."
        return install_gemini(base, exe), note if scope == "project" else ""
    if agent == "copilot":
        return install_copilot(base, exe, user=scope == "user"), ""
    if agent == "openclaw":
        return install_openclaw(home, exe)
    raise ValueError(f"unknown agent {agent!r}")
