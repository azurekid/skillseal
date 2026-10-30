"""Terminal menu for common Skillseal workflows."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

from . import __version__, policy as policies
from .cli import _default_exe, _print_result, main
from .discover import project_chain
from .scan import ScanError, scan_exceeds_threshold, scan_skill
from .setup import SETUP_AGENTS, SetupError, _answer, _apply, _confirm, _hook_plan, _json, approval_policy
from .sign import SignError, remove_signature, sign_skill
from .verify import verify_skill


def _choose(title: str, choices: tuple[str, ...]) -> int:
    print(f"\n{title}")
    for number, label in enumerate(choices, 1):
        print(f"  {number}. {label}")
    print("  0. Back / exit")
    while True:
        answer = input("Choose a number: ").strip()
        if answer == "0":
            return 0
        if answer.isascii() and answer.isdecimal() and 1 <= int(answer) <= len(choices):
            return int(answer)
        print(f"Enter a number from 0 to {len(choices)}.")


def _path(question: str, default: str = "") -> Path:
    answer = _answer(None, question, default).strip()
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in "\"'":
        answer = answer[1:-1]
    if not answer:
        raise SetupError("No path supplied. Nothing changed.")
    return Path(answer).expanduser().resolve()


def _agent() -> str | None:
    selected = _choose("Which agent?", SETUP_AGENTS)
    return SETUP_AGENTS[selected - 1] if selected else None


def _project() -> Path:
    path = _path("Project folder", str(Path.cwd()))
    if not path.is_dir():
        raise SetupError(f"Project folder does not exist: {path}")
    return path


def _personal_key(project: Path, skill: Path | None = None) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    effective = policies.load_policy(project=project)
    if effective.require_ca_issued:
        raise SetupError("CA-issued certificates or Sigstore are required. A personal raw key cannot be used.")
    if policies.system_policy_path().exists():
        raise SetupError("This machine has a managed system policy. Ask its administrator to authorize a signer.")
    target = policies.user_policy_path().expanduser().absolute()
    raw = json.loads(target.read_text(encoding="utf-8")) if target.exists() else approval_policy("Personal local key")
    authority = Path.home() / ".skillseal-authorities" / uuid.uuid4().hex
    if authority.resolve().is_relative_to(project_chain(project)[-1]) or (
        skill is not None and authority.resolve().is_relative_to(skill)
    ):
        raise SetupError("The private key must stay outside the project. Choose a project below, not containing, your home folder.")
    private_path, public_path = authority / "approval-private.pem", authority / "approval.pub"
    print(f"\nPrivate key (never share or commit): {private_path}")
    print(f"Public key: {public_path}")
    print(f"Adds a personal signer to: {target}")
    print(f"Policy mode stays {raw.get('mode', 'enforce')}; existing signers and revocations are preserved.")
    print("This key can approve skills on this machine. Protect its folder with your account's access controls.")
    _confirm("Create and trust this personal signing key?", False)
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = {"name": "Personal local key", "type": "public_key", "public_key": str(public_path)}
    if target.exists():
        raw.setdefault("trusted_signers", []).append(signer)
    else:
        raw["trusted_signers"] = [signer]
    authority.mkdir(parents=True, mode=0o700)
    _apply({
        private_path: key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ),
        public_path: public,
        target: _json(raw),
    })
    print(f"Personal key saved: {private_path}")
    print(f"Public-key SHA256: {hashlib.sha256(public).hexdigest()}")
    return private_path


def _protect() -> int:
    choice = _choose("Set up protection", (
        "Use an existing team/setup ZIP",
        "Install hooks using my existing trust policy",
        "Create a personal local signing key and install hooks",
        "Prepare a GitHub signing repository",
    ))
    if not choice:
        return 0
    if choice == 4:
        return main(["setup", "organization", "--project", str(_project())])
    agent = _agent()
    if not agent:
        return 0
    project = _project()
    if choice == 1:
        bundle = _path("Path to your trusted setup ZIP")
        return main(["setup", "--agent", agent, "--project", str(project), "--bundle", str(bundle)])
    exe = _default_exe()
    if exe == "skillseal":
        raise SetupError("Skillseal is not on PATH. Open a new terminal after installation, then retry.")
    if choice == 3:
        _personal_key(project)
    else:
        policy = policies.load_policy(project=project)
        if not policy.signers:
            raise SetupError("No trusted signers configured. Use a setup ZIP or create a personal signing key first.")
    print(f"Install user-wide {agent} hooks; existing unrelated settings will be preserved.")
    _confirm("Install these hooks?", False)
    _apply(_hook_plan(agent, exe))
    print("Hooks installed. Restart your agent, check skills, then enable enforcement when ready.")
    return 0


def _sign_local() -> int:
    project = _project()
    policy = policies.load_policy(project=project)
    skill = _path("Skill folder containing SKILL.md")
    print("A rejected or failed scan removes any existing approval signature.")
    _confirm("Scan this skill before approval?", False)
    print("Scanning locally. No files are uploaded or skill scripts executed.")
    try:
        findings = scan_skill(skill)
    except ScanError:
        remove_signature(skill)
        raise
    for finding in findings:
        print(f"[{finding.severity}] {finding.path}:{finding.line}: {finding.description}")
    if scan_exceeds_threshold(findings, "HIGH"):
        remove_signature(skill)
        raise SetupError("Scan found HIGH/CRITICAL findings. Existing approval removed; review before signing.")
    print("No HIGH/CRITICAL findings. This heuristic scan is not a safety guarantee.")
    choice = _choose("Local signing method", (
        "Use an existing private key",
        "Use an existing CA-issued certificate and private key",
        "Create and trust a personal local key",
        "Use Sigstore (online identity login / transparency log)",
    ))
    if not choice:
        return 0
    if choice in (1, 3) and policy.require_ca_issued:
        raise SetupError("Policy requires CA-issued certificates or Sigstore. Raw-key signing is not offered under this policy.")
    method = {1: "key", 2: "certificate", 3: "key", 4: "sigstore"}[choice]
    private = certificate = None
    chain = None
    if choice in (1, 2):
        private = _path("Private-key PEM path (not its contents)")
        if private.is_relative_to(project_chain(project)[-1]) or private.is_relative_to(skill):
            raise SetupError("Move the private key outside the project and skill folder before signing.")
    if choice == 2:
        certificate = _path("Signing certificate PEM path")
        chain = [_path("CA chain PEM bundle path")]
    print(f"\nApprove the entire folder: {skill}")
    print("Signing replaces its existing approval signature. It does not make unsafe instructions safe.")
    if choice == 4:
        print("Sigstore requires online authentication and publishes signing metadata to a transparency log.")
    _confirm("Have you reviewed these files and want to sign them?", False)
    if choice == 3:
        private = _personal_key(project, skill)
        policy = policies.load_policy(project=project)
    signature = sign_skill(skill, method=method, private_key=private,
                           signing_certificate=certificate, certificate_chain=chain)
    print(f"Signed: {signature}")
    result = verify_skill(skill, policy, use_cache=False)
    _print_result(result)
    if not result.ok:
        print("Signed, but NOT approved by your current policy. No signer was automatically trusted.", file=sys.stderr)
        return 1
    print("Signature verified against your current policy.")
    return 0


def run_menu() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("The menu needs an interactive terminal. Use skillseal --help for scriptable commands.", file=sys.stderr)
        return 2
    print(f"Skillseal {__version__}")
    print("Check approvals, protect your agent, and sign reviewed skills.")
    print("No changes are made without confirmation. Ctrl+C exits.")
    while True:
        choice = _choose("What would you like to do?", (
            "Check my skills and trust policy",
            "Set up protection",
            "Scan and sign a local skill",
            "Enable enforcement",
            "Try the safe demonstration",
            "Help / command reference",
        ))
        if not choice:
            return 0
        try:
            if choice in (1, 4):
                agent = _agent()
                if not agent:
                    continue
                project = _project()
                if choice == 1:
                    result = main(["check", "--agent", agent, "--cwd", str(project)])
                else:
                    result = main(["setup", "enforce", "--agent", agent, "--project", str(project)])
            elif choice == 2:
                result = _protect()
            elif choice == 3:
                result = _sign_local()
            elif choice == 5:
                result = main(["demo"])
            else:
                from .cli import build_parser

                build_parser().print_help()
                print("\nLocal signing covers whole skill folders, not arbitrary individual files.")
                print("Verification before startup: skillseal run --agent copilot -- copilot")
                print("Hooks are defense in depth, not a sandbox. A signature is approval, not proof of safety.")
                result = 0
            if result:
                print("Action did not complete successfully. See the details above; no success is assumed.", file=sys.stderr)
        except (OSError, ValueError, SignError, ScanError) as exc:
            print(f"Action could not finish: {exc}", file=sys.stderr)
