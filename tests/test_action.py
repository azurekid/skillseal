import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_skill
from skillseal.policy import Policy, Signer
from skillseal.verify import verify_skill


def action_env(tmp_path, keys):
    skill = make_skill(tmp_path / ".claude/skills")
    runner = tmp_path / "runner"
    runner.mkdir()
    return skill, {
        **os.environ,
        "SIGNING_METHOD": "key",
        "APPROVAL_PRIVATE_KEY": keys[0].read_text(),
        "APPROVAL_CERTIFICATE": "",
        "APPROVAL_CERTIFICATE_CHAIN": "",
        "SKILLS": str(skill),
        "SCAN": "",
        "ALLOW_NO_SCAN": "true",
        "RUNNER_TEMP": str(runner),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }


def invoke(env):
    return subprocess.run([sys.executable, "-m", "skillseal.action"], env=env,
                          capture_output=True, text=True, check=False)


def test_organization_key_signs_skips_and_detects_tampering(tmp_path, keys):
    skill, env = action_env(tmp_path, keys)
    env["SKILLSEAL_SCANNER"] = "scanner-must-not-run-while-key-exists"
    assert invoke(env).returncode == 0
    policy = Policy(signers=[Signer("org", "public_key", public_key=str(keys[1]))])
    assert verify_skill(skill, policy, use_cache=False).ok
    assert "unchanged:" in invoke(env).stdout
    (skill / "SKILL.md").write_text("Reviewed new content.\n")
    assert invoke(env).returncode == 0
    assert verify_skill(skill, policy, use_cache=False).ok
    assert not list(Path(env["RUNNER_TEMP"]).iterdir())
    assert env["APPROVAL_PRIVATE_KEY"] not in Path(env["GITHUB_OUTPUT"]).read_text()


@pytest.mark.parametrize("method", ["key", "certificate", "unknown"])
def test_missing_or_invalid_credentials_fail_cleanly(tmp_path, keys, method):
    skill, env = action_env(tmp_path, keys)
    env.update(SIGNING_METHOD=method, APPROVAL_PRIVATE_KEY="")
    result = invoke(env)
    assert result.returncode == 1
    assert "::error::" in result.stderr
    assert not (skill / "skill.oms.sig").exists()
    assert not list(Path(env["RUNNER_TEMP"]).iterdir())


def test_scanner_cannot_inherit_credentials_or_find_key_files(tmp_path, keys):
    skill, env = action_env(tmp_path, keys)
    scanner = tmp_path / "scanner.py"
    scanner.write_text(
        "import os\nfrom pathlib import Path\n"
        "assert not any(k.startswith('APPROVAL_') for k in os.environ)\n"
        "assert not list(Path(os.environ['RUNNER_TEMP']).iterdir())\n"
        "raise SystemExit(1)\n"
    )
    env["SCAN"] = f'"{sys.executable}" "{scanner}"'
    result = invoke(env)
    assert result.returncode == 1 and "Scanner blocked" in result.stderr
    assert "AssertionError" not in result.stderr
    assert not (skill / "skill.oms.sig").exists()


def test_certificate_approval_verifies_and_rejects_mismatched_key(tmp_path, keys):
    skill, env = action_env(tmp_path, keys)
    lab = runpy.run_path(str(Path(__file__).parents[1] / "examples/trust-lab.py"))
    private, certificate, chain = lab["_external_certificate"](tmp_path)
    env.update(
        SIGNING_METHOD="certificate", APPROVAL_PRIVATE_KEY=private.read_text(),
        APPROVAL_CERTIFICATE=certificate.read_text(), APPROVAL_CERTIFICATE_CHAIN=chain.read_text(),
    )
    assert invoke(env).returncode == 0
    policy = Policy(signers=[Signer("org CA", "certificate", certificate_chain=(str(chain),))])
    assert verify_skill(skill, policy, use_cache=False).ok
    env["APPROVAL_PRIVATE_KEY"] = keys[0].read_text()
    result = invoke(env)
    assert result.returncode == 1 and "does not match" in result.stderr
    assert not list(Path(env["RUNNER_TEMP"]).iterdir())


def test_action_rejects_no_matches(tmp_path, keys):
    _, env = action_env(tmp_path, keys)
    env["SKILLS"] = str(tmp_path / "missing/*")
    result = invoke(env)
    assert result.returncode == 1 and "no skill folders" in result.stderr


def test_key_rotation_resigns_and_old_authority_rejects(tmp_path, keys):
    from conftest import make_key

    skill, env = action_env(tmp_path, keys)
    assert invoke(env).returncode == 0
    directory = tmp_path / "rotation"
    directory.mkdir()
    private, public = make_key(directory)
    env["APPROVAL_PRIVATE_KEY"] = private.read_text()
    assert invoke(env).returncode == 0
    old = Policy(signers=[Signer("old", "public_key", public_key=str(keys[1]))])
    new = Policy(signers=[Signer("new", "public_key", public_key=str(public))])
    assert not verify_skill(skill, old, use_cache=False).ok
    assert verify_skill(skill, new, use_cache=False).ok


def test_sign_failure_cleans_credentials(tmp_path, keys):
    skill, env = action_env(tmp_path, keys)
    (skill / "skill.oms.sig").mkdir()
    result = invoke(env)
    assert result.returncode == 1
    assert not list(Path(env["RUNNER_TEMP"]).iterdir())
    assert env["APPROVAL_PRIVATE_KEY"] not in result.stdout + result.stderr
