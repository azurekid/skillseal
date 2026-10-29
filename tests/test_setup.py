import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

from skillseal import policy as policy_mod
from skillseal import setup
from skillseal.cli import main
from skillseal.policy import load_policy, user_policy_path
from skillseal.sign import sign_skill
from skillseal.verify import verify_skill

from conftest import make_key, make_skill


@pytest.fixture
def bundle(tmp_path, keys):
    _, pub = keys
    public = pub.read_bytes()
    path = tmp_path / "team.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("team.json", json.dumps({
            "format": "skillseal-team-v1", "organization": "Contoso",
            "key_sha256": hashlib.sha256(public).hexdigest(),
        }))
        archive.writestr("policy.json", json.dumps(setup.approval_policy("Contoso")))
        archive.writestr("approval.pub", public)
    return path


def join(bundle, tmp_path, agent="copilot", yes=True):
    return setup.join_team(bundle, agent, shutil.which("skillseal") or "skillseal", yes, tmp_path)


def test_demo_is_isolated(capsys):
    assert main(["demo"]) == 0
    assert capsys.readouterr().out.count("PASS") == 3
    assert not user_policy_path().exists()
    assert not (Path.home() / ".copilot").exists()


def test_join_audit_and_repeat_preserves_hooks(bundle, tmp_path):
    config = Path.home() / ".copilot/hooks/skillseal.json"
    config.parent.mkdir(parents=True)
    other = {"type": "command", "bash": "echo other"}
    config.write_text(json.dumps({"hooks": {"preToolUse": [other]}}))
    assert join(bundle, tmp_path) == 0
    assert load_policy().mode == "audit"
    assert json.loads(config.read_text())["hooks"]["preToolUse"][0] == other
    original = config.read_bytes()
    assert join(bundle, tmp_path) == 0
    assert config.read_bytes() == original
    assert len(list(config.parent.glob("*.backup-*"))) == 1


@pytest.mark.parametrize("agent", setup.SETUP_AGENTS)
def test_every_supported_setup_agent(bundle, tmp_path, agent):
    assert join(bundle, tmp_path, agent) == 0
    assert load_policy().signers[0].name == "Contoso"


@pytest.mark.parametrize("agent", setup.SETUP_AGENTS)
def test_join_replaces_empty_default_policy(bundle, tmp_path, agent, capsys):
    assert main(["init"]) == 0
    target = user_policy_path()
    original = target.read_bytes()
    assert join(bundle, tmp_path, agent) == 0
    assert json.loads(target.read_text()) == setup.approval_policy("Contoso")
    assert (target.parent / "approval.pub").is_file()
    assert list(target.parent.glob("policy.json.backup-*"))[0].read_bytes() == original
    assert "empty default policy" in capsys.readouterr().out


def test_default_policy_to_enforcement(bundle, tmp_path, keys, monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda _: "skillseal")
    skill = make_skill(tmp_path / ".agents/skills")
    sign_skill(skill, method="key", private_key=keys[0])
    assert main(["init"]) == 0
    assert main(["check", "--cwd", str(tmp_path)]) == 1
    assert join(bundle, tmp_path) == 0
    assert main(["check", "--cwd", str(tmp_path)]) == 0
    assert setup.enable_enforcement("copilot", True, tmp_path) == 0
    assert load_policy().mode == "enforce"
    assert not load_policy().allow_repo_signers
    enforced = user_policy_path().read_bytes()
    assert join(bundle, tmp_path) == 0
    assert user_policy_path().read_bytes() == enforced
    assert verify_skill(skill, load_policy(), use_cache=False).ok
    (skill / "SKILL.md").write_text("Edited after approval\n")
    assert not verify_skill(skill, load_policy(), use_cache=False).ok
    unsigned = make_skill(tmp_path / ".agents/skills", "unsigned")
    assert not verify_skill(unsigned, load_policy(), use_cache=False).ok
    other_private, _ = make_key(tmp_path, "untrusted")
    sign_skill(unsigned, method="key", private_key=other_private)
    assert not verify_skill(unsigned, load_policy(), use_cache=False).ok


