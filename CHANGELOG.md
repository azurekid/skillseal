# Changelog

## 0.4.2

- Explain `enforce`, `warn` and `audit` modes in CLI output and `init --help`.
- Clarify mode behavior, configuration and defaults in the README and reference.
- Save generated team packages outside the signing checkout and support multiple
  GitHub workflow signers in one user policy.

## 0.4.1

- Give individual developers and private repositories a first-class setup path,
  alongside optional team sharing, without implying corporate accounts or
  administrators are required.
- Replace the long onboarding pages with short install, developer and team
  setup steps. Move custom signing and incident-response details to the
  advanced administration guide, keeping the normal path free of policy JSON
  and cryptography explanations.
- Allow organization setup to reuse an original private key using `--private-key`,
  retaining an existing workflow and GitHub approval secret instead of forcing
  users to create another authority. Show fingerprint and secret-match limits
  before confirmation; never overwrite existing team outputs or rotate trust.
- Explain recovery from an existing approval secret and how to verify that the
  GitHub signer matches the generated team policy.

## 0.4.0

- Add `skillseal demo`, with embedded signed examples in wheels and standalone builds.
- Add guided `setup organization` repository scaffolding, protected private-key
  backup, explicit GitHub secret upload, a commit-pinned signing action, and a
  public-only team onboarding ZIP.
- Add `setup --bundle` with explicit authority confirmation, strict bounded ZIP
  validation, audit-first user hooks, backups, rollback, and protection for
  existing authorities and managed policies. Add readiness-gated `setup enforce`.
- Make role-based administrator/developer building blocks the primary onboarding
  path; retain manual instructions for advanced trust arrangements.
- Add two pre-signed starter skills, an explicit demo-only trust policy, a public
  key fingerprint, and a checksummed/attested starter ZIP in release assets.
- Clarify user policy folders, required filenames, and copying both the policy
  and public key for nontechnical users.
- Replace decorative CLI check output with a compact plain-text report, explicit
  approval statuses, consistent verification details, and clear next steps.
  JSON output, hook responses, and exit codes remain unchanged.

## 0.3.1

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
