# Reproducible trust and emergency revocation lab

This offline lab demonstrates Skillseal's verifier and Copilot skill discovery.
It does not install hooks, start Copilot, modify your real policy, or prove that
a particular version of an agent host enforces hook decisions.

## Run from a checkout

Use Python 3.10 or later. Installation needs package access; running the lab
after installation needs no network, server, Azure subscription, or tenant.

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Then:

```bash
python -m pip install ".[test]"
python examples/trust-lab.py
```

The script generates fresh test keys and a test CA in a temporary directory.
The directory, private keys, policy, and cache are removed when the script exits.
Never install the test CA into your OS certificate store.

## Expected results

The script checks exit codes and JSON verification results, exits nonzero on
failure, and ends with `LAB PASSED`. It demonstrates:

1. Unsigned content is rejected.
2. An explicitly configured internal EC key is trusted.
3. An external certificate signature is rejected before its dedicated CA is
   configured, then accepted after explicit trust is added.
4. Replacing a configured CA file invalidates its cached approvals; an edit to
   a signed skill is also rejected.
5. A previously cached external approval is rejected after content revocation.
6. Re-signing identical content does not bypass the denylist.
7. Removing external publisher trust does not remove internal publisher trust.
8. A reviewed and signed replacement is accepted while the old digest stays revoked.

These are synthetic publishers, not a live third-party publisher or Sigstore
test. The separate CI Sigstore job exercises real GitHub workflow signing.
The lab deliberately uses `--no-scan`: its subject is provenance, integrity,
and revocation, not whether the harmless skill text passes a threat scanner.

The regular test suite separately checks Copilot hook `deny` output, enforce /
warn / audit behavior, and audit records after revocation:

```bash
python -m pytest -q
```

CI runs the lab on Windows, macOS, and Linux. A locally successful run proves
only the environment where it ran; check the CI results before claiming
cross-platform release validation.

## Demonstrate in a real agent host

Use a disposable VM or developer profile for this optional step. Install hooks
using the [getting-started guide](../GETTING-STARTED.md), configure an explicit
publisher, and place a harmless signed skill in the host's supported skill
directory.

1. Verify the skill and observe a successful tool call.
2. Get its digest with `skillseal digest PATH`.
3. Add that digest and an incident reason to the authoritative policy's
   `revoked_skills`, preserving other fields. Use `mode: enforce`.
4. Run `skillseal check --agent copilot` and expect `revoked` and exit 1.
5. Make another tool call and record the actual host's response.
6. Test the missing-binary and timeout cases separately in the disposable profile.

Record host version, runtime, operating system, hook configuration, and observed
outcome. Do not equate verifier rejection or emitted hook JSON with proven host
enforcement. Host timeouts can fail open; content already in a running agent's
context cannot be recalled by changing policy.

See the [incident runbook](../APPROVAL.md#emergency-trust-revocation) for policy
distribution, signer compromise, and recovery.
