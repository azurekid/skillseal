# Changelog

## 0.3.1 (unreleased)

- Support organization approval keys and dedicated certificate anchors in the
  action and reusable workflow, with explicitly passed GitHub secrets.
- Make organization approval the recommended setup and the reusable workflow's
  default. Keep the composite action's keyless default for compatibility.
- Scan before writing private credentials, exclude PEM inputs from scanner
  subprocesses, verify produced signatures, and clean temporary credential files.
- Add a reusable approval workflow and a small caller example for skills repos.
- Bind shared-workflow trust to the caller's signed Fulcio Build Config URI;
  require upgraded verifiers and do not trust a shared identity on its own.
- Verify newly produced signatures and use the actual shared signing identity
  for unchanged-skill checks.
- Add real reusable-signing CI coverage and local caller-binding tests.

## 0.3.0

- Add portable `skillseal digest` content identifiers and authoritative-policy
  `revoked_skills` denials. Copying or re-signing identical content does not
  bypass a content denial.
- Check content revocations before accepting cached approvals.
- Invalidate cached approvals when configured public-key or certificate files
  change, not just when their configured paths change.
- Add an offline internal / external publisher trust lab, exercised by the
  existing Windows, macOS, and Linux CI matrix.
- Document emergency signer removal, content withdrawal, policy rollout,
  recovery, certificate-store limits, and host enforcement limits.
- Include the built-in heuristic scanner introduced since 0.2.1.

### Release validation

Before tagging `v0.3.0`, require the test matrix, offline trust lab, real Sigstore
CI job, and manual standalone release-workflow build to pass. Publish through
the existing tag-triggered release workflow; it produces platform archives,
SHA256 checksums, and GitHub build provenance. Do not publish a release or claim
Windows/Linux verification based only on a local macOS run.
