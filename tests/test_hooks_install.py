import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_skill, write_policy
from skillseal.hooks import run_hook
from skillseal.install import install
from skillseal.sign import sign_skill


@pytest.fixture
def project(tmp_path, keys, isolated_env):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1])
    return proj


def stdin(cwd, **extra):
    return json.dumps({"cwd": str(cwd), **extra})


def test_no_skills_allows(project, capsys):
    assert run_hook("claude", "PreToolUse", stdin(project)) == 0


def test_signed_skill_allows(project, keys):
    skill = make_skill(project / ".claude" / "skills")
    sign_skill(skill, method="key", private_key=keys[0])
    assert run_hook("claude", "PreToolUse", stdin(project)) == 0


@pytest.mark.parametrize(
    "agent,event,skills_dir",
    [
        ("claude", "PreToolUse", ".claude/skills"),
        ("claude", "UserPromptSubmit", ".claude/skills"),
        ("codex", "PreToolUse", ".agents/skills"),
        ("copilot", "preToolUse", ".github/skills"),
        ("openclaw", "before_tool_call", "skills"),
    ],
)
def test_unsigned_skill_blocks_exit_2(project, agent, event, skills_dir, capsys):
    make_skill(project / skills_dir)
    assert run_hook(agent, event, stdin(project)) == 2
    assert "not approved" in capsys.readouterr().err


def test_copilot_prints_deny_json(project, capsys):
    make_skill(project / ".github" / "skills")
    assert run_hook("copilot", "preToolUse", stdin(project)) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["permissionDecision"] == "deny"


def test_gemini_denies_with_json_exit_0(project, capsys):
    make_skill(project / ".gemini" / "skills")
    assert run_hook("gemini", "BeforeTool", stdin(project)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "deny"


def test_claude_expansion_block_json(project, capsys):
    make_skill(project / ".claude" / "skills")
    assert run_hook("claude", "UserPromptExpansion", stdin(project)) == 2
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_tampered_skill_blocks(project, keys):
    skill = make_skill(project / ".claude" / "skills")
    sign_skill(skill, method="key", private_key=keys[0])
    (skill / "SKILL.md").write_text("tampered\n")
    assert run_hook("claude", "PreToolUse", stdin(project)) == 2


def test_session_start_never_blocks_but_tells_claude(project, capsys):
    make_skill(project / ".claude" / "skills")
    assert run_hook("claude", "SessionStart", stdin(project)) == 0
    assert "blocked by skillseal" in capsys.readouterr().out


def test_broken_policy_fails_closed(project, isolated_env, capsys):
    (isolated_env / ".config" / "skillseal" / "policy.json").write_text("{not json")
    assert run_hook("claude", "PreToolUse", stdin(project)) == 2
    assert "cannot verify" in capsys.readouterr().err


def test_warn_mode_allows_with_message(project, keys, isolated_env, capsys):
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1], mode="warn")
    make_skill(project / ".claude" / "skills")
    assert run_hook("claude", "PreToolUse", stdin(project)) == 0
    assert "not approved" in capsys.readouterr().err


