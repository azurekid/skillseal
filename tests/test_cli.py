import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import make_skill, write_policy
from skillseal.cli import main
from skillseal.policy import system_policy_path

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="uses sh")
no_system_policy = pytest.mark.skipif(system_policy_path().exists(), reason="a real system policy is installed")


def run_cli(args, stdin="", env=None):
    return subprocess.run(
        [sys.executable, "-m", "skillseal", *args],
        input=stdin, capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False,
    )


def test_init_sign_check_roundtrip(tmp_path, keys, isolated_env, monkeypatch, capsys):
    priv, pub = keys
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    skill = make_skill(proj / ".claude" / "skills")
    assert main(["init", "--public-key", str(pub)]) == 0
    assert main(["check", "--agent", "claude", "--cwd", str(proj)]) == 1
    assert main(["sign", "--no-scan", "--method", "key", "--private-key", str(priv), str(skill)]) == 0
    assert main(["check", "--agent", "claude", "--cwd", str(proj)]) == 0
    capsys.readouterr()
    assert main(["check", "--agent", "claude", "--cwd", str(proj), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "verified"


def test_sign_requires_scan_choice(tmp_path, keys):
    skill = make_skill(tmp_path)
    assert main(["sign", "--method", "key", "--private-key", str(keys[0]), str(skill)]) == 2
    assert not (skill / "skill.oms.sig").exists()


def test_scan_gate_blocks_signing(tmp_path, keys):
    skill = make_skill(tmp_path)
    failing = f'{sys.executable} -c "import sys; sys.exit(1)"'
    assert main(["sign", "--scan", failing, "--method", "key", "--private-key", str(keys[0]), str(skill)]) == 1
    assert not (skill / "skill.oms.sig").exists()
    passing = f'{sys.executable} -c "import sys; sys.exit(0)" {{path}}'
    assert main(["sign", "--scan", passing, "--method", "key", "--private-key", str(keys[0]), str(skill)]) == 0
    assert (skill / "skill.oms.sig").is_file()


@no_system_policy
def test_hook_subprocess_blocks(tmp_path, keys, isolated_env):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1])
    make_skill(proj / ".agents" / "skills")
    stdin = json.dumps({"hook_event_name": "PreToolUse", "cwd": str(proj), "tool_name": "Bash"})
    r = run_cli(["hook", "codex"], stdin)
    assert r.returncode == 2 and "not approved" in r.stderr


@posix_only
def test_missing_binary_still_blocks():
    # This is the exact wrapper `skillseal install` writes into hook configs.
    r = subprocess.run(["sh", "-c", "skillseal-does-not-exist hook claude PreToolUse || exit 2"], capture_output=True)
    assert r.returncode == 2


@posix_only
@no_system_policy
@pytest.mark.skipif(shutil.which("skillseal") is None, reason="skillseal not on PATH")
def test_installed_wrapper_allows_when_clean(tmp_path, isolated_env, keys):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1])
    r = subprocess.run(
        ["sh", "-c", "skillseal hook claude PreToolUse || exit 2"],
        input=json.dumps({"cwd": str(proj)}), capture_output=True, text=True,
        env={**os.environ}, check=False,
    )
    assert r.returncode == 0, r.stderr
