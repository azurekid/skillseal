import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from skillseal import policy as policy_mod


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.delenv("SKILLSEAL_POLICY", raising=False)
    monkeypatch.delenv("SKILLSEAL_SCANNER", raising=False)
    monkeypatch.setattr(policy_mod, "system_policy_path", lambda: tmp_path / "no-system-policy.json")
    return home


def make_key(dirpath: Path, name: str = "k"):
    key = ec.generate_private_key(ec.SECP256R1())
    priv = dirpath / f"{name}.pem"
    pub = dirpath / f"{name}.pub"
    priv.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return priv, pub


@pytest.fixture
def keys(tmp_path):
    d = tmp_path / "keys"
    d.mkdir()
    return make_key(d)


def make_skill(root: Path, name: str = "demo") -> Path:
    d = root / name
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test skill\n---\nDo the thing.\n")
    (d / "scripts" / "run.sh").write_text("echo hi\n")
    return d


def write_policy(path: Path, pub: Path | None, mode: str = "enforce", **extra) -> Path:
    signers = [{"name": "test key", "type": "public_key", "public_key": str(pub)}] if pub else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": mode, "trusted_signers": signers, **extra}))
    return path
