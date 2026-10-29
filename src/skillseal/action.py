"""GitHub Action runner. Keep signing credentials out of scanner subprocesses."""

from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import SKILL_FILE
from .policy import GITHUB_ISSUER, Policy, Signer
from .sign import SignError, run_scanner
from .verify import verify_skill

_CREDENTIALS = ("APPROVAL_PRIVATE_KEY", "APPROVAL_CERTIFICATE", "APPROVAL_CERTIFICATE_CHAIN")


def _write(root: Path, name: str, value: str) -> Path:
    if not value.strip():
        raise ValueError(f"missing {name}")
    path = root / name
    with path.open("x", encoding="utf-8") as file:
        file.write(value)
    path.chmod(0o600)
    return path


def run() -> int:
    credentials = {name: os.environ.pop(name, "") for name in _CREDENTIALS}
    os.environ.pop("SKILLSEAL_SCANNER", None)
    method = os.environ.get("SIGNING_METHOD", "sigstore")
    if method not in ("sigstore", "key", "certificate"):
        raise ValueError("signing-method must be sigstore, key, or certificate")
    scan = os.environ.get("SCAN", "")
    if not scan and os.environ.get("ALLOW_NO_SCAN") != "true":
        raise ValueError("set scan or explicitly set allow-no-scan: true")
    skills = sorted({
        path for pattern in os.environ.get("SKILLS", "").split()
        for path in glob.glob(pattern) if (Path(path) / SKILL_FILE).is_file()
    })
    if not skills:
        raise ValueError("no skill folders matched skills")

    # Scan before writing any private key to disk. Scanners receive no PEM inputs.
    for skill in skills:
        if scan:
            ok, output = run_scanner(scan, Path(skill))
            if not ok:
                print(f"::error::Scanner blocked {skill}\n{output[-4000:]}", file=sys.stderr)
                return 1

    with tempfile.TemporaryDirectory(prefix="skillseal-sign-", dir=os.environ.get("RUNNER_TEMP")) as temp:
        root = Path(temp)
        args = ["--method", method]
        if method == "sigstore":
            if any(credentials.values()):
                raise ValueError("approval credentials supplied with sigstore; select key or certificate")
            from sigstore.oidc import detect_credential

            token = detect_credential()
            if not token:
                raise ValueError("Sigstore requires permissions: id-token: write")
            payload = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            identity = "https://github.com/" + claims["job_workflow_ref"]
            caller = "https://github.com/" + os.environ["GITHUB_WORKFLOW_REF"]
            signer = Signer("self", "sigstore", identity=identity, issuer=GITHUB_ISSUER, github_workflow=caller)
            print(f"Signing identity: {identity}\nCaller workflow: {caller}")
        else:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            private = _write(root, "approval-private-key.pem", credentials["APPROVAL_PRIVATE_KEY"])
            key = serialization.load_pem_private_key(private.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise ValueError("approval-private-key must be an unencrypted EC PEM private key")
            args += ["--private-key", str(private)]
            if method == "key":
                if credentials["APPROVAL_CERTIFICATE"] or credentials["APPROVAL_CERTIFICATE_CHAIN"]:
                    raise ValueError("certificate material supplied with key; select certificate")
                public = root / "approval.pub"
                public.write_bytes(key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
                ))
                signer = Signer("organization", "public_key", public_key=str(public))
            else:
                cert = _write(root, "approval-certificate.pem", credentials["APPROVAL_CERTIFICATE"])
                chain = _write(root, "approval-chain.pem", credentials["APPROVAL_CERTIFICATE_CHAIN"])
                from cryptography import x509

                leaf = x509.load_pem_x509_certificate(cert.read_bytes())
                if leaf.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
                ) != key.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
                ):
                    raise ValueError("approval certificate does not match approval private key")
                args += ["--signing-certificate", str(cert), "--certificate-chain", str(chain)]
                signer = Signer("organization", "certificate", certificate_chain=(str(chain),))

        credentials.clear()
        policy = Policy(signers=[signer])
        signed = []
        for skill in skills:
            path = Path(skill)
            if os.environ.get("ONLY_CHANGED", "true") == "true" and verify_skill(path, policy, use_cache=False).ok:
                print(f"unchanged: {skill}")
                continue
            # Scan already passed; no scanner is run while private material exists.
            command = [sys.executable, "-m", "skillseal", "sign", "--no-scan", *args, "--", skill]
            subprocess.run(command, check=True)
            result = verify_skill(path, policy, use_cache=False)
            if not result.ok:
                raise ValueError(f"new signature failed verification for {skill}: {result.reasons}")
            signed.append(skill)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as file:
                file.write("signed=" + " ".join(signed) + "\n")
        print(f"Signed {len(signed)} skill(s) using {method}")
    return 0


def main() -> int:
    try:
        return run()
    except (ValueError, KeyError, OSError, SignError, subprocess.CalledProcessError) as exc:
        print(f"::error::Approval failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
