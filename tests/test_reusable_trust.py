from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier
from sigstore.errors import VerificationError

from skillseal.policy import GITHUB_ISSUER, Policy, PolicyError, Signer
from skillseal.verify import _crypto_verify

CALLER = "https://github.com/team/skills/.github/workflows/approve-skills.yml@refs/heads/main"
SHARED = "https://github.com/azurekid/skillseal/.github/workflows/approve-skills.yml@main"


@pytest.mark.parametrize("caller", [None, 42, "not-a-workflow", "https://github.com/team/skills"])
def test_caller_policy_rejects_malformed_values(tmp_path, caller):
    with pytest.raises(PolicyError, match="github_workflow"):
        Signer.parse({"type": "sigstore", "identity": SHARED, "issuer": GITHUB_ISSUER,
                      "github_workflow": caller}, tmp_path)


@pytest.mark.parametrize("actual", [CALLER, CALLER.replace("team/skills", "other/skills"), None])
@pytest.mark.parametrize("crypto_valid", [True, False])
def test_caller_extension_checked_after_crypto_verification(tmp_path, monkeypatch, actual, crypto_valid):
    import model_signing
    from sigstore.models import Bundle

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + timedelta(hours=1))
    )
    if actual:
        value = actual.encode()
        assert len(value) < 128
        builder = builder.add_extension(x509.UnrecognizedExtension(
            ObjectIdentifier("1.3.6.1.4.1.57264.1.18"), b"\x0c" + bytes([len(value)]) + value,
        ), critical=False)
    certificate = builder.sign(key, hashes.SHA256())
    calls = []

    def verified(*args):
        if not crypto_valid:
            raise ValueError("invalid signature")
        calls.append("authenticated")

    def bundle(*args):
        assert calls == ["authenticated"]
        return SimpleNamespace(signing_certificate=certificate)

    monkeypatch.setattr(model_signing.verifying.Config, "verify", verified)
    monkeypatch.setattr(Bundle, "from_json", bundle)
    sig = tmp_path / "skill.oms.sig"
    sig.write_text("{}")
    signer = Signer("shared", "sigstore", identity=SHARED, issuer=GITHUB_ISSUER, github_workflow=CALLER)
    ser = {"hash_type": "sha256", "ignore_paths": []}
    if not crypto_valid:
        with pytest.raises(ValueError, match="invalid signature"):
            _crypto_verify(tmp_path, sig, signer, ser)
        assert calls == []
    elif actual == CALLER:
        _crypto_verify(tmp_path, sig, signer, ser)
    else:
        with pytest.raises(VerificationError, match="extension|match"):
            _crypto_verify(tmp_path, sig, signer, ser)


def test_caller_restriction_changes_cache_fingerprint():
    first = Signer("shared", "sigstore", identity=SHARED, issuer=GITHUB_ISSUER, github_workflow=CALLER)
    other = Signer("shared", "sigstore", identity=SHARED, issuer=GITHUB_ISSUER,
                   github_workflow=CALLER.replace("team/skills", "other/skills"))
    assert Policy(signers=[first]).fingerprint() != Policy(signers=[other]).fingerprint()
