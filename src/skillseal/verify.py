"""Verify a skill folder against the trust policy.

Signature format: OpenSSF Model Signing (OMS), a Sigstore bundle with a DSSE
envelope whose in-toto predicate lists every file and its digest. The format
and the cryptographic checks come from the `model-signing` library; skillseal
adds the stricter rules an agent skill needs:

* the signed manifest must use per-file serialization without symlinks;
* nothing may exist on disk under a path the signature chose to ignore
  (OMS ignores .github/, .gitignore and .gitattributes by default), except
  the signature file itself and a .git/ directory;
* the folder must contain SKILL.md and stay under a size cap so a hook can
  not be stalled.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import SIGNATURE_FILE, SKILL_FILE, cache
from .policy import Policy, Signer

MAX_FILES = 2000
MAX_BYTES = 64 * 1024 * 1024
ALLOWED_HASHES = {"sha256", "blake2", "blake3"}
ALWAYS_IGNORED = {SIGNATURE_FILE, ".git"}

VERIFIED = "verified"
UNSIGNED = "unsigned"
INVALID = "invalid"


@dataclass
class Result:
    path: str
    status: str
    signer: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == VERIFIED

    def to_dict(self) -> dict:
        return {"path": self.path, "status": self.status, "signer": self.signer, "reasons": self.reasons}


def _predicate(sig_path: Path) -> dict:
    """Read the (not yet authenticated) OMS predicate for pre-checks."""
    bundle = json.loads(sig_path.read_text(encoding="utf-8"))
    payload = bundle["dsseEnvelope"]["payload"]
    statement = json.loads(base64.b64decode(payload))
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("signature has no predicate")
    return predicate


def _walk(root: Path) -> tuple[list[str], list[str]]:
    """Return (relative file paths, problems) without following symlinks."""
    files: list[str] = []
    problems: list[str] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir.parts[:1] == (".git",):
            dirnames[:] = []
            continue
        for name in list(dirnames):
            p = Path(dirpath) / name
            if p.is_symlink():
                problems.append(f"symlink not allowed: {(rel_dir / name).as_posix()}")
                dirnames.remove(name)
        for name in filenames:
            p = Path(dirpath) / name
            rel = (rel_dir / name).as_posix()
            if p.is_symlink():
                problems.append(f"symlink not allowed: {rel}")
                continue
            if not p.is_file():
                problems.append(f"not a regular file: {rel}")
                continue
            files.append(rel)
            total += p.stat().st_size
            if len(files) > MAX_FILES or total > MAX_BYTES:
                problems.append(f"skill folder exceeds {MAX_FILES} files or {MAX_BYTES} bytes")
                return files, problems
    return files, problems


def _under(rel: str, prefix: str) -> bool:
    # Case-insensitive on purpose: Windows (and default macOS) paths match that way.
    rel, prefix = rel.casefold(), prefix.strip("/").casefold()
    return rel == prefix or rel.startswith(prefix + "/")


def _bad_ignore_path(p: str) -> bool:
    parts = p.strip("/").split("/")
    return not p.strip("/") or "\\" in p or ":" in p or p.startswith("/") or any(x in ("", ".", "..") for x in parts)


def _verify_hashing_config(ser: dict):
    """Hash exactly what the signer declared, nothing more is skipped.

    model_signing's own guessed config starts from hashing.Config(), which always
    skips .github/, .gitignore and .gitattributes, even when the signer hashed them.
    """
    import model_signing

    ignored = {str(p).strip("/") for p in ser.get("ignore_paths", [])} | ALWAYS_IGNORED
    return (
        model_signing.hashing.Config()
        .use_file_serialization(hashing_algorithm=ser["hash_type"], allow_symlinks=False)
        .set_ignored_paths(paths=sorted(ignored), ignore_git_paths=False)
    )


def _crypto_verify(skill: Path, sig: Path, signer: Signer, ser: dict) -> None:
    import model_signing

    cfg = model_signing.verifying.Config()
    if signer.type == "sigstore":
        cfg.use_sigstore_verifier(identity=signer.identity, oidc_issuer=signer.issuer)
    elif signer.type == "certificate":
        cfg.use_certificate_verifier(certificate_chain=list(signer.certificate_chain))
    else:
        cfg.use_elliptic_key_verifier(public_key=signer.public_key)
    cfg.set_hashing_config(_verify_hashing_config(ser))
    cfg.set_ignore_unsigned_files(False)
    cfg.verify(skill, sig)


def _short_error(exc: Exception) -> str:
    text = str(exc)
    changed = re.findall(r"Hash mismatch for \\?'([^'\\]+)\\?'", text)
    extra = re.search(r"Extra files found in model \\?'[^']*\\?': ([^\"'\\]+)", text)
    missing = re.search(r"Missing files in model \\?'[^']*\\?': ([^\"'\\]+)", text)
    parts = []
    if changed:
        parts.append("changed: " + ", ".join(changed))
    if extra:
        parts.append("added: " + extra.group(1))
    if missing:
        parts.append("removed: " + missing.group(1))
    return "; ".join(parts) if parts else text.splitlines()[0][:300]


def verify_skill(skill_dir: Path, policy: Policy, use_cache: bool = True) -> Result:
    shown = str(skill_dir)
    try:
        real = skill_dir.resolve(strict=True)
    except OSError as exc:
        return Result(shown, INVALID, reasons=[f"cannot resolve: {exc}"])
    if not (real / SKILL_FILE).is_file():
        return Result(shown, INVALID, reasons=[f"no {SKILL_FILE} in folder"])
    if (real / SKILL_FILE).is_symlink():
        return Result(shown, INVALID, reasons=[f"{SKILL_FILE} is a symlink"])

    sig = real / SIGNATURE_FILE
    if sig.is_symlink() or not sig.is_file():
        return Result(shown, UNSIGNED, reasons=[f"no {SIGNATURE_FILE}"])

    files, problems = _walk(real)
    if problems:
        return Result(shown, INVALID, reasons=problems)

    try:
        pred = _predicate(sig)
        ser = pred.get("serialization", {})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return Result(shown, INVALID, reasons=[f"unreadable signature: {exc}"])
    if ser.get("method") != "files":
        return Result(shown, INVALID, reasons=[f"serialization method must be 'files', got {ser.get('method')!r}"])
    if ser.get("allow_symlinks") is not False:
        return Result(shown, INVALID, reasons=["signature allows symlinks"])
    if ser.get("hash_type") not in ALLOWED_HASHES:
        return Result(shown, INVALID, reasons=[f"hash type {ser.get('hash_type')!r} not allowed"])

    raw_ignored = [str(p) for p in ser.get("ignore_paths", [])]
    bad = [p for p in raw_ignored if _bad_ignore_path(p)]
    if bad:
        return Result(shown, INVALID, reasons=[f"signature has an unsafe ignore path: {p!r}" for p in bad])
    ignored = [p for p in raw_ignored if p.strip("/") not in ALWAYS_IGNORED]
    hidden = sorted(f for f in files if any(_under(f, ig) for ig in ignored))
    if hidden:
        return Result(shown, INVALID, reasons=[f"file not covered by signature (ignored path): {h}" for h in hidden])

    if not policy.signers:
        return Result(shown, INVALID, reasons=["no trusted signers configured (run: skillseal init)"])

    key = None
    if use_cache:
        try:
            key = cache.content_key(real, files, sig, policy.fingerprint())
            hit = cache.get(key)
        except OSError:
            hit = None
        if hit and any(s.name == hit for s in policy.signers):
            return Result(shown, VERIFIED, signer=hit)

    errors: list[str] = []
    for signer in policy.signers:
        try:
            _crypto_verify(real, sig, signer, ser)
        except Exception as exc:  # noqa: BLE001 - every failure means "not this signer"
            errors.append(f"{signer.name}: {_short_error(exc)}")
            continue
        if key:
            cache.put(key, signer.name)
        return Result(shown, VERIFIED, signer=signer.name)
    return Result(shown, INVALID, reasons=errors)