def test_declining_default_policy_replacement_preserves_settings(bundle, tmp_path, monkeypatch):
    assert main(["init"]) == 0
    target = user_policy_path()
    original = target.read_bytes()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    with pytest.raises(setup.SetupError, match="Cancelled"):
        join(bundle, tmp_path, yes=False)
    assert target.read_bytes() == original
    assert not (target.parent / "approval.pub").exists()
    assert not (Path.home() / ".copilot").exists()
    assert not list(target.parent.glob("*.backup-*"))


def test_decline_and_noninteractive_need_explicit_trust(bundle, tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(setup.SetupError, match="Confirmation"):
        join(bundle, tmp_path, yes=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    with pytest.raises(setup.SetupError, match="Cancelled"):
        join(bundle, tmp_path, yes=False)
    assert not user_policy_path().exists()
    assert not (Path.home() / ".copilot").exists()


@pytest.mark.parametrize("extra", [
    {"revoked_skills": {"a" * 64: "withdrawn"}},
    {"revoked_skills": {}},
    {"skill_roots": ["/custom/skills"]},
    {"allow_repo_signers": True},
])
def test_cannot_replace_existing_policy_or_revocations(bundle, tmp_path, extra):
    target = user_policy_path()
    target.parent.mkdir(parents=True)
    original = json.dumps({"mode": "enforce", "trusted_signers": [],
                           "allow_repo_signers": False, **extra}).encode()
    target.write_bytes(original)
    with pytest.raises(setup.SetupError, match="different policy"):
        join(bundle, tmp_path)
    assert target.read_bytes() == original


def test_cannot_replace_existing_key(bundle, tmp_path):
    target = user_policy_path().parent / "approval.pub"
    target.parent.mkdir(parents=True)
    target.write_text("existing authority")
    with pytest.raises(setup.SetupError, match="different approval key"):
        join(bundle, tmp_path)
    assert target.read_text() == "existing authority"
    assert not user_policy_path().exists()


def test_system_managed_refused(bundle, tmp_path, monkeypatch):
    target = tmp_path / "system.json"
    target.write_text("{}")
    monkeypatch.setattr(policy_mod, "system_policy_path", lambda: target)
    with pytest.raises(setup.SetupError, match="IT already manages"):
        join(bundle, tmp_path)
    assert not user_policy_path().exists()


def test_custom_policy_location(bundle, tmp_path, monkeypatch):
    target = tmp_path / "custom/policy.json"
    monkeypatch.setenv("SKILLSEAL_POLICY", str(target))
    assert join(bundle, tmp_path) == 0
    assert target.exists()
    assert (target.parent / "approval.pub").exists()
    assert load_policy().mode == "audit"


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation requires optional privileges")
def test_linked_config_directory_and_linked_file(bundle, tmp_path):
    real = tmp_path / "real-config"
    real.mkdir()
    (Path.home() / ".config").symlink_to(real, target_is_directory=True)
    assert join(bundle, tmp_path) == 0
    assert (real / "skillseal/policy.json").exists()
    target = user_policy_path()
    original = target.read_bytes()
    target.unlink()
    other = tmp_path / "other-policy.json"
    other.write_bytes(original)
    target.symlink_to(other)
    with pytest.raises(setup.SetupError, match="symbolic-link settings"):
        join(bundle, tmp_path)
    assert target.is_symlink()
    assert other.read_bytes() == original


@pytest.mark.parametrize("bad_name", ["../approval.pub", "/tmp/approval.pub", "extra.sh"])
def test_bundle_rejects_unexpected_members(bundle, bad_name):
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr(bad_name, "bad")
    with pytest.raises(setup.SetupError, match="expected only"):
        setup.read_bundle(bundle)


def test_bundle_rejects_duplicate_members(bundle):
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.writestr("approval.pub", "bad")
    with pytest.raises(setup.SetupError, match="expected only"):
        setup.read_bundle(bundle)


def test_key_cannot_hide_additional_content(bundle):
    with zipfile.ZipFile(bundle) as archive:
        data = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    data["approval.pub"] += b"\nUnexpected trailing content\n"
    team = json.loads(data["team.json"])
    team["key_sha256"] = hashlib.sha256(data["approval.pub"]).hexdigest()
    data["team.json"] = json.dumps(team).encode()
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, value in data.items():
            archive.writestr(name, value)
    with pytest.raises(setup.SetupError, match="public-only PEM"):
        setup.read_bundle(bundle)


@pytest.mark.parametrize("change", ["fingerprint", "policy", "key", "size", "symlink"])
def test_invalid_bundle_content(bundle, change):
    with zipfile.ZipFile(bundle) as archive:
        data = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    if change == "fingerprint":
        team = json.loads(data["team.json"])
        team["key_sha256"] = "0" * 64
        data["team.json"] = json.dumps(team).encode()
    elif change == "policy":
        data["policy.json"] = b'{"mode":"enforce"}'
    elif change == "key":
        data["approval.pub"] = b"not a key"
    elif change == "size":
        data["team.json"] = b"x" * (setup.MAX_BUNDLE_BYTES + 1)
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in data.items():
            member = zipfile.ZipInfo(name)
            if change == "symlink" and name == "approval.pub":
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(member, value)
    with pytest.raises(ValueError):
        setup.read_bundle(bundle)
    assert not user_policy_path().exists()


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_atomic_rollback(tmp_path, monkeypatch, error):
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"keep")
    new = tmp_path / "new.json"
    atomic = setup._atomic

    def fail(path, content):
        if path == new:
            raise error("test interrupted write")
        atomic(path, content)

    monkeypatch.setattr(setup, "_atomic", fail)
    with pytest.raises(error, match="interrupted write"):
        setup._apply({existing: b"changed", new: b"new"})
    assert existing.read_bytes() == b"keep"
    assert not new.exists()
    assert list(tmp_path.glob("existing.json.backup-*"))[0].read_bytes() == b"keep"


def test_bad_hook_json_leaves_policy_uninstalled(bundle, tmp_path):
    target = Path.home() / ".copilot/hooks/skillseal.json"
    target.parent.mkdir(parents=True)
    target.write_text("broken JSON")
    with pytest.raises(ValueError):
        join(bundle, tmp_path)
    assert target.read_text() == "broken JSON"
    assert not user_policy_path().exists()


def test_enforce_requires_skills_and_preserves_policy(bundle, tmp_path, keys, monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda _: "skillseal")
    join(bundle, tmp_path)
    target = user_policy_path()
    original = target.read_bytes()
    with pytest.raises(setup.SetupError, match="No skills"):
        setup.enable_enforcement("copilot", True, tmp_path)
    skill = make_skill(tmp_path / ".github/skills")
    with pytest.raises(setup.SetupError, match="need approval"):
        setup.enable_enforcement("copilot", True, tmp_path)
    sign_skill(skill, method="key", private_key=keys[0])
    raw = json.loads(original)
    raw["revoked_skills"] = {"b" * 64: "another withdrawn skill"}
    raw["skill_roots"] = []
    target.write_text(json.dumps(raw))
    assert setup.enable_enforcement("copilot", True, tmp_path) == 0
    raw["mode"] = "enforce"
    assert json.loads(target.read_text()) == raw
    assert verify_skill(skill, load_policy(), use_cache=False).ok


def test_enforce_refuses_missing_hook(bundle, tmp_path):
    join(bundle, tmp_path)
    config = Path.home() / ".copilot/hooks/skillseal.json"
    config.write_text('{"hooks":{}}')
    with pytest.raises(setup.SetupError, match="hooks need updating"):
        setup.enable_enforcement("copilot", True, tmp_path)
    assert load_policy().mode == "audit"


def test_organization_to_developer_flow(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repository"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)
    assert setup.organization(repo, "Contoso", "contoso/skills", "main", False, True) == 0
    bundle = setup._team_bundle_path("contoso/skills")
    assert bundle.is_file() and not bundle.is_relative_to(repo)
    output = capsys.readouterr().out
    assert f"Team package: {bundle}" in output
    assert str(bundle) in output
    team, public, _ = setup.read_bundle(bundle)
    assert team["organization"] == "Contoso"
    backups = list((Path.home() / ".skillseal-authorities").glob("*/approval-private.pem"))
    assert len(backups) == 1
    if os.name != "nt":
        assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    for path in repo.rglob("*"):
        if path.is_file():
            assert b"PRIVATE KEY" not in path.read_bytes()
    workflow = (repo / ".github/workflows/approve-skills.yml").read_text()
    for roots in setup.PROJECT_DIRS.values():
        for root in roots:
            assert root + "/*" in workflow
    assert f"azurekid/skillseal@{setup.ACTION_REF}" in workflow
    assert "pull_request" not in workflow
    assert join(bundle, repo) == 0
    assert verify_skill(repo / ".agents/skills/skillseal-welcome", load_policy(), use_cache=False).ok
    assert public == (repo / ".skillseal/approval.pub").read_bytes()
    with pytest.raises(setup.SetupError, match="already exists"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", False, True)


def test_secret_upload_uses_stdin_only(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    calls = []

    def gh(args, project, *, private=None):
        calls.append((args, private))
        if args[:2] == ["repo", "view"]:
            return "contoso/skills"
        return "[]" if args[:2] == ["secret", "list"] else ""

    monkeypatch.setattr(setup, "_gh", gh)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "gh")
    assert setup.organization(repo, "Contoso", "contoso/skills", "main", True, True) == 0
    args, private = calls[-1]
    assert args == ["secret", "set", "SKILLSEAL_APPROVAL_PRIVATE_KEY", "--repo", "contoso/skills"]
    assert b"PRIVATE KEY" in private
    assert not any("PRIVATE KEY" in arg for arg in args)


def test_existing_secret_is_not_overwritten(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "gh")
    monkeypatch.setattr(setup, "_gh", lambda args, *a, **k: "contoso/skills" if args[:2] == ["repo", "view"]
                        else '[{"name":"SKILLSEAL_APPROVAL_PRIVATE_KEY"}]')
    with pytest.raises(setup.SetupError, match="already exists"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", True, True)
    assert not setup._team_bundle_path("contoso/skills").exists()
    assert not (Path.home() / ".skillseal-authorities").exists()


def test_cli_errors_are_readable(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("skillseal.cli._default_exe", lambda: "/usr/local/bin/skillseal")
    assert main(["setup", "--bundle", str(tmp_path / "missing.zip"), "--yes"]) == 2
    assert "could not finish" in capsys.readouterr().err
    assert main(["setup", "enforce", "--bundle", "team.zip"]) == 2


def test_keyboard_cancellation_is_clean(monkeypatch, capsys):
    def cancel():
        raise KeyboardInterrupt

    monkeypatch.setattr(setup, "demo", cancel)
    assert main(["demo"]) == 130
    assert "Cancelled" in capsys.readouterr().err


def test_demo_from_other_directory(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run([sys.executable, "-m", "skillseal", "demo"], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("PASS") == 3


@pytest.mark.parametrize("content", ['{"hooks":[]}', '{"hooks":{"preToolUse":42}}', "null"])
def test_invalid_existing_hook_structure_is_safe(bundle, tmp_path, content):
    target = Path.home() / ".copilot/hooks/skillseal.json"
    target.parent.mkdir(parents=True)
    target.write_text(content)
    with pytest.raises(setup.SetupError, match="Cannot merge"):
        join(bundle, tmp_path)
    assert target.read_text() == content
    assert not user_policy_path().exists()


def test_enforcement_cancelled_without_changes(bundle, tmp_path, keys, monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda _: "skillseal")
    join(bundle, tmp_path)
    skill = make_skill(tmp_path / ".github/skills")
    sign_skill(skill, method="key", private_key=keys[0])
    original = user_policy_path().read_bytes()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    with pytest.raises(setup.SetupError, match="Cancelled"):
        setup.enable_enforcement("copilot", False, tmp_path)
    assert user_policy_path().read_bytes() == original


def test_failed_upload_keeps_recoverable_authority(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "gh")

    def gh(args, *a, **k):
        if args[:2] == ["repo", "view"]:
            return "contoso/skills"
        if args[:2] == ["secret", "set"]:
            raise setup.SetupError("upload failed")
        return "[]"

    monkeypatch.setattr(setup, "_gh", gh)
    with pytest.raises(setup.SetupError, match="upload failed"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", True, True)
    bundle = setup._team_bundle_path("contoso/skills")
    assert bundle.exists() and not bundle.is_relative_to(repo)
    assert list((Path.home() / ".skillseal-authorities").glob("*/approval-private.pem"))
    assert "same key" in capsys.readouterr().err
    assert join(bundle, repo) == 0
    assert verify_skill(repo / ".agents/skills/skillseal-welcome", load_policy(), use_cache=False).ok


def test_invalid_repo_and_branch_cannot_create_authority(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(setup.SetupError, match="not a Git repository"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", False, True)
    (repo / ".git").rmdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    with pytest.raises(setup.SetupError, match="valid Git signing branch"):
        setup.organization(repo, "Contoso", "contoso/skills", "main${{injection}}", False, True)
    assert not (Path.home() / ".skillseal-authorities").exists()


def test_cli_join_then_real_guard_rejects_edit(bundle, tmp_path, keys, monkeypatch):
    monkeypatch.setenv("PATH", sysconfig.get_path("scripts") + os.pathsep + os.environ["PATH"])
    skill = make_skill(tmp_path / ".github/skills")
    sign_skill(skill, method="key", private_key=keys[0])

    def cli(*args):
        return subprocess.run([sys.executable, "-m", "skillseal", *args], cwd=tmp_path,
                              capture_output=True, text=True)

    result = cli("setup", "--bundle", str(bundle), "--yes")
    assert result.returncode == 0, result.stderr
    result = cli("setup", "enforce", "--yes")
    assert result.returncode == 0, result.stderr
    hook = json.loads((Path.home() / ".copilot/hooks/skillseal.json").read_text())
    handler = hook["hooks"]["preToolUse"][0]
    if os.name == "nt":
        args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", handler["powershell"]]
    else:
        args = ["sh", "-c", handler["bash"]]

    def guard():
        return subprocess.run(args, input=json.dumps({"cwd": str(tmp_path)}),
                              capture_output=True, text=True)

    assert guard().returncode == 0
    (skill / "SKILL.md").write_text("Edited after approval.")
    assert guard().returncode != 0


@pytest.mark.parametrize("secret_exists", [True, False])
def test_original_key_reused_without_rotation(tmp_path, keys, monkeypatch, capsys, secret_exists):
    repo = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    workflow = repo / ".github/workflows/approve-skills.yml"
    workflow.parent.mkdir(parents=True)
    original_workflow = b"name: Existing organization workflow\n"
    workflow.write_bytes(original_workflow)
    private, pub = keys
    original_key = private.read_bytes()
    calls = []

    def gh(args, project, *, private=None):
        calls.append((args, private))
        if args[:2] == ["repo", "view"]:
            return "contoso/skills"
        if args[:2] == ["secret", "list"]:
            return '[{"name":"SKILLSEAL_APPROVAL_PRIVATE_KEY"}]' if secret_exists else "[]"
        return ""

    monkeypatch.setattr(setup, "_gh", gh)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "gh")
    assert setup.organization(repo, "Contoso", "contoso/skills", "main", True, True,
                              private_key=private) == 0
    uploads = [data for args, data in calls if args[:2] == ["secret", "set"]]
    assert uploads == ([] if secret_exists else [original_key])
    assert private.read_bytes() == original_key
    assert workflow.read_bytes() == original_workflow
    assert (repo / ".skillseal/approval.pub").read_bytes() == pub.read_bytes()
    assert not (Path.home() / ".skillseal-authorities").exists()
    assert join(setup._team_bundle_path("contoso/skills"), repo) == 0
    assert verify_skill(repo / ".agents/skills/skillseal-welcome", load_policy(), use_cache=False).ok
    output = capsys.readouterr().out
    assert "No new authority" in output
    assert "SAME key" in output
    assert original_key.decode() not in output


def test_reuse_private_key_decline_has_no_side_effects(tmp_path, keys, monkeypatch):
    repo = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)
    with pytest.raises(setup.SetupError, match="Cancelled"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", False, False,
                           private_key=keys[0])
    assert list(repo.iterdir()) == [repo / ".git"]
    assert not (Path.home() / ".skillseal-authorities").exists()


def test_reuse_requires_private_key_outside_repo(tmp_path, keys):
    repo = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    private = repo / "approval-private.pem"
    shutil.copyfile(keys[0], private)
    with pytest.raises(setup.SetupError, match="outside this repository"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", False, True,
                           private_key=private)
    assert not setup._team_bundle_path("contoso/skills").exists()


def test_reuse_rejects_public_key_file(tmp_path, keys):
    repo = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    with pytest.raises(setup.SetupError, match="private-key PEM"):
        setup.organization(repo, "Contoso", "contoso/skills", "main", False, True,
                           private_key=keys[1])
    assert not setup._team_bundle_path("contoso/skills").exists()


def test_private_key_option_only_for_organization(tmp_path, capsys):
    assert main(["setup", "--private-key", str(tmp_path / "key.pem")]) == 2
    assert "belong to setup organization" in capsys.readouterr().err
