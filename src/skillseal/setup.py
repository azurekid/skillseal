"""Guided onboarding: explicit trust, public bundles, and safe local defaults."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
import zlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import install as hooks
from . import policy as policies
from .discover import PROJECT_DIRS, discover
from .policy import load_policy, user_policy_path
from .sign import SignError, sign_skill
from .verify import verify_skill

SETUP_AGENTS = ("copilot", "claude", "codex", "gemini", "opencode")
ACTION_REF = "83dd7fa1f5841e3d8281dab7b93a480a201b9e1e"
MAX_BUNDLE_BYTES = 1024 * 1024


class SetupError(ValueError):
    pass


def starter_path() -> Path:
    packaged = Path(__file__).parent / "resources" / "starter"
    if packaged.is_dir():
        return packaged
    source = Path(__file__).resolve().parents[2] / "examples" / "starter"
    if source.is_dir():
        return source
    raise SetupError("Starter files are missing. Reinstall an official Skillseal package.")


def _json(data: dict) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode()


def _confirm(message: str, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise SetupError("Confirmation needs a terminal. Review the settings, then use --yes to approve.")
    if input(message + " [y/N] ").strip().lower() not in ("y", "yes"):
        raise SetupError("Cancelled. No further changes made.")


def _answer(value: str | None, question: str, default: str = "") -> str:
    if value:
        return value
    if not sys.stdin.isatty():
        if default:
            return default
        raise SetupError(f"{question} Supply the corresponding command option.")
    answer = input(question + (f" [{default}]" if default else "") + ": ").strip()
    return answer or default


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".skillseal-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _apply(files: dict[Path, bytes]) -> None:
    """Keep backups and roll back written files if a later write fails."""
    for path in files:
        if path.is_symlink():
            raise SetupError(f"Refusing a symbolic-link settings path: {path}")
        if path.exists() and not path.is_file():
            raise SetupError(f"Expected a file, found another kind of path: {path}")
    original = {path: path.read_bytes() if path.exists() else None for path in files}
    changed = []
    backup_id = uuid.uuid4().hex[:8]
    try:
        for path, content in files.items():
            if original[path] == content:
                continue
            previous = original[path]
            if previous is not None:
                backup = path.with_name(path.name + f".backup-{backup_id}")
                _atomic(backup, previous)
                print(f"Backup: {backup}")
            changed.append(path)
            _atomic(path, content)
    except (OSError, KeyboardInterrupt):
        for path in reversed(changed):
            previous = original[path]
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                _atomic(path, previous)
        raise


def approval_policy(name: str, public_file: str = "approval.pub") -> dict:
    return {
        "mode": "audit", "allow_repo_signers": False,
        "trusted_signers": [{"name": name, "type": "public_key", "public_key": public_file}],
        "revoked_skills": {},
    }


def read_bundle(path: Path) -> tuple[dict, bytes, dict]:
    try:
        if path.stat().st_size > 3 * MAX_BUNDLE_BYTES:
            raise SetupError("Team package is too large.")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {e.filename for e in entries} != {
                "team.json", "policy.json", "approval.pub",
            }:
                raise SetupError("Not a team package: expected only team.json, policy.json and approval.pub.")
            if any(e.file_size > MAX_BUNDLE_BYTES or e.flag_bits & 1
                   or stat.S_ISLNK(e.external_attr >> 16) for e in entries):
                raise SetupError("Team package is too large, encrypted or contains symbolic links.")
            data = {e.filename: archive.read(e) for e in entries}
        team = json.loads(data["team.json"])
        policy = json.loads(data["policy.json"])
        if (not isinstance(team, dict) or set(team) != {"format", "organization", "key_sha256"}
                or team.get("format") != "skillseal-team-v1"):
            raise SetupError("Unsupported team package format.")
        name = team.get("organization")
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or not name.isprintable():
            raise SetupError("Team package has an invalid organization name.")
        public = data["approval.pub"]
        key = serialization.load_pem_public_key(public)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise SetupError("Team approval key must be an EC P-256 public key.")
        if public != key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo):
            raise SetupError("Team approval key must be canonical public-only PEM without additional content.")
        if hashlib.sha256(public).hexdigest() != team.get("key_sha256"):
            raise SetupError("Team package key does not match its fingerprint.")
        if policy != approval_policy(name):
            raise SetupError("Team package must contain a single organization key and audit-only settings.")
        return team, public, policy
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError,
            TypeError, KeyError, RecursionError, NotImplementedError, zlib.error) as exc:
        raise SetupError("Invalid team package. Ask your administrator for a new copy.") from exc


def _hook_plan(agent: str, exe: str) -> dict[Path, bytes]:
    relative = {
        "copilot": ".copilot/hooks/skillseal.json", "claude": ".claude/settings.json",
        "codex": ".codex/hooks.json", "gemini": ".gemini/settings.json",
        "opencode": ".config/opencode/plugins/skillseal.js",
    }[agent]
    target = Path.home() / relative
    with tempfile.TemporaryDirectory(prefix="skillseal-hooks-") as directory:
        base = Path(directory)
        staged = base / relative
        if target.exists():
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(target.read_bytes())
        try:
            if agent in ("copilot", "opencode"):
                installer = hooks.install_copilot if agent == "copilot" else hooks.install_opencode
                paths = installer(base, exe, user=True)
            else:
                installer = {"claude": hooks.install_claude, "codex": hooks.install_codex,
                             "gemini": hooks.install_gemini}[agent]
                paths = installer(base, exe, windows=sys.platform == "win32")
        except (AttributeError, TypeError, KeyError, ValueError) as exc:
            raise SetupError(f"Cannot merge {agent} settings at {target}: {exc}. No settings changed.") from exc
        return {Path.home() / path.relative_to(base): path.read_bytes() for path in paths}


def join_team(bundle: Path, agent: str, exe: str, yes: bool, cwd: Path) -> int:
    team, public, policy = read_bundle(bundle)
    if policies.system_policy_path().exists():
        raise SetupError(f"IT already manages this machine through {policies.system_policy_path()}. Ask IT before onboarding.")
    target = user_policy_path().expanduser().absolute()
    public_path = target.parent / "approval.pub"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        same = dict(existing) if isinstance(existing, dict) else {}
        same["mode"] = "audit"
        if same != policy or existing.get("mode") not in ("audit", "warn", "enforce"):
            raise SetupError(f"A different policy already exists at {target}. Nothing replaced; ask your administrator to merge it.")
        policy = existing
    if public_path.exists() and public_path.read_bytes() != public:
        raise SetupError(f"A different approval key exists at {public_path}. Nothing replaced.")
    load_policy(project=cwd)
    print(f"Organization: {team['organization']}")
    print(f"Approval key SHA256: {team['key_sha256']}")
    print(f"Agent: {agent}\nMode: {policy['mode']}\nPolicy: {target}")
    print("Only continue if this package came through your organization's trusted channel.")
    _confirm("Trust this authority and configure your agent?", yes)
    plan = _hook_plan(agent, exe)
    plan.update({public_path: public, target: _json(policy)})
    _apply(plan)
    effective = load_policy(project=cwd)
    results = [verify_skill(skill, effective) for skill in discover([agent], cwd, effective.skill_roots)]
    failed = sum(not result.ok for result in results)
    print("\nSetup complete")
    print("  OK  Organization trust configured")
    print(f"  OK  {agent} hooks configured")
    print(f"  Check: {len(results)} skills found, {failed} need approval")
    print(f"  Mode: {policy['mode']}" + (" - tool calls are not blocked" if policy["mode"] != "enforce" else " - guards request denial for unapproved skills"))
    print("Next: restart your agent and confirm Skillseal appears in its hooks.")
    print("Host enforcement has not been tested. Hook timeouts can fail open.")
    return 0


def enable_enforcement(agent: str, yes: bool, cwd: Path) -> int:
    if policies.system_policy_path().exists():
        raise SetupError("Enforcement is managed by IT. Ask your administrator.")
    target = user_policy_path().expanduser().absolute()
    policy = load_policy(project=cwd)
    if str(target) not in [str(Path(p).absolute()) for p in policy.sources] or not policy.signers:
        raise SetupError("No user approval policy configured. Run team setup first.")
    # Planning is read-only and reuses the same host-specific hook writers.
    for path, planned in _hook_plan(agent, sys.executable if getattr(sys, "frozen", False) else
                                    (shutil.which("skillseal") or "skillseal")).items():
        if not path.is_file():
            raise SetupError(f"No {agent} hook configuration found. Run team setup first.")
        actual = path.read_bytes()
        changed = json.loads(actual) != json.loads(planned) if path.suffix == ".json" else actual != planned
        if changed:
            raise SetupError(f"{agent} hooks need updating. Rerun team setup before enabling enforcement.")
    results = [verify_skill(skill, policy, use_cache=False)
               for skill in discover([agent], cwd, policy.skill_roots)]
    if not results:
        raise SetupError("No skills discovered here. Open your project and retry before enabling enforcement.")
    failed = [result for result in results if not result.ok]
    if failed:
        raise SetupError(f"{len(failed)} skills still need approval. Run skillseal check --agent {agent}.")
    print(f"All {len(results)} discovered skills verify for {agent} in this project.")
    print("Enforce mode affects every configured guard using this policy, including other projects.")
    print("Confirm your agent actually loads its hooks; this check cannot prove host enforcement.")
    _confirm("Enable blocking for unapproved skills?", yes)
    raw = json.loads(target.read_text(encoding="utf-8"))
    raw["mode"] = "enforce"
    _apply({target: _json(raw)})
    print("Enforce mode enabled. Restart your agent and test its hook behavior.")
    return 0


def demo() -> int:
    with tempfile.TemporaryDirectory(prefix="skillseal-demo-") as directory:
        root = Path(directory) / "starter"
        shutil.copytree(starter_path(), root)
        policy = load_policy(explicit=root / "policy.json")
        greeting = root / "skills/friendly-greeting"
        checklist = root / "skills/writing-checklist"
        if not all(verify_skill(skill, policy, use_cache=False).ok for skill in (greeting, checklist)):
            raise SetupError("Bundled starter signatures failed verification. Reinstall an official package.")
        print("Skillseal demonstration\n\nPASS  Approved skills verified")
        with (greeting / "SKILL.md").open("a", encoding="utf-8") as file:
            file.write("\nHarmless test edit.\n")
        if verify_skill(greeting, policy, use_cache=False).ok:
            raise SetupError("Demo failed: modified content was accepted.")
        print("PASS  Modified skill rejected")
        (checklist / "skill.oms.sig").unlink()
        if verify_skill(checklist, policy, use_cache=False).ok:
            raise SetupError("Demo failed: unsigned content was accepted.")
        print("PASS  Unsigned skill rejected\n\nYour computer's trust settings were not changed.")
        print("This verifies signatures; it does not install hooks or test an agent host.")
    return 0


def _gh(args: list[str], project: Path, *, private: bytes | None = None) -> str:
    try:
        result = subprocess.run(["gh", *args], cwd=project, input=private,
                                capture_output=True, check=False, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise SetupError("GitHub request timed out. Check connectivity and whether the secret upload completed before retrying.") from exc
    if result.returncode:
        # Do not echo arbitrary subprocess output when it received key material.
        detail = "Secret upload failed. Check your repository permissions." if private else result.stderr.decode(errors="replace").strip()
        raise SetupError(f"GitHub setup failed: {detail}")
    return result.stdout.decode().strip()


def _workflow(branch: str) -> bytes:
    locations = sorted({root for roots in PROJECT_DIRS.values() for root in roots})
    filters = "\n".join(f"      - {json.dumps(root + '/**')}" for root in locations)
    patterns = "\n".join(f"            {root}/*" for root in locations)
    return (
        "name: Approve skills\non:\n  push:\n"
        f"    branches: [{json.dumps(branch)}]\n    paths:\n{filters}\n"
        '      - ".github/workflows/approve-skills.yml"\n  workflow_dispatch:\n'
        "permissions:\n  contents: write\n"
        "concurrency:\n  group: skillseal-approval-${{ github.ref }}\n  cancel-in-progress: false\n"
        f"jobs:\n  approve:\n    if: github.ref == 'refs/heads/{branch}'\n"
        "    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        f"      - uses: azurekid/skillseal@{ACTION_REF}\n"
        "        with:\n          signing-method: key\n"
        '          scan: "skillseal scan --fail-on HIGH {path}"\n'
        "          approval-private-key: ${{ secrets.SKILLSEAL_APPROVAL_PRIVATE_KEY }}\n"
        f"          skills: |\n{patterns}\n"
        "      - name: Commit signatures\n        env:\n          BRANCH: ${{ github.ref_name }}\n"
        "        run: |\n          set -euo pipefail\n"
        "          git config user.name 'skillseal[bot]'\n"
        "          git config user.email 'skillseal@users.noreply.github.com'\n"
        "          git add -- ':(glob)**/skill.oms.sig'\n"
        "          if git diff --cached --quiet; then exit 0; fi\n"
        "          git commit -m 'Sign approved skills'\n"
        '          git push origin "HEAD:refs/heads/$BRANCH"\n'
    ).encode()


def organization(project: Path, name: str | None, repository: str | None, branch: str,
                 upload: bool, yes: bool) -> int:
    project = project.resolve()
    if not (project / ".git").exists():
        raise SetupError("Open the root of your skills Git repository and retry. No files changed.")
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=project,
                          capture_output=True, text=True, check=False)
    if root.returncode or Path(root.stdout.strip()).resolve() != project:
        raise SetupError("This is not a Git repository root. Open your skills checkout and retry.")
    checked = subprocess.run(["git", "check-ref-format", "--branch", branch],
                             capture_output=True, check=False)
    if checked.returncode or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch):
        raise SetupError("Choose a valid Git signing branch, such as main.")
    if not shutil.which("gh") and upload:
        raise SetupError("Install GitHub CLI and run gh auth login first, or omit --upload-secret for offline preparation.")
    if not repository and shutil.which("gh"):
        repository = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], project)
    repository = _answer(repository, "GitHub signing repository (OWNER/REPO)")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise SetupError("Use a GitHub repository name such as contoso/approved-skills.")
    name = _answer(name, "Organization name", repository.split("/")[0])
    if not name.strip() or len(name) > 100 or not name.isprintable():
        raise SetupError("Use a short, printable organization name.")
    workflow = project / ".github/workflows/approve-skills.yml"
    bundle = project / "skillseal-team.zip"
    public = project / ".skillseal/approval.pub"
    skill = project / ".agents/skills/skillseal-welcome"
    for path in (workflow, bundle, public, skill):
        if path.exists() or path.is_symlink():
            raise SetupError(f"Setup already exists or would replace {path}. Nothing changed; keep the existing authority.")
    if upload:
        _gh(["auth", "status"], project)
        detected = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], project)
        if detected.casefold() != repository.casefold():
            raise SetupError(f"This checkout belongs to {detected}, not {repository}. Refusing to upload a key to another repository.")
        existing = json.loads(_gh(["secret", "list", "--repo", repository, "--json", "name"], project))
        if any(secret["name"] == "SKILLSEAL_APPROVAL_PRIVATE_KEY" for secret in existing):
            raise SetupError("The GitHub approval secret already exists. Refusing to replace your organization's authority.")
    print(f"Organization: {name}\nSigning repository: {repository}\nBranch: {branch}")
    print("Creates: reviewed signing workflow, signed welcome skill, public team package.")
    print("A private-key backup will be kept outside this repository. Protect it like a password.")
    if upload:
        print("Uploads the private key to the named repository secret after preparation.")
    _confirm("Prepare this repository and approval authority?", yes)
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    # Never place the private key in the checkout, even temporarily.
    authority = Path.home() / ".skillseal-authorities" / uuid.uuid4().hex
    if authority.resolve().is_relative_to(project):
        raise SetupError("Private-key backup would be inside the repository. Use a repository outside your home root.")
    authority.mkdir(parents=True, mode=0o700)
    private_path = authority / "approval-private.pem"
    _atomic(private_path, private)
    print(f"Private-key backup (do not share): {private_path}")
    try:
        with tempfile.TemporaryDirectory(prefix="skillseal-team-") as directory:
            temp = Path(directory)
            welcome = temp / "welcome"
            welcome.mkdir()
            shutil.copyfile(starter_path() / "skills/friendly-greeting/SKILL.md", welcome / "SKILL.md")
            sign_skill(welcome, method="key", private_key=private_path)
            fingerprint = hashlib.sha256(pub).hexdigest()
            team = {"format": "skillseal-team-v1", "organization": name, "key_sha256": fingerprint}
            archive = temp / "team.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
                output.writestr("team.json", _json(team))
                output.writestr("approval.pub", pub)
                output.writestr("policy.json", _json(approval_policy(name)))
            read_bundle(archive)
            (temp / "approval.pub").write_bytes(pub)
            (temp / "policy.json").write_bytes(_json(approval_policy(name)))
            if not verify_skill(welcome, load_policy(explicit=temp / "policy.json"), use_cache=False).ok:
                raise SetupError("The generated welcome signature did not verify; no repository files written.")
            _apply({
                workflow: _workflow(branch), bundle: archive.read_bytes(), public: pub,
                skill / "SKILL.md": (welcome / "SKILL.md").read_bytes(),
                skill / "skill.oms.sig": (welcome / "skill.oms.sig").read_bytes(),
            })
        if upload:
            _gh(["secret", "set", "SKILLSEAL_APPROVAL_PRIVATE_KEY", "--repo", repository], project, private=private)
    except (OSError, ValueError, SignError, KeyboardInterrupt):
        print(f"Preparation incomplete. Your key backup remains at {private_path}.", file=sys.stderr)
        print("If public files were written, keep them and upload this same backup; do not generate a replacement authority.",
              file=sys.stderr)
        print(f"GitHub: {repository} > Settings > Secrets and variables > Actions > "
              "New repository secret > SKILLSEAL_APPROVAL_PRIVATE_KEY.", file=sys.stderr)
        raise
    print(f"\nRepository prepared. Team package: {bundle}")
    print(f"Approval key SHA256: {fingerprint}")
    if not upload:
        print("Before signing in GitHub: add the private backup as repository secret SKILLSEAL_APPROVAL_PRIVATE_KEY.")
        if os.name == "nt":
            path = str(private_path).replace("'", "''")
            print(f"PowerShell: Get-Content -Raw -LiteralPath '{path}' | "
                  f"gh secret set SKILLSEAL_APPROVAL_PRIVATE_KEY --repo {repository}")
        else:
            print("Or upload with GitHub CLI: gh secret set SKILLSEAL_APPROVAL_PRIVATE_KEY --repo "
                  f"{repository} < {shlex.quote(str(private_path))}")
    print("Next: review and commit the generated public files, then push to the signing branch.")
    print("In GitHub Actions, confirm 'Approve skills' passes. Branch rules must allow its signature commits.")
    print("Send skillseal-team.zip through your trusted company channel; never send the private backup.")
    print("Developer command: skillseal setup --bundle skillseal-team.zip")
    print("The welcome skill uses .agents/skills. For Claude Code, copy its complete folder to .claude/skills.")
    return 0
