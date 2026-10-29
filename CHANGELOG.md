# Changelog

## 0.3.0 (unreleased)

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
