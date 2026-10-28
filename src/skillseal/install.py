"""Write skillseal hooks into each agent's own configuration (merging, idempotent)."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

MARK = "skillseal hook"
TIMEOUT = 60
_OURS = re.compile(r"skillseal(?:\.exe)?['\"]? hook ", re.IGNORECASE)
_EXE_NAME = re.compile(r"(?:^|[\\/])skillseal(?:\.exe)?$", re.IGNORECASE)


def _cmd(exe: str, agent: str, event: str, guard: bool, shell: str = "sh") -> str:
    """Hook command line for the shell the agent uses: sh, cmd (cmd.exe) or ps (PowerShell)."""
    args = f"hook {agent} {event}"
    if shell == "ps":
        quoted = "'" + exe.replace("'", "''") + "'"
        # $? is false when the program is missing or exits non-zero.
        return f"& {quoted} {args}" + ("; if (-not $?) { exit 2 }" if guard else "")
    if shell == "cmd":
        quoted = f'"{exe}"' if exe != "skillseal" else exe
    else:
        quoted = shlex.quote(exe) if exe != "skillseal" else exe
    # A crash or missing binary must block, not allow: map any failure to exit 2.
    return f"{quoted} {args} || exit 2" if guard else f"{quoted} {args}"


def _handler_is_ours(h: object) -> bool:
    if not isinstance(h, dict):
        return False
    text = " ".join(str(h.get(k, "")) for k in ("command", "bash", "powershell"))
    if _OURS.search(text):
        return True
    args = h.get("args")
    return isinstance(args, list) and args[:1] == ["hook"] and bool(_EXE_NAME.search(str(h.get("command", ""))))


def _entry_is_ours(entry: object) -> bool:
    if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
        return any(_handler_is_ours(h) for h in entry["hooks"])
    return _handler_is_ours(entry)


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
    groups = [g for g in hooks.get(event, []) if not _entry_is_ours(g)]
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


def _claude_group(exe: str, event: str, guard: bool, matcher: str | None, windows: bool) -> dict:
    if windows:
        # Claude Code runs shell-form hooks in Git Bash or PowerShell on Windows; exec form needs no shell.
        handler: dict = {"type": "command", "command": exe, "args": ["hook", "claude", event], "timeout": TIMEOUT}
    else:
        handler = {"type": "command", "command": _cmd(exe, "claude", event, guard), "timeout": TIMEOUT}
    if guard:
        handler["onFailure"] = "block"  # also block on crash or timeout (Claude Code 2.1.295+)
    group: dict = {"hooks": [handler]}
    return {"matcher": matcher, **group} if matcher is not None else group


def install_claude(base: Path, exe: str, windows: bool = False) -> list[Path]:
    path = base / ".claude" / "settings.json"
    data = _load_json(path)
    _merge_groups(data, "SessionStart", _claude_group(exe, "SessionStart", False, None, windows))
    for event in ("UserPromptSubmit", "UserPromptExpansion"):
        _merge_groups(data, event, _claude_group(exe, event, True, None, windows))
    _merge_groups(data, "PreToolUse", _claude_group(exe, "PreToolUse", True, "*", windows))
    _write_json(path, data)
    return [path]


def install_codex(base: Path, exe: str, windows: bool = False) -> list[Path]:
    path = base / ".codex" / "hooks.json"
    shell = "cmd" if windows else "sh"  # Codex runs hooks with %COMSPEC% /C on Windows
    data = _load_json(path)
    _merge_groups(data, "SessionStart", _group(_cmd(exe, "codex", "SessionStart", False, shell), None, TIMEOUT))
    _merge_groups(data, "PreToolUse", _group(_cmd(exe, "codex", "PreToolUse", True, shell), "*", TIMEOUT))
    _write_json(path, data)
    return [path]


def install_gemini(base: Path, exe: str, windows: bool = False) -> list[Path]:
    path = base / ".gemini" / "settings.json"
    shell = "ps" if windows else "sh"  # Gemini CLI runs hooks with PowerShell on Windows
    data = _load_json(path)
    ms = TIMEOUT * 1000
    _merge_groups(data, "SessionStart", _group(_cmd(exe, "gemini", "SessionStart", False, shell), None, ms, "skillseal-session"))
    _merge_groups(data, "BeforeTool", _group(_cmd(exe, "gemini", "BeforeTool", True, shell), "*", ms, "skillseal"))
    _write_json(path, data)
    return [path]


def install_copilot(base: Path, exe: str, user: bool) -> list[Path]:
    path = (base / ".copilot" / "hooks" if user else base / ".github" / "hooks") / "skillseal.json"
    ours = {
        "sessionStart": {"type": "command", "bash": _cmd(exe, "copilot", "sessionStart", False),
                         "powershell": _cmd(exe, "copilot", "sessionStart", False, "ps"), "timeoutSec": TIMEOUT},
        "preToolUse": {"type": "command", "bash": _cmd(exe, "copilot", "preToolUse", True),
                       "powershell": _cmd(exe, "copilot", "preToolUse", True, "ps"), "timeoutSec": TIMEOUT},
    }
    data = _load_json(path)
    data["version"] = 1
    hooks = data.setdefault("hooks", {})
    for event, handler in ours.items():
        kept = [h for h in hooks.get(event, []) if not _handler_is_ours(h)]
        hooks[event] = kept + [handler]
    _write_json(path, data)
    return [path]


OPENCODE_PLUGIN = """\
// skillseal guard for OpenCode: blocks every tool call (including the `skill` tool)
// while a skill OpenCode can load is unsigned, changed or signed by an untrusted signer.
// Written by `skillseal install opencode`. Errors also block (fail closed).
import { execFile } from "node:child_process";

