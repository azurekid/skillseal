"""skillseal command line."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .discover import AGENTS, discover
from .hooks import run_hook
from .install import install, uninstall
from .policy import GITHUB_ISSUER, MODES, PolicyError, load_policy, repo_policy_path, user_policy_path
from .sign import SignError, run_scanner, sign_skill
from .verify import verify_skill


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


def cmd_verify(a) -> int:
    policy = load_policy(project=Path.cwd(), explicit=Path(a.policy) if a.policy else None)
    results = [verify_skill(Path(d), policy, use_cache=not a.no_cache) for d in a.dirs]
    _print_results(results, a.json)
    return 0 if all(r.ok for r in results) else 1


def cmd_check(a) -> int:
    cwd = Path(a.cwd).resolve()
    policy = load_policy(project=cwd, explicit=Path(a.policy) if a.policy else None)
    agents = a.agent or list(AGENTS)
    skills = discover(agents, cwd, policy.skill_roots)
    results = [verify_skill(s, policy, use_cache=not a.no_cache) for s in skills]
    if not a.json:
        print(f"policy: {', '.join(policy.sources) or '(none)'}  mode: {policy.mode}  signers: {len(policy.signers)}")
        print(f"agents: {', '.join(agents)}  skills found: {len(results)}")
    _print_results(results, a.json)
    return 0 if all(r.ok for r in results) else 1


def cmd_hook(a) -> int:
    return run_hook(a.agent, a.event or "", sys.stdin.read())


def _default_exe() -> str:
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

    s = sub.add_parser("verify", help="verify skill folders against the policy")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--policy")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_verify)

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


if __name__ == "__main__":
    sys.exit(main())
