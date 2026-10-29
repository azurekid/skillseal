"""Offline trust and revocation lab. Run with the Python that has skillseal installed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _key(root: Path, name: str):
    key = ec.generate_private_key(ec.SECP256R1())
    private = root / f"{name}.pem"
    public = root / f"{name}.pub"
    private.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    private.chmod(0o600)
    public.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return key, private, public


def _external_certificate(root: Path) -> tuple[Path, Path, Path]:
    ca_key, _, _ = _key(root, "lab-ca")
    leaf_key, leaf_private, _ = _key(root, "external")
    now = datetime.now(timezone.utc)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Skillseal lab CA - not for production")])
    ca = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "External lab publisher")]))
        .issuer_name(ca_name).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=12))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_path, leaf_path = root / "external-ca.pem", root / "external-cert.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    leaf_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    return leaf_private, leaf_path, ca_path


def run_lab(root: Path) -> None:
    env = {
        **os.environ,
        "HOME": str(root), "USERPROFILE": str(root),
        "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"),
    }
    env.pop("SKILLSEAL_SCANNER", None)
    env.pop("SKILLSEAL_POLICY", None)

    def cli(*args: str, expected: int = 0) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "skillseal", *args], env=env,
            capture_output=True, text=True, check=False,
        )
        if result.returncode != expected:
            raise RuntimeError(
                f"{args}: expected exit {expected}, got {result.returncode}\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result.stdout

    def verify(skill: Path, policy: Path, status: str) -> None:
        output = cli("verify", "--json", "--policy", str(policy), str(skill),
                     expected=0 if status == "verified" else 1)
        result = json.loads(output)[0]
        if result["status"] != status:
            raise RuntimeError(f"expected {status}, got {result}")

    _, internal_private, internal_public = _key(root, "internal")
    external_private, external_cert, external_ca = _external_certificate(root)
    project = root / "project"
    (project / ".git").mkdir(parents=True)
    skills = project / ".github/skills"
    internal, external = skills / "internal", skills / "external"
    for skill in (internal, external):
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {skill.name}\ndescription: harmless lab skill\n---\nSay hello.\n", encoding="utf-8",
        )
    internal_signer = {"name": "internal", "type": "public_key", "public_key": str(internal_public)}
    external_signer = {"name": "external", "type": "certificate", "certificate_chain": [str(external_ca)]}
    policy_path = root / "policy.json"

    def policy(signers: list[dict], revoked: dict[str, str] | None = None) -> None:
        policy_path.write_text(json.dumps({
            "mode": "enforce", "allow_repo_signers": False,
            "trusted_signers": signers, "revoked_skills": revoked or {},
        }), encoding="utf-8")

    policy([internal_signer])
    verify(internal, policy_path, "unsigned")
    cli("sign", "--no-scan", "--method", "key", "--private-key", str(internal_private), str(internal))
    cli("sign", "--no-scan", "--method", "certificate", "--private-key", str(external_private),
        "--signing-certificate", str(external_cert), "--certificate-chain", str(external_ca), "--", str(external))
    verify(internal, policy_path, "verified")
    verify(external, policy_path, "invalid")
    print("PASS: internal signer accepted; valid but unconfigured external signer rejected")

    policy([internal_signer, external_signer])
    verify(external, policy_path, "verified")
    cli("check", "--json", "--agent", "copilot", "--cwd", str(project), "--policy", str(policy_path))
    print("PASS: explicitly trusted external certificate accepted; Copilot skill discovery passes")

    ca_bytes = external_ca.read_bytes()
    replacement_dir = root / "replacement-ca"
    replacement_dir.mkdir()
    _, _, replacement_ca = _external_certificate(replacement_dir)
    external_ca.write_bytes(replacement_ca.read_bytes())
    verify(external, policy_path, "invalid")
    external_ca.write_bytes(ca_bytes)
    verify(external, policy_path, "verified")
    print("PASS: replacing the configured CA file invalidates its cached approval")

    original = (external / "SKILL.md").read_bytes()
    (external / "SKILL.md").write_bytes(original + b"\nA harmless test edit.\n")
    verify(external, policy_path, "invalid")
    (external / "SKILL.md").write_bytes(original)
    verify(external, policy_path, "verified")
    print("PASS: changed signed content rejected")

    digest = cli("digest", str(external)).split()[0]
    policy([internal_signer, external_signer], {digest: "LAB-001: withdrawn external release"})
    verify(external, policy_path, "revoked")
    cli("sign", "--no-scan", "--method", "certificate", "--private-key", str(external_private),
        "--signing-certificate", str(external_cert), "--certificate-chain", str(external_ca), "--", str(external))
    verify(external, policy_path, "revoked")
    cli("check", "--agent", "copilot", "--cwd", str(project), "--policy", str(policy_path), expected=1)
    verify(internal, policy_path, "verified")
    print("PASS: cached external approval revoked; re-signing cannot bypass content revocation")

    policy([internal_signer])
    verify(external, policy_path, "invalid")
    verify(internal, policy_path, "verified")
    print("PASS: publisher trust removed while internal skills remain usable")

    policy([internal_signer, external_signer], {digest: "LAB-001: keep old release revoked"})
    (external / "SKILL.md").write_bytes(original + b"\nReviewed replacement release.\n")
    cli("sign", "--no-scan", "--method", "certificate", "--private-key", str(external_private),
        "--signing-certificate", str(external_cert), "--certificate-chain", str(external_ca), "--", str(external))
    verify(external, policy_path, "verified")
    print("PASS: reviewed replacement accepted; old content remains revoked")
    print("LAB PASSED (offline verifier/check lab; no running Copilot host or hooks were installed)")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="skillseal-trust-lab-") as directory:
        run_lab(Path(directory))
