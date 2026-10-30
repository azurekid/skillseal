"""Approval: run the scan gate, then sign the exact folder with OMS."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from . import SIGNATURE_FILE, SKILL_FILE
from .verify import _walk


class SignError(RuntimeError):
    pass


def remove_signature(skill_dir: Path) -> bool:
    sig = skill_dir / SIGNATURE_FILE
    try:
        sig.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SignError(f"cannot remove {sig}: {exc}") from exc
    print(f"[REMOVED] {sig}")
    return True


def run_scanner(command: str, skill_dir: Path, timeout: int = 300) -> tuple[bool, str]:
    """Run a pluggable scanner. `{path}` in the command is replaced by the folder.

    Exit code 0 means clean; anything else blocks signing.
    """
    try:
        if os.name == "nt":
            argv = [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a for a in shlex.split(command, posix=False)]
        else:
            argv = shlex.split(command)
    except ValueError as exc:
        raise SignError(f"invalid scanner command: {exc}") from exc
    if not argv:
        raise SignError("empty scanner command")
    if any("{path}" in a for a in argv):
        argv = [a.replace("{path}", str(skill_dir)) for a in argv]
    else:
        argv.append(str(skill_dir))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise SignError(f"scanner not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SignError(f"scanner timed out after {timeout}s") from exc
    except OSError as exc:
        raise SignError(f"cannot run scanner {argv[0]}: {exc}") from exc
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def _hashing_config():
    import model_signing

    # Hash .github/, .gitignore and .gitattributes too: OMS skips them by default.
    return model_signing.hashing.Config().set_ignored_paths(
        paths=[SIGNATURE_FILE], ignore_git_paths=False
    ).set_allow_symlinks(False)


def sign_skill(
    skill_dir: Path,
    *,
    method: str = "sigstore",
    private_key: Path | None = None,
    signing_certificate: Path | None = None,
    certificate_chain: list[Path] | None = None,
    identity_token: str | None = None,
    use_staging: bool = False,
) -> Path:
    import model_signing

    skill_dir = skill_dir.resolve()
    if not (skill_dir / SKILL_FILE).is_file():
        raise SignError(f"{skill_dir} has no {SKILL_FILE}")
    _, problems = _walk(skill_dir)
    if problems:
        raise SignError("; ".join(problems))

    cfg = model_signing.signing.Config().set_hashing_config(_hashing_config())
    if method == "sigstore":
        cfg.use_sigstore_signer(
            use_ambient_credentials=identity_token is None,
            identity_token=identity_token,
            use_staging=use_staging,
        )
    elif method == "key":
        if not private_key:
            raise SignError("--private-key is required for method 'key'")
        cfg.use_elliptic_key_signer(private_key=private_key)
    elif method == "certificate":
        if not (private_key and signing_certificate and certificate_chain):
            raise SignError("method 'certificate' needs --private-key, --signing-certificate and --certificate-chain")
        cfg.use_certificate_signer(
            private_key=private_key,
            signing_certificate=signing_certificate,
            certificate_chain=certificate_chain,
        )
    else:
        raise SignError(f"unknown signing method {method!r}")

    sig = skill_dir / SIGNATURE_FILE
    if sig.is_symlink():
        raise SignError(f"{SIGNATURE_FILE} is a symlink")
    cfg.sign(skill_dir, sig)
    return sig
