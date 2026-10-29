import hashlib
import shutil
from pathlib import Path

from skillseal.cli import main
from skillseal.policy import load_policy
from skillseal.verify import INVALID, verify_skill

STARTER = Path(__file__).parents[1] / "examples/starter"
KEY_FINGERPRINT = "b22cd994bc688234edaf8df63f23a923101cb5079e23d1dd0c2ee77c1875ad33"


def test_published_starters_verify_without_private_keys(tmp_path, isolated_env):
    root = tmp_path / "download with spaces"
    shutil.copytree(STARTER, root)
    policy = load_policy(explicit=root / "policy.json")
    skills = sorted((root / "skills").iterdir())
    assert len(skills) == 2
    for skill in skills:
        result = verify_skill(skill, policy, use_cache=False)
        assert result.ok, result.reasons
        assert result.signer == "Skillseal starter examples only"
    assert main(["verify", "--no-cache", "--policy", str(root / "policy.json"),
                 *(str(skill) for skill in skills)]) == 0
    assert not (isolated_env / ".config/skillseal/policy.json").exists()
    assert hashlib.sha256((root / "starter-approval.pub").read_bytes()).hexdigest() == KEY_FINGERPRINT
    guide = (STARTER.parents[1] / "GETTING-STARTED.md").read_text()
    assert KEY_FINGERPRINT in guide
    for path in root.rglob("*"):
        if path.is_file():
            assert b"PRIVATE KEY" not in path.read_bytes()


def test_starter_edit_rejected_and_normal_policy_does_not_trust_demo(tmp_path):
    root = tmp_path / "starter"
    shutil.copytree(STARTER, root)
    skill = root / "skills/friendly-greeting"
    assert not verify_skill(skill, load_policy(project=root), use_cache=False).ok
    policy = load_policy(explicit=root / "policy.json")
    with (skill / "SKILL.md").open("a", encoding="utf-8") as file:
        file.write("\nEdited example.\n")
    assert verify_skill(skill, policy, use_cache=False).status == INVALID
    assert verify_skill(root / "skills/writing-checklist", policy, use_cache=False).ok
