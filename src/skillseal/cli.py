"""skillseal command line."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import SKILL_FILE, __version__, cache
from .discover import AGENTS, discover
from .hooks import run_hook
from .install import install, uninstall
from .policy import GITHUB_ISSUER, MODES, Policy, PolicyError, load_policy, repo_policy_path, user_policy_path
from .scan import ScanError, scan_exceeds_threshold, scan_skill
from .sign import SignError, run_scanner, sign_skill
from .verify import Result, _walk, verify_skill


def _display_path(value: str) -> str:
    path = Path(value)
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _print_check(results: list[Result], policy: Policy, agents: list[str]) -> None:
    print(r"   .-------.")
    print(r"   |  S S  |   SKILLSEAL")
    print(r"   |   v   |   Skill signature check")
    print(r"    \     /")
    print(r"     '---'")
    print()
    print(f"  Mode     {policy.mode}")
    print(f"  Policy   {', '.join(_display_path(p) for p in policy.sources) or '(none)'}")
    print(f"  Signers  {len(policy.signers)} trusted")
    print(f"  Agents   {', '.join(agents)}")
    print()
    if not policy.signers:
        print("  WARNING: No trusted signers configured.")
        print("  Run skillseal init with your team's signer before using enforce mode.")
        print()
    failed = [r for r in results if not r.ok]
    verified = [r for r in results if r.ok]
    for title, group in (("NEEDS APPROVAL", failed), ("VERIFIED", verified)):
        if not group:
            continue
        print(f"  {title} ({len(group)})")
        print("  " + "-" * 60)
        for r in group:
            mark = "OK" if r.ok else "FAIL"
            print(f"  [{mark}] {_display_path(r.path)}")
            print(f"         {r.status}" + (f" | signer: {r.signer}" if r.signer else ""))
            for reason in r.reasons[:20]:
                print(f"         - {reason}")
            if len(r.reasons) > 20:
                print(f"         ... {len(r.reasons) - 20} more reasons (use --json to see all)")
        print()
    print(f"  Summary: {len(results)} skills | {len(verified)} verified | {len(failed)} not approved")
    if not results:
        print("  No skills found in the selected agents' skill folders.")
    elif failed:
        if policy.mode == "enforce":
            print("  Enforce mode: configured agent guards block tool use until these skills are approved.")
        else:
            print(f"  {policy.mode.capitalize()} mode: configured agent guards do not block these skills.")
        print("  Next: remove unapproved skills or ask your team lead to sign them.")
    else:
        print("  All discovered skills have a valid signature from a trusted signer.")
    print()


def _print_results(results, as_json: bool) -> None:
    if as_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        extra = f"  signer: {r.signer}" if r.ok else ""
        print(f"[{mark}] {r.path}  ({r.status}){extra}")
        for reason in r.reasons[:20]:
            print(f"       - {reason}")


def cmd_init(a) -> int:
    path = repo_policy_path(Path(a.project).resolve()) if a.scope == "repo" else user_policy_path()
    if path.exists() and not a.force:
        print(f"{path} exists; use --force to overwrite", file=sys.stderr)
        return 1
    signers = []
    if a.github_workflow:
        signers.append({
            "name": "approval workflow",
            "type": "sigstore",
            "identity": f"https://github.com/{a.github_workflow}",
            "issuer": GITHUB_ISSUER,
        })
    if a.identity:
        signers.append({"name": "sigstore identity", "type": "sigstore", "identity": a.identity, "issuer": a.issuer})
    if a.public_key:
        signers.append({"name": "public key", "type": "public_key", "public_key": str(Path(a.public_key).resolve())})
    if a.certificate_chain:
        signers.append({"name": "certificate", "type": "certificate", "certificate_chain": [str(Path(c).resolve()) for c in a.certificate_chain]})
    policy = {"mode": a.mode, "trusted_signers": signers}
    if a.scope == "user":
        policy["allow_repo_signers"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(signers)} trusted signer(s), mode {a.mode})")
    if not signers:
        print("warning: no trusted signers yet, so every skill will be blocked in enforce mode", file=sys.stderr)
    return 0


def cmd_sign(a) -> int:
    scanner = a.scan or os.environ.get("SKILLSEAL_SCANNER")
    failed = 0
    for d in a.dirs:
        skill = Path(d)
        try:
            if scanner:
                ok, out = run_scanner(scanner, skill)
                if not ok:
                    print(f"[BLOCKED] {skill}: scanner reported findings, not signing\n{out[-4000:]}", file=sys.stderr)
                    failed += 1
                    continue
            elif not a.no_scan:
                print("error: pass --scan CMD (or SKILLSEAL_SCANNER), or --no-scan to sign without a scan gate", file=sys.stderr)
                return 2
            sig = sign_skill(
                skill,
                method=a.method,
                private_key=Path(a.private_key) if a.private_key else None,
                signing_certificate=Path(a.signing_certificate) if a.signing_certificate else None,
                certificate_chain=[Path(c) for c in a.certificate_chain or []],
                identity_token=a.identity_token,
                use_staging=a.staging,
            )
            print(f"[SIGNED] {sig}")
        except SignError as exc:
            print(f"[ERROR] {skill}: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def cmd_scan(a) -> int:
    failed = False
    errors = False
    for directory in a.dirs:
        skill = Path(directory)
        try:
            findings = scan_skill(skill)
        except ScanError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            errors = True
            continue
        if not findings:
            print(f"[CLEAN] {skill}: no heuristic findings")
            continue
        for finding in findings:
            print(
                f"[{finding.severity}] {finding.path}:{finding.line}: "
                f"{finding.description}"
            )
        failed = failed or scan_exceeds_threshold(findings, a.fail_on)
    if errors:
        return 2
    return 1 if failed else 0


def cmd_verify(a) -> int:
    policy = load_policy(project=Path.cwd(), explicit=Path(a.policy) if a.policy else None)
    results = [verify_skill(Path(d), policy, use_cache=not a.no_cache) for d in a.dirs]
    _print_results(results, a.json)
    return 0 if all(r.ok for r in results) else 1


def cmd_digest(a) -> int:
    failed = False
    for directory in a.dirs:
        skill = Path(directory)
        try:
            if not (skill / SKILL_FILE).is_file() or (skill / SKILL_FILE).is_symlink():
                raise ValueError(f"no regular {SKILL_FILE} in {skill}")
            files, problems = _walk(skill)
            if problems:
                raise ValueError("; ".join(problems))
            print(f"{cache.skill_digest(skill, files)}  {skill}")
        except (OSError, ValueError) as exc:
            print(f"[ERROR] {skill}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


def cmd_check(a) -> int:
    cwd = Path(a.cwd).resolve()
    policy = load_policy(project=cwd, explicit=Path(a.policy) if a.policy else None)
    agents = a.agent or list(AGENTS)
    skills = discover(agents, cwd, policy.skill_roots)
    results = [verify_skill(s, policy, use_cache=not a.no_cache) for s in skills]
    if a.json:
        _print_results(results, True)
    else:
        _print_check(results, policy, agents)
    return 0 if all(r.ok for r in results) else 1


def cmd_hook(a) -> int:
    return run_hook(a.agent, a.event or "", sys.stdin.read())


def _default_exe() -> str:
    if getattr(sys, "frozen", False):  # standalone build: point hooks at this binary
        return sys.executable
    # Agents started from a desktop launcher often lack ~/.local/bin on PATH, so use an absolute path.
    found = shutil.which("skillseal")
    return os.path.abspath(found) if found else "skillseal"


def cmd_install(a) -> int:
    project = Path(a.project).resolve()
    exe = a.exe or _default_exe()
    if exe == "skillseal":
        print("warning: skillseal is not on PATH; hooks will call plain 'skillseal' (pass --exe /full/path)", file=sys.stderr)
    for agent in a.agents:
        paths, note = install(agent, a.scope, project, exe=exe)
        for p in paths:
            print(f"[{agent}] wrote {p}")
        if note:
            print(f"[{agent}] {note}")
    print(f"hooks call: {exe}")
    return 0


def cmd_uninstall(a) -> int:
    project = Path(a.project).resolve()
    for agent in a.agents:
        touched = uninstall(agent, a.scope, project)
        print(f"[{agent}] " + (", ".join(f"cleaned {p}" for p in touched) if touched else f"nothing installed ({a.scope} scope)"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillseal", description="Only run agent skills that were approved and signed.")
    p.add_argument("--version", action="version", version=f"skillseal {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a trust policy")
    s.add_argument("--scope", choices=["user", "repo"], default="user")
    s.add_argument("--project", default=".")
    s.add_argument("--mode", choices=MODES, default="enforce")
    s.add_argument("--github-workflow", metavar="OWNER/REPO/.github/workflows/FILE.yml@REF",
                   help="trust Sigstore signatures made by this GitHub Actions workflow")
    s.add_argument("--identity", help="trust this Sigstore certificate identity (needs --issuer)")
    s.add_argument("--issuer", default=GITHUB_ISSUER)
    s.add_argument("--public-key", help="trust an EC public key (PEM)")
    s.add_argument("--certificate-chain", nargs="+", help="trust a certificate chain, for example nv-agent-root-cert.pem")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("sign", help="scan, then sign skill folders (writes skill.oms.sig)")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--scan", help="scanner command; exit 0 = clean. {path} is replaced by the skill folder")
    s.add_argument("--no-scan", action="store_true", help="sign without a scan gate")
    s.add_argument("--method", choices=["sigstore", "key", "certificate"], default="sigstore")
    s.add_argument("--private-key")
    s.add_argument("--signing-certificate")
    s.add_argument("--certificate-chain", nargs="+")
    s.add_argument("--identity-token", help="explicit OIDC token for Sigstore")
    s.add_argument("--staging", action="store_true", help="use Sigstore staging (testing only)")
    s.set_defaults(func=cmd_sign)

    s = sub.add_parser("scan", help="heuristically scan skill folders for common risky content")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--fail-on", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM",
                   help="exit 1 when a finding at or above this severity is found (default: MEDIUM)")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("verify", help="verify skill folders against the policy")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--policy")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("digest", help="print portable skill content digests for policy revocation")
    s.add_argument("dirs", nargs="+")
    s.set_defaults(func=cmd_digest)

    s = sub.add_parser("check", help="find every skill your agents can load and verify it")
    s.add_argument("--agent", action="append", choices=AGENTS)
    s.add_argument("--cwd", default=".")
    s.add_argument("--policy")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("hook", help="hook entry point (reads the agent's JSON on stdin)")
    s.add_argument("agent", choices=AGENTS)
    s.add_argument("event", nargs="?")
    s.set_defaults(func=cmd_hook)

    s = sub.add_parser("install", help="register skillseal hooks in agent configs")
    s.add_argument("agents", nargs="+", choices=AGENTS)
    s.add_argument("--scope", choices=["project", "user"], default="project")
    s.add_argument("--project", default=".")
    s.add_argument("--exe", help="command used inside hooks (default: absolute path of skillseal on PATH)")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("uninstall", help="remove skillseal hooks from agent configs")
    s.add_argument("agents", nargs="+", choices=AGENTS)
    s.add_argument("--scope", choices=["project", "user"], default="project")
    s.add_argument("--project", default=".")
    s.set_defaults(func=cmd_uninstall)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PolicyError as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        return 2
    except ScanError as exc:
        print(f"scan error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
