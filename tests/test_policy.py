import json

import pytest

from conftest import make_key, write_policy
from skillseal.policy import PolicyError, load_policy


def test_no_policy_trusts_nothing(tmp_path):
    p = load_policy(project=tmp_path)
    assert p.signers == [] and p.mode == "enforce"


def test_repo_policy_alone_is_not_trusted(tmp_path, keys):
    write_policy(tmp_path / "repo" / ".skillseal" / "policy.json", keys[1], mode="audit", skill_roots=["extra"])
    p = load_policy(project=tmp_path / "repo")
    assert p.signers == []
    assert p.mode == "enforce"
    assert p.skill_roots == ["extra"]


def test_repo_signers_ignored_unless_allowed(tmp_path, keys, isolated_env):
    other = tmp_path / "o"
    other.mkdir()
    _, repo_pub = make_key(other)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1])
    write_policy(tmp_path / "repo" / ".skillseal" / "policy.json", repo_pub, mode="audit")
    p = load_policy(project=tmp_path / "repo")
    assert [s.public_key for s in p.signers] == [str(keys[1])]
    assert p.mode == "enforce"


def test_repo_signers_added_when_allowed(tmp_path, keys, isolated_env):
    other = tmp_path / "o"
    other.mkdir()
    _, repo_pub = make_key(other)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", keys[1], allow_repo_signers=True)
    write_policy(tmp_path / "repo" / ".skillseal" / "policy.json", repo_pub)
    p = load_policy(project=tmp_path / "repo")
    assert len(p.signers) == 2


def test_system_policy_wins(tmp_path, keys, isolated_env, monkeypatch):
    from skillseal import policy as policy_mod

    sys_path = write_policy(tmp_path / "etc" / "policy.json", keys[1], mode="warn")
    monkeypatch.setattr(policy_mod, "system_policy_path", lambda: sys_path)
    write_policy(isolated_env / ".config" / "skillseal" / "policy.json", None, mode="audit")
    p = load_policy(project=tmp_path)
    assert p.mode == "warn" and len(p.signers) == 1


def test_relative_paths_resolve_from_policy_dir(tmp_path):
    d = tmp_path / "pol"
    d.mkdir()
    (d / "policy.json").write_text(json.dumps({"trusted_signers": [{"type": "public_key", "public_key": "k.pub"}]}))
    p = load_policy(explicit=d / "policy.json")
    assert p.signers[0].public_key == str((d / "k.pub").resolve())


@pytest.mark.parametrize("revoked", [
    [], None, {"invalid": "incident"}, {"A" * 64: "incident"},
    {"0" * 64: ""}, {"0" * 64: 3},
])
def test_invalid_revocations_fail_explicitly(tmp_path, revoked):
    path = write_policy(tmp_path / "policy.json", None, revoked_skills=revoked)
    with pytest.raises(PolicyError, match="revoked_skills"):
        load_policy(explicit=path)


def test_repo_cannot_clear_authoritative_revocation(tmp_path, keys, isolated_env):
    digest = "a" * 64
    write_policy(isolated_env / ".config/skillseal/policy.json", keys[1],
                 revoked_skills={digest: "incident"}, allow_repo_signers=True)
    write_policy(tmp_path / ".skillseal/policy.json", keys[1], revoked_skills={})
    policy = load_policy(project=tmp_path)
    assert policy.revoked_skills == {digest: "incident"}


def test_revocation_changes_policy_fingerprint(tmp_path, keys):
    policy = load_policy(explicit=write_policy(tmp_path / "policy.json", keys[1]))
    before = policy.fingerprint()
    policy.revoked_skills["a" * 64] = "incident"
    assert before != policy.fingerprint()
