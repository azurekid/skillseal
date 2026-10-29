"""Content-addressed cache of successful verifications.

Key = sha256(policy fingerprint, signature bytes, every file path + content hash
on disk). A hit means the exact same bytes were already verified against the
same signers, so the result is identical; any edit, added file or policy
change produces a new key. The cache only ever stores successes.

The file is protected only by normal file permissions (0600). Code already
running as your user can also edit your hook settings, so it is outside the
threat model either way.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from . import SIGNATURE_FILE

MAX_ENTRIES = 5000


def cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "skillseal" / "verified.json"


def skill_digest(root: Path, files: list[str]) -> str:
    """Portable digest of paths and contents, excluding the root signature."""
    h = hashlib.sha256()
    h.update(b"skillseal-content-v1\0")
    for rel in sorted(files):
        if rel == SIGNATURE_FILE:
            continue
        fh = hashlib.sha256()
        with open(root / rel, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                fh.update(chunk)
        h.update(rel.encode() + b"\0" + fh.digest())
    return h.hexdigest()


def content_key(root: Path, files: list[str], sig: Path, policy_fp: str, *, digest: str | None = None) -> str:
    h = hashlib.sha256()
    h.update(b"skillseal-v2\0" + policy_fp.encode() + b"\0")
    h.update(hashlib.sha256(sig.read_bytes()).digest())
    h.update((digest if digest is not None else skill_digest(root, files)).encode())
    return h.hexdigest()


def _load() -> dict:
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key: str) -> str | None:
    entry = _load().get(key)
    return entry.get("signer") if isinstance(entry, dict) else None


def put(key: str, signer: str) -> None:
    data = _load()
    data[key] = {"signer": signer, "at": int(time.time())}
    if len(data) > MAX_ENTRIES:
        newest = sorted(data.items(), key=lambda kv: kv[1].get("at", 0) if isinstance(kv[1], dict) else 0)
        data = dict(newest[-MAX_ENTRIES:])
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".verified-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        pass
