import json

import pytest

from conftest import make_skill, write_policy
from skillseal.cli import build_parser, cmd_check, _print_check
from skillseal.policy import Policy
from skillseal.sign import sign_skill
from skillseal.verify import Result


@pytest.mark.parametrize("mode", ["audit", "warn", "enforce"])
def test_check_readable_output(tmp_path, isolated_env, keys, capsys, mode):
    project = tmp_path / "project"
    project.mkdir()
    policy_path = write_policy(isolated_env / ".config/skillseal/policy.json", keys[1], mode=mode)
    unsigned = make_skill(project / ".claude/skills", "unsigned")
    signed = make_skill(project / ".claude/skills", "signed")
    sign_skill(signed, method="key", private_key=keys[0])
    args = build_parser().parse_args(["check", "--cwd", str(project), "--agent", "claude"])
    assert cmd_check(args) == 1
    out = capsys.readouterr().out
    assert "SKILLSEAL" in out and ".-------." in out
    assert "Summary: 2 skills | 1 verified | 1 not approved" in out
    assert out.index(str(unsigned)) < out.index(str(signed))
    assert "signer: test key" in out and "no skill.oms.sig" in out
    assert "~/.config/skillseal/policy.json" in out
    assert str(policy_path) not in out
    assert ("guards block tool use" in out) == (mode == "enforce")
    assert ("guards do not block" in out) == (mode != "enforce")


def test_check_json_unchanged(tmp_path, isolated_env, keys, capsys):
    write_policy(isolated_env / ".config/skillseal/policy.json", keys[1])
    skill = make_skill(tmp_path / ".claude/skills")
    args = build_parser().parse_args(["check", "--cwd", str(tmp_path), "--agent", "claude", "--json"])
    assert cmd_check(args) == 1
    results = json.loads(capsys.readouterr().out)
    assert results == [{"path": str(skill), "status": "unsigned", "signer": "", "reasons": ["no skill.oms.sig"]}]


def test_check_empty_and_no_signers(tmp_path, capsys):
    args = build_parser().parse_args(["check", "--cwd", str(tmp_path), "--agent", "claude"])
    assert cmd_check(args) == 0
    out = capsys.readouterr().out
    assert "No trusted signers configured" in out
    assert "No skills found" in out
    assert "All discovered skills" not in out


def test_check_all_verified_and_reason_overflow(capsys):
    _print_check([Result("/skills/demo", "verified", "team")], Policy(), ["claude"])
    assert "All discovered skills have a valid signature" in capsys.readouterr().out
    _print_check([Result("/skills/demo", "invalid", reasons=["changed"] * 23)], Policy(), ["claude"])
    out = capsys.readouterr().out
    assert "... 3 more reasons (use --json to see all)" in out
    assert out.count("         - changed") == 20
