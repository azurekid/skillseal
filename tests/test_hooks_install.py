import json

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
    install("claude", "project", proj)
    install("claude", "project", proj)
    data = json.loads(settings.read_text())
    assert data["permissions"] == {"deny": ["Bash(rm *)"]}
    pre = data["hooks"]["PreToolUse"]
    assert pre[0] == other and len(pre) == 2
    assert pre[1]["hooks"][0]["command"] == "skillseal hook claude PreToolUse || exit 2"
    assert len(data["hooks"]["SessionStart"]) == 1


@pytest.mark.parametrize("agent,rel", [
    ("codex", ".codex/hooks.json"),
    ("gemini", ".gemini/settings.json"),
    ("copilot", ".github/hooks/skillseal.json"),
])
def test_install_writes_agent_files(tmp_path, agent, rel):
    paths, _ = install(agent, "project", tmp_path)
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