const SKILLSEAL = process.env.SKILLSEAL_BIN ?? __EXE__;

function verify(cwd) {
  return new Promise((resolve) => {
    let child;
    try {
      child = execFile(
        SKILLSEAL,
        ["hook", "opencode", "tool.execute.before"],
        { timeout: 60_000 },
        (err, _stdout, stderr) => {
          if (!err) return resolve(undefined);
          resolve(String(stderr).trim() || `skillseal could not verify skills: ${err.message}`);
        },
      );
    } catch (err) {
      return resolve(`skillseal could not run: ${err}`);
    }
    child.on("error", (err) => resolve(`skillseal could not run: ${err.message}`));
    child.stdin?.end(JSON.stringify({ cwd }));
  });
}

export const SkillsealGuard = async ({ directory, worktree }) => {
  const cwd = directory || worktree || process.cwd();
  return {
    "tool.execute.before": async (_input, _output) => {
      const reason = await verify(cwd);
      if (reason) throw new Error(reason);
    },
  };
};
"""


def install_opencode(base: Path, exe: str, user: bool) -> list[Path]:
    path = (base / ".config" / "opencode" / "plugins" if user else base / ".opencode" / "plugins") / "skillseal.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OPENCODE_PLUGIN.replace("__EXE__", json.dumps(exe)), encoding="utf-8")
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


def _strip_ours(data: dict) -> bool:
    changed = False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _entry_is_ours(e)]
        if len(kept) != len(entries):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if not hooks:
        del data["hooks"]
    return changed


def uninstall(agent: str, scope: str, project: Path) -> list[Path]:
    """Remove only skillseal's own entries; other hooks and settings stay."""
    home = Path(os.path.expanduser("~"))
    base = home if scope == "user" else project
    json_files = {
        "claude": [base / ".claude" / "settings.json"],
        "codex": [base / ".codex" / "hooks.json"],
        "gemini": [base / ".gemini" / "settings.json"],
        "copilot": [(base / ".copilot" / "hooks" if scope == "user" else base / ".github" / "hooks") / "skillseal.json"],
    }.get(agent, [])
    plugin_files = {
        "opencode": [(base / ".config" / "opencode" / "plugins" if scope == "user" else base / ".opencode" / "plugins") / "skillseal.js"],
        "openclaw": [home / ".openclaw" / "policies" / "skillseal-guard.ts"],
    }.get(agent, [])
    touched: list[Path] = []
    for path in json_files:
        if not path.is_file():
            continue
        data = _load_json(path)
        if _strip_ours(data):
            if agent == "copilot" and set(data) <= {"version"}:
                path.unlink()
            else:
                _write_json(path, data)
            touched.append(path)
    for path in plugin_files:
        if path.is_file() and MARK.split()[0] in path.read_text(encoding="utf-8"):
            path.unlink()
            touched.append(path)
    return touched


def install(agent: str, scope: str, project: Path, exe: str = "skillseal",
            windows: bool | None = None) -> tuple[list[Path], str]:
    if windows is None:
        windows = os.name == "nt"
    home = Path(os.path.expanduser("~"))
    base = home if scope == "user" else project
    if agent == "claude":
        return install_claude(base, exe, windows), ""
    if agent == "codex":
        note = "Codex asks you to review new hooks once: run /hooks in Codex and trust the skillseal hooks."
        return install_codex(base, exe, windows), note
    if agent == "gemini":
        note = "Gemini CLI shows a warning for new project hooks; accept it once."
        return install_gemini(base, exe, windows), note if scope == "project" else ""
    if agent == "copilot":
        return install_copilot(base, exe, user=scope == "user"), ""
    if agent == "opencode":
        return install_opencode(base, exe, user=scope == "user"), "Restart OpenCode to load the plugin."
    if agent == "openclaw":
        return install_openclaw(home, exe)
    raise ValueError(f"unknown agent {agent!r}")