def test_audit_mode_is_silent_and_logs(project, keys, isolated_env, capsys):
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1], mode="audit")
    make_skill(project / ".claude" / "skills")
    assert run_hook("claude", "PreToolUse", stdin(project)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and captured.out == ""
    log = (isolated_env / ".cache" / "skillseal" / "audit.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["failures"]


def test_user_skills_dir_is_checked(project, isolated_env):
    make_skill(isolated_env / ".claude" / "skills")
    assert run_hook("claude", "PreToolUse", stdin(project)) == 2


def test_install_is_idempotent_and_keeps_other_hooks(tmp_path):
    proj = tmp_path / "p"
    settings = proj / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}
    settings.write_text(json.dumps({"permissions": {"deny": ["Bash(rm *)"]}, "hooks": {"PreToolUse": [other]}}))
    install("claude", "project", proj, windows=False)
    install("claude", "project", proj, windows=False)
    data = json.loads(settings.read_text())
    assert data["permissions"] == {"deny": ["Bash(rm *)"]}
    pre = data["hooks"]["PreToolUse"]
    assert pre[0] == other and len(pre) == 2
    assert pre[1]["hooks"][0]["command"] == "skillseal hook claude PreToolUse || exit 2"
    assert pre[1]["hooks"][0]["onFailure"] == "block"
    assert len(data["hooks"]["SessionStart"]) == 1


@pytest.mark.parametrize("agent,rel", [
    ("codex", ".codex/hooks.json"),
    ("gemini", ".gemini/settings.json"),
    ("copilot", ".github/hooks/skillseal.json"),
])
def test_install_writes_agent_files(tmp_path, agent, rel):
    paths, _ = install(agent, "project", tmp_path, windows=False)
    assert paths == [tmp_path / rel]
    data = json.loads((tmp_path / rel).read_text())
    text = json.dumps(data)
    assert f"skillseal hook {agent}" in text and "exit 2" in text


def test_install_copilot_user_scope(isolated_env, tmp_path):
    paths, _ = install("copilot", "user", tmp_path)
    assert paths == [isolated_env / ".copilot" / "hooks" / "skillseal.json"]
    hook = json.loads(paths[0].read_text())["hooks"]["preToolUse"][0]
    assert hook["timeoutSec"] == 60 and "if (-not $?) { exit 2 }" in hook["powershell"]


def test_install_copilot_keeps_other_hooks(tmp_path):
    path = tmp_path / ".github" / "hooks" / "skillseal.json"
    path.parent.mkdir(parents=True)
    mine = {"type": "command", "bash": "./audit.sh", "timeoutSec": 5}
    path.write_text(json.dumps({"version": 1, "hooks": {"preToolUse": [mine], "postToolUse": [mine]}}))
    install("copilot", "project", tmp_path)
    install("copilot", "project", tmp_path)
    hooks = json.loads(path.read_text())["hooks"]
    assert hooks["postToolUse"] == [mine]
    assert hooks["preToolUse"][0] == mine and len(hooks["preToolUse"]) == 2
    assert len(hooks["sessionStart"]) == 1


NODE_HARNESS = """
const { pathToFileURL } = require("node:url");
(async () => {
  const mod = await import(pathToFileURL(process.argv[2]).href);
  const hooks = await mod.SkillsealGuard({ directory: process.argv[3], worktree: process.argv[3] });
  try {
    await hooks["tool.execute.before"]({ tool: "bash" }, { args: {} });
    console.log("ALLOWED");
  } catch (e) {
    console.log("BLOCKED " + e.message.split("\\n")[0]);
  }
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("signed,exe_ok,expected", [
    (False, True, "BLOCKED skillseal: 1 skill not approved"),
    (True, True, "ALLOWED"),
    (True, False, "BLOCKED skillseal could not"),
])
def test_opencode_plugin(project, keys, tmp_path, signed, exe_ok, expected):
    skill = make_skill(project / ".opencode" / "skills")
    if signed:
        sign_skill(skill, method="key", private_key=keys[0])
    exe = str(Path(sys.executable).with_name("skillseal")) if exe_ok else str(tmp_path / "missing-skillseal")
    if exe_ok and not Path(exe).exists():
        pytest.skip("skillseal console script not installed next to python")
    paths, _ = install("opencode", "project", project, exe=exe)
    assert paths == [project / ".opencode" / "plugins" / "skillseal.js"]
    harness = tmp_path / "harness.cjs"
    harness.write_text(NODE_HARNESS)
    r = subprocess.run(["node", str(harness), str(paths[0]), str(project)], capture_output=True, text=True,
                       env={**os.environ}, timeout=120, check=False)
    assert r.stdout.strip().startswith(expected), r.stdout + r.stderr


@pytest.mark.parametrize("windows,exe", [
    (False, "skillseal"),
    (False, "/opt/my tools/skillseal"),
    (True, "skillseal"),
    (True, r"C:\Program Files\it's\skillseal.exe"),
])
@pytest.mark.parametrize("agent", ["claude", "codex", "gemini", "copilot", "opencode"])
def test_uninstall_removes_only_ours(tmp_path, agent, windows, exe):
    from skillseal.install import uninstall

    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}
    if agent == "claude":
        f = tmp_path / ".claude" / "settings.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [other]}}))
    install(agent, "project", tmp_path, exe=exe, windows=windows)
    paths, _ = install(agent, "project", tmp_path, exe=exe, windows=windows)
    if agent in ("claude", "codex", "gemini"):
        events = json.loads(paths[0].read_text())["hooks"]
        assert all(len([g for g in groups if g != other]) == 1 for groups in events.values())
    assert uninstall(agent, "project", tmp_path) == paths
    if agent == "claude":
        assert json.loads(paths[0].read_text()) == {"model": "x", "hooks": {"PreToolUse": [other]}}
    elif agent in ("copilot", "opencode"):
        assert not paths[0].exists()
    else:
        assert "skillseal" not in paths[0].read_text()
    assert uninstall(agent, "project", tmp_path) == []


def _hook_commands(paths, agent, windows):
    """Yield (event, how-to-run) for each blocking or session hook written for `agent`."""
    data = json.loads(paths[0].read_text())
    for event, entries in data["hooks"].items():
        for entry in entries:
            for h in entry.get("hooks", [entry]):
                if agent == "copilot":
                    yield event, ("ps", h["powershell"]) if windows else ("sh", h["bash"])
                elif "args" in h:
                    yield event, ("exec", [h["command"], *h["args"]])
                elif agent == "codex" and windows:
                    yield event, ("cmd", h["command"])
                elif agent == "gemini" and windows:
                    # Gemini CLI appends this to every PowerShell hook command.
                    yield event, ("ps", h["command"] + "; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }")
                else:
                    yield event, ("sh", h["command"])


def _run(how, payload, cwd, shell_exe=None):
    kind, cmd = how
    if kind == "exec":
        args = cmd
    elif kind == "sh":
        args = ["sh", "-c", cmd]
    elif kind == "cmd":
        # Same command line Codex builds: %COMSPEC% /C "<command>"
        args = f'{os.environ.get("COMSPEC", "cmd.exe")} /C "{cmd}"'
    else:
        args = [shell_exe, "-NoProfile", "-NonInteractive", "-Command", cmd]
    return subprocess.run(args, input=payload, capture_output=True, text=True, cwd=cwd, timeout=120, check=False)


def _real_skillseal(tmp_path):
    found = shutil.which("skillseal") or shutil.which("skillseal", path=str(Path(sys.executable).parent))
    if not found:
        pytest.skip("skillseal console script not installed")
    # A copy in a folder with a space and an apostrophe proves the quoting.
    target = tmp_path / "my tools's" / Path(found).name
    target.parent.mkdir()
    shutil.copy2(found, target)
    return str(target)


SHELLS = ["powershell.exe", "pwsh"] if os.name == "nt" else [None]


@pytest.mark.parametrize("shell_exe", SHELLS)
@pytest.mark.parametrize("agent", ["claude", "codex", "gemini", "copilot"])
@pytest.mark.parametrize("state", ["unsigned", "signed", "missing-binary"])
def test_installed_hook_commands_run_in_real_shells(project, keys, tmp_path, agent, state, shell_exe):
    windows = os.name == "nt"
    if shell_exe and not shutil.which(shell_exe):
        pytest.skip(f"{shell_exe} not installed")
    skill = make_skill(project / (".claude" if agent == "claude" else ".agents") / "skills")
    if state != "unsigned":
        sign_skill(skill, method="key", private_key=keys[0])
    if state == "missing-binary":
        if agent == "claude" and windows:
            pytest.skip("exec form: Claude Code itself blocks via onFailure when the binary is missing")
        exe = str(tmp_path / "gone dir" / ("skillseal.exe" if windows else "skillseal"))
    else:
        exe = _real_skillseal(tmp_path)
    paths, _ = install(agent, "project", project, exe=exe, windows=windows)
    blocking = {"claude": "PreToolUse", "codex": "PreToolUse", "gemini": "BeforeTool", "copilot": "preToolUse"}[agent]
    payload = json.dumps({"cwd": str(project), "tool_name": "Bash", "toolName": "bash"})
    # Run from another folder: the project is only known from stdin, so a shell
    # that does not pass stdin on to skillseal makes this test fail.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    ran = 0
    for event, how in _hook_commands(paths, agent, windows):
        if event != blocking:
            continue
        r = _run(how, payload, elsewhere, shell_exe)
        ran += 1
        out = r.stdout + r.stderr
        if state == "signed":
            assert r.returncode == 0 and "not approved" not in out, (how, out)
        elif state == "missing-binary":
            assert r.returncode == 2, (how, r.returncode, out)
        elif agent == "gemini":
            assert r.returncode == 0 and json.loads(r.stdout)["decision"] == "deny", (how, out)
        else:
            assert r.returncode == 2 and "not approved" in out, (how, r.returncode, out)
    assert ran == 1
