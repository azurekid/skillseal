"""Trust policy: which signers are trusted and how strictly to enforce.

Policy layers, highest authority first:
  1. system   /etc/skillseal/policy.json (Linux/macOS) or %ProgramData%\\skillseal\\policy.json
  2. user     $SKILLSEAL_POLICY, or ~/.config/skillseal/policy.json
  3. repo     <project>/.skillseal/policy.json

When a system or user policy exists it is authoritative. A repository policy is
then only merged in when that policy sets "allow_repo_signers": true, so a
cloned repository can never make your machine trust its own signing key.
Without either, repository roots may be discovered but no signer is trusted.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MODES = ("enforce", "warn", "audit")
SIGNER_TYPES = ("sigstore", "certificate", "public_key")
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Signer:
    name: str
    type: str
    identity: str = ""
    issuer: str = ""
    certificate_chain: tuple[str, ...] = ()
    public_key: str = ""
    github_workflow: str = ""

    @classmethod
    def parse(cls, raw: dict, base: Path) -> "Signer":
        if not isinstance(raw, dict):
            raise PolicyError("each trusted_signers entry must be an object")
        kind = raw.get("type")
        if kind not in SIGNER_TYPES:
            raise PolicyError(f"signer type must be one of {SIGNER_TYPES}, got {kind!r}")
        name = str(raw.get("name") or kind)
        if kind == "sigstore":
            identity, issuer = raw.get("identity"), raw.get("issuer")
            if not identity or not issuer:
                raise PolicyError(f"sigstore signer {name!r} needs 'identity' and 'issuer'")
            caller = raw.get("github_workflow", "")
            if not isinstance(caller, str) or (caller and (
                issuer != GITHUB_ISSUER or not caller.startswith("https://github.com/")
                or "/.github/workflows/" not in caller or "@" not in caller
            )):
                raise PolicyError(f"sigstore signer {name!r}: github_workflow needs an exact GitHub workflow URL and GitHub issuer")
            return cls(name, kind, identity=str(identity), issuer=str(issuer), github_workflow=caller)
        if kind == "certificate":
            chain = raw.get("certificate_chain")
            if isinstance(chain, str):
                chain = [chain]
            if not chain:
                raise PolicyError(f"certificate signer {name!r} needs 'certificate_chain'")
            return cls(name, kind, certificate_chain=tuple(str(_resolve(base, c)) for c in chain))
        key = raw.get("public_key")
        if not key:
            raise PolicyError(f"public_key signer {name!r} needs 'public_key'")
        return cls(name, kind, public_key=str(_resolve(base, key)))


@dataclass
class Policy:
    mode: str = "enforce"
    signers: list[Signer] = field(default_factory=list)
    skill_roots: list[str] = field(default_factory=list)
    allow_repo_signers: bool = False
    sources: list[str] = field(default_factory=list)
    revoked_skills: dict[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        material: dict[str, str] = {}
        for signer in self.signers:
            paths = signer.certificate_chain + ((signer.public_key,) if signer.public_key else ())
            for path in paths:
                try:
                    material[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                except OSError as exc:
                    raise PolicyError(f"cannot read trust material {path}: {exc}") from exc
        blob = json.dumps(
            {"mode": self.mode, "signers": [s.__dict__ for s in self.signers],
             "trust_material": material, "revoked_skills": self.revoked_skills},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()


def _resolve(base: Path, value: str) -> Path:
    p = Path(os.path.expanduser(str(value)))
    return p if p.is_absolute() else (base / p).resolve()


def system_policy_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "skillseal" / "policy.json"
    return Path("/etc/skillseal/policy.json")


def user_policy_path() -> Path:
    env = os.environ.get("SKILLSEAL_POLICY")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "skillseal" / "policy.json"


def repo_policy_path(project: Path) -> Path:
    return project / ".skillseal" / "policy.json"


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError(f"policy {path} must be a JSON object")
    return data


def _layer(data: dict, path: Path) -> Policy:
    mode = data.get("mode", "enforce")
    if mode not in MODES:
        raise PolicyError(f"{path}: mode must be one of {MODES}")
    signers = [Signer.parse(s, path.parent) for s in data.get("trusted_signers", [])]
    roots = [str(r) for r in data.get("skill_roots", [])]
    revoked = data.get("revoked_skills", {})
    if not isinstance(revoked, dict):
        raise PolicyError(f"{path}: revoked_skills must be an object mapping SHA256 digests to reasons")
    for digest, reason in revoked.items():
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PolicyError(f"{path}: revoked_skills keys must be lowercase SHA256 hex digests")
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError(f"{path}: each revoked_skills entry needs a nonempty reason")
    return Policy(
        mode=mode,
        signers=signers,
        skill_roots=roots,
        allow_repo_signers=bool(data.get("allow_repo_signers", False)),
        sources=[str(path)],
        revoked_skills=dict(revoked),
    )


def load_policy(project: Path | None = None, explicit: Path | None = None) -> Policy:
    """Build the effective policy. Raises PolicyError on any malformed layer."""
    if explicit is not None:
        data = _read(explicit)
        if data is None:
            raise PolicyError(f"policy file not found: {explicit}")
        return _layer(data, explicit)

    authoritative: Policy | None = None
    for path in (system_policy_path(), user_policy_path()):
        data = _read(path)
        if data is not None:
            authoritative = _layer(data, path)
            break

    repo: Policy | None = None
    if project is not None:
        rp = repo_policy_path(project)
        data = _read(rp)
        if data is not None:
            repo = _layer(data, rp)

    # A repo must never be able to trust its own signer or relax the mode: without a
    # system or user policy, only its extra skill_roots are used (and nothing is trusted).
    if authoritative is None:
        return Policy(skill_roots=list(repo.skill_roots) if repo else [], sources=[])
    if repo is not None:
        authoritative.skill_roots += [r for r in repo.skill_roots if r not in authoritative.skill_roots]
        if authoritative.allow_repo_signers:
            authoritative.signers += repo.signers
            authoritative.sources += repo.sources
    return authoritative
