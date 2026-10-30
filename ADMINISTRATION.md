# Advanced administration

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Team setup](APPROVAL.md) | [Reference](REFERENCE.md)

For normal setup, use the [short signing guide](APPROVAL.md). Use this page
only when you need to customize signing or manage trust.

- [Set up signing manually](#1-create-a-skills-repository)
- [Understand scan results](#scan-results-and-signature-removal)
- [Use AgentLens](#optional-agentlens-scanning)
- [Update an existing workflow](#update-an-existing-workflow)
- [Distribute trust and signed skills](#3-distribute-the-organization-trust-policy)
- [Use keyless signing](#optional-keyless-workflow-trust)
- [Trust NVIDIA's signature](#trust-an-existing-nvidia-signature)
- [Withdraw approval](#emergency-trust-revocation)
- [Find hooks and check platform coverage](#hook-locations-and-platform-tests)
- [Manage device-wide hooks](#hooks-that-users-cannot-switch-off)

## 1. Create a skills repository

Use your own GitHub repository, with one folder per skill:

```text
skills/
  deploy/
    SKILL.md
    scripts/deploy.sh
  code-review/
    SKILL.md
```

Already using `.agents/skills/`, `.github/skills/` or another
[agent skill location](REFERENCE.md#where-each-agent-loads-skills)?
Keep it. You do not need to move skills to `skills/`.

## 2. Add the approval workflow

1. Copy [`examples/approve-skills.yml`](examples/approve-skills.yml) to
   `.github/workflows/approve-skills.yml` **in your skills repository**.
2. Keep the locations you use in both `paths` and `skills`. Patterns such as
   `skills/*` select immediate skill folders; add patterns for deeper folders.
3. Add the approval key as described below.
4. Review, commit and push. Open **Actions > Approve skills** to see the results.

The example calls the [reusable workflow](.github/workflows/approve-skills.yml).
It checks out the repository, scans skills, signs them, verifies the signatures
and commits them back. Use the lower-level [action](action.yml) only if you need
custom setup steps, such as installing another scanner.

**Before production:** pin both the reusable workflow and the action it calls
to reviewed commit SHAs. Pinning the outer workflow alone does not pin its
inner `uses: ...@main`.

Run only on reviewed, trusted branches, not pull requests or tags.
The workflow needs permission to push signature commits. If branch rules
prevent that, use a reviewed PR-based publishing workflow instead; do not
weaken branch protection.

### Workflow options

| Input | Default | Meaning |
| --- | --- | --- |
| `skills` | Required | Space/newline separated folders or glob patterns |
| `signing-method` | `key` | Organization EC key; alternatively `certificate` or optional `sigstore` |
| `scan` | `skillseal scan --fail-on HIGH {path}` | Scanner command; failed scans remove previous approval |
| `only-changed` | `true` | Skip signing when the current authority still verifies the signature; scanning still runs |
| `commit-signatures` | `true` | Commit signatures to the caller's branch |

Outputs: `signed` lists signed folders; `removed` lists folders whose signature
was removed. Both are space-separated lists.

`{path}` means the skill folder. A scanner must return exit code `0` to pass.
An empty `scan` is rejected. To deliberately skip scanning, use the lower-level
action with `allow-no-scan: true` (not recommended).

### Configure the organization approval authority

If you already have an approval key, keep using it. Otherwise, generate one
in a secure location **outside the repository**:

```bash
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out approval-private.pem
chmod 600 approval-private.pem
openssl pkey -in approval-private.pem -pubout -out approval.pub
```

On GitHub, open your repository:

1. Go to **Settings > Secrets and variables > Actions > New repository secret**.
2. Name it `SKILLSEAL_APPROVAL_PRIVATE_KEY`.
3. Paste the entire contents of `approval-private.pem`, including the
   `BEGIN PRIVATE KEY` and `END PRIVATE KEY` lines, and save.

Keep a protected backup: GitHub cannot show you the saved value later.
Never commit the private key, paste it into chat, or send it to developers.
Share only `approval.pub` and the [trust policy](#3-distribute-the-organization-trust-policy).
An organization secret is also suitable if restricted to approved repositories.

**Protect the signing job.** Review workflow and scanner changes, and prefer
ephemeral hosted runners. The action hides PEM inputs from scanner processes
and scans before writing temporary key files. Normal completion removes those
files; forced termination may prevent cleanup. This is not HSM-backed signing
or isolation from malicious runner code.

### Use a certificate instead

Obtain an EC signing certificate and matching private key from your PKI.
Use a dedicated approval CA, not the complete OS certificate store.
To require CA-issued leaves or Sigstore and disallow raw keys and self-issued
signing certificates, enable
[`require_ca_issued`](REFERENCE.md#optional-ca-issued-certificate-requirement)
in the authoritative policy. Self-signed root CAs remain valid trust anchors;
the signing leaf must be a non-CA certificate with a different subject and issuer.
Change the caller's settings to:

```yaml
    with:
      signing-method: certificate
      skills: ".claude/skills/* .agents/skills/* .github/skills/*"
    secrets:
      approval-private-key: ${{ secrets.SKILLSEAL_APPROVAL_PRIVATE_KEY }}
      approval-certificate: ${{ secrets.SKILLSEAL_APPROVAL_CERTIFICATE }}
      approval-certificate-chain: ${{ secrets.SKILLSEAL_APPROVAL_CERTIFICATE_CHAIN }}
```

Supply the leaf certificate as PEM and the CA chain as a concatenated PEM
bundle. Key and certificate signing do not need `id-token: write`.
When using the lower-level action, set `signing-method` explicitly:
its default is `sigstore`, not `key`.

## Scan results and signature removal

The default scanner checks locally for common prompt-injection phrases and
risky commands. It can miss harmful content and flag harmless examples.
**A signature proves approval and unchanged files, not safety.**

Scan output appears in the approval step, including for unchanged skills.

| Result | What happens |
| --- | --- |
| Every scan passes | New or changed skills are signed and verified; valid existing signatures are kept. |
| A scan rejects a skill or cannot finish | That skill's signature is removed. No skills are signed in that run. |
| A selected signed folder loses `SKILL.md` | Its signature is removed and approval fails. |

The reusable workflow commits removals even when approval fails.
**The workflow stays failed.** With `commit-signatures: false`, removals stay
only in the checkout.

For local commands, `skillseal sign --scan ...` also removes approval after a
failed scan. `skillseal scan` alone does not change local files.
Already-distributed copies need a [trust-policy update](#emergency-trust-revocation);
deleting a signature in Git does not withdraw those copies.

## Optional AgentLens scanning

AgentLens is optional. Local scanning remains the default.

**Before enabling uploads:** this service publishes HIGH/CRITICAL
fingerprints, skill names, redacted excerpts and assessment summaries
indefinitely, including private uploads. It retains high-risk originals
privately for 30 days. Redaction does not guarantee confidentiality.
Only submit material you can publish; never include private keys or
confidential files.

Set `scan` in your approval job's existing `with:` block:

```yaml
    with:
      scan: >-
        skillseal scan --agentlens-url https://app-skillvenom-bb6uknnp.azurewebsites.net
        --fail-on HIGH {path}
```

No extra scanner package is needed.

- **Uploads:** skill files and supporting scripts, excluding signatures and Git
  metadata, through multipart `POST /api/scan/files`.
- **Blocks:** HIGH/CRITICAL findings, service errors, invalid responses or
  incomplete coverage. There is no fallback to a local scan.
- **Limits per skill:** 500 files, 256 KiB per file, 5 MiB total.

`--agentlens-url` takes the HTTPS base URL, not the API path.
For a local command, replace `{path}` with your skill folder.

## Update an existing workflow

Upgrading Skillseal does not rewrite existing workflows.

1. Update the action or reusable-workflow pin to a reviewed commit containing
   AgentLens support and the `removed` output.
2. If you call the reusable workflow, it handles signature commits for you
   unless you set `commit-signatures: false`.
3. If you call the action directly, give its step `id: seal` and use the commit
   step below. It runs after failure when signatures were added or removed.

```yaml
      - name: Commit signatures
        if: ${{ !cancelled() && (steps.seal.outputs.signed != '' || steps.seal.outputs.removed != '') }}
        env:
          BRANCH: ${{ github.ref_name }}
        run: |
          set -euo pipefail
          git config user.name "skillseal[bot]"
          git config user.email "skillseal@users.noreply.github.com"
          git add -A -- ':(glob)**/skill.oms.sig'
          if git diff --cached --quiet; then exit 0; fi
          git commit -m "Update skill approval signatures"
          git push origin "HEAD:refs/heads/$BRANCH"
```

## 3. Distribute the organization trust policy

Give developers these **public files only**:

| Signing method | Files to distribute |
| --- | --- |
| Key | [`organization-key.json`](examples/policies/organization-key.json), renamed to `policy.json`, plus `approval.pub` |
| Certificate | [`organization-certificate.json`](examples/policies/organization-certificate.json), renamed to `policy.json`, plus `approval-ca.pem` |

Follow the [manual installation steps](REFERENCE.md#manual-setup).
The files go together in `~/.config/skillseal/` on macOS/Linux or
`%USERPROFILE%\.config\skillseal\` on Windows. If a policy already exists,
merge the signer into it; do not overwrite existing settings or revocations.
For managed devices, update the authoritative system policy instead.

No `init` command or workflow identity is needed for key/certificate trust.
Start in `audit` mode; switch to `enforce` after testing.

The same approval key can serve several repositories without changing
developer trust settings. Each repository with that key can approve **any**
skill, so restrict secret access.

To rotate a key: distribute the new public trust entry, switch signing
credentials, then remove the old entry after migration.
For a compromise, [remove old trust immediately](#emergency-trust-revocation).

Signing replaces the root `skill.oms.sig`; organizational approval does not
preserve a separate vendor signature. Verify vendor provenance before approval
and retain that evidence outside the skill folder if required.

## Optional: keyless workflow trust

If you prefer no persistent private key, set `signing-method: sigstore`, remove
the `secrets` mapping, and grant `id-token: write` in the caller's permissions.
For this mode only, configure workflow-based trust:

```bash
skillseal init \
  --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main \
  --reusable-workflow azurekid/skillseal/.github/workflows/approve-skills.yml@refs/heads/main
```

For a caller using `@COMMIT_SHA`, the `--reusable-workflow` suffix must be that
exact `@COMMIT_SHA`, not `@refs/heads/main`. For `@vX.Y.Z`, use
`@refs/tags/vX.Y.Z`. The action prints the signing identity and caller workflow
for troubleshooting.

Trust must identify **both** the reusable workflow and your caller.
Trusting only the shared workflow would also authorize other repositories
that call it. Rename the caller, change its branch or update the shared
workflow ref? Update the trust policy too.

The certificate identity identifies the reusable workflow; the policy's
`github_workflow` field checks the caller through its signed Build Config URI.

If you use the composite action directly in your own workflow instead, omit
`--reusable-workflow`; the ordinary `--github-workflow` command remains valid.

Share the resulting policy through a trusted channel, using the
[policy installation steps](REFERENCE.md#manual-setup). Include any public
key or certificate files it references, using portable relative paths.

### Trusting more than one signing workflow

For a **new user policy**, repeat `--github-workflow`.
Replace `YOUR-ORG` with your GitHub account or organization:

```bash
skillseal init --scope user \
  --github-workflow YOUR-ORG/skills-one/.github/workflows/approve.yml@refs/heads/main \
  --github-workflow YOUR-ORG/skills-two/.github/workflows/approve.yml@refs/heads/main
```

If those callers use the same reusable workflow, also supply
`--reusable-workflow` once. Each caller gets a restricted signer entry.

For an **existing policy**, append entries to `trusted_signers` and preserve
the other settings. Do not use `skillseal init --force`: it replaces the file.

Every listed workflow can approve any discovered skill across projects using
that policy. Trust is not limited to the project where a skill is installed.

## 4. Get the skills to developers

Copy or clone the **complete signed folders**, including `skill.oms.sig`, into
an [agent skill location](REFERENCE.md#where-each-agent-loads-skills).
Do not edit files after signing.

Signing a folder does not make an agent discover it. CI signs repository
files, not developers' home directories. For Copilot, `~/.copilot/skills/`
is a user location; repository `.copilot/skills/` needs explicit `skill_roots`.

## Trust an existing NVIDIA signature

The [NVIDIA DiffDock skill](https://github.com/NVIDIA/skills/tree/main/skills/bionemo-diffdock-nim)
already includes `skill.oms.sig`. You can verify NVIDIA's approval without
re-signing the skill:

1. Obtain [NVIDIA's root certificate](https://github.com/NVIDIA/skills/blob/main/nv-agent-root-cert.pem)
   from a source you trust. Confirm its provenance before accepting it as a
   trust anchor; a certificate shipped with a skill is not automatically trusted.
   Save it as `nv-agent-root-cert.pem` beside your user policy, normally in
   `~/.config/skillseal/` (Windows: `%USERPROFILE%\.config\skillseal\`).
2. Append this object to the existing policy's `trusted_signers` array, preserving
   its other signers and settings. The certificate path is relative to the policy:

   ```json
   {
     "name": "NVIDIA",
     "type": "certificate",
     "certificate_chain": ["nv-agent-root-cert.pem"]
   }
   ```

   If a system policy is installed, ask its administrator to add the signer
   there instead; the system policy takes precedence over your user policy.
   Do not use `skillseal init --force` to add this entry: it replaces the policy.
3. Copy the complete `bionemo-diffdock-nim` folder, including its signature and
   all supporting files, into an [agent skill folder](REFERENCE.md#where-each-agent-loads-skills).
   Do not edit the signed files. Verify it and then check all discovered skills:

   ```text
   skillseal verify /path/to/bionemo-diffdock-nim
   skillseal check
   ```

**Trust scope:** this authorizes skills signed under NVIDIA's certificate across
the projects using this policy, not only DiffDock. A valid signature establishes
provenance and integrity, not that the instructions are safe for your use case.
If you only want to approve this specific skill, review and sign that copy with
your own approval key instead of adding NVIDIA as a trusted signer.

## Sign without GitHub Actions

Scan and sign with your approval key:

```bash
skillseal sign --method key --private-key /secure/approval-private.pem \
  --scan "skillseal scan --fail-on HIGH {path}" skills/deploy
```

For certificates, use `--method certificate` and add
`--signing-certificate leaf.pem --certificate-chain ca.pem`.
For keyless signing with browser login, use `--method sigstore` and omit
`--private-key`.

On a new installation, trust a key with `skillseal init --public-key approval.pub`
or a CA with `skillseal init --certificate-chain ca.pem`.
For existing policies, merge the signer instead of replacing the policy.

## Emergency trust revocation

No server is required. The authoritative local/system policy controls trust
for every project checked by that installation. Distribute policy updates with
your existing endpoint management, configuration management, or another
authenticated administrative channel.

### Withdraw a specific skill release

1. Obtain the affected release's exact files from a known copy. Compute its
   content identifier:

   ```bash
   skillseal digest path/to/affected-skill
   ```

2. Add the printed lowercase SHA256 digest to `revoked_skills` in the
   authoritative policy, preserving its other fields:

   ```json
   "revoked_skills": {
     "REPLACE_WITH_THE_64_CHARACTER_LOWERCASE_DIGEST": "INC-123: withdrawn release"
   }
   ```

   This is a policy fragment, not a complete file. Replace the placeholder,
   keep existing revocations and signers, and give a nonempty reason.
   Invalid digests cause a policy error.
   Do not use `skillseal init --force`; it replaces the policy.

3. Distribute the complete policy through your trusted administrative channel.
   Stage and validate it, then replace the live policy atomically. Do not
   rewrite it partially while hooks are reading it.
4. Run `skillseal verify --policy PATH/TO/POLICY path/to/affected-skill` and
   expect `revoked` with exit 1, including when that skill was previously cached.
   Check the effective system/user policy with `skillseal check` too.
5. Remove the affected skill from agents' loadable folders. Restart affected
   sessions if its instructions might already have entered their context.

The digest identifies exact file paths and content, excluding the root
`skill.oms.sig`. Git metadata inside skills is rejected before digest checks.
Copying the folder, renaming it or re-signing
unchanged files does not bypass withdrawal. Editing content or paths inside
the skill creates a new digest: this blocks one release, not every variation.

### Revoke a compromised publisher

Remove **all** entries authorizing that publisher from the authoritative
`trusted_signers`, including alternate keys, certificate-chain entries, and
Sigstore identities. Set `allow_repo_signers` to `false` so a repository cannot
add the removed signer back. Removing an entry invalidates cached approvals
on the next check; replacing a configured key/certificate file also changes
the cache fingerprint.

**Shared CA?** Removing it may also affect other publishers. Move unaffected
publishers to explicit keys or dedicated trust anchors if needed.
Skillseal does not support per-certificate revocation, CRLs or OCSP.
Removing local trust is not CA-level certificate revocation.

Investigate and remove other copies and already-loaded instructions. Skillseal
does not undo previous tool actions or terminate running agents.

### Recover and scale the rollout

- Review the replacement and sign it with an uncompromised, trusted signer.
  Keep withdrawn digests denied. Restore publisher trust only after investigation.
- Use one managed policy per device/group, not one per skill or repository.
  Signers apply across discovered projects. Trust exact Sigstore identities,
  pinned keys or dedicated certificate anchors, not vendor names alone.
- Deliver updates through your managed channel and track which devices received
  them. Skillseal has no automatic broadcast, policy expiry, rollback protection
  or delivery confirmation. Offline devices keep their last local policy.
- Protect system policies with administrator-managed permissions.
  **Only `enforce` requests blocking.** `warn` and `audit` report revocations
  without blocking.

For an offline demonstration, run the [trust lab](examples/TRUST-LAB.md).

## Hook locations and platform tests

The [hook location table](REFERENCE.md#what-the-hook-adds-per-agent) lists
user-wide and project files for Copilot, Claude Code, Codex, Gemini, OpenCode
and experimental OpenClaw, including Windows path guidance.
Hooks and plugins are separate from the trust policy.

CI tests Linux, Windows and macOS. It checks generated configurations, runs
hook commands in real shells and tests OpenCode through a Node.js harness.
It does not run every agent application end-to-end; OpenClaw is untested.
See [test coverage and skips](REFERENCE.md#cross-platform-test-coverage).
Restart your agent after installation and test that blocking actually works.

## Hooks that users cannot switch off

A user who controls their machine can remove user hooks. For managed devices,
install system-level policies and hooks with administrator permissions:

- **Skillseal policy:** `/etc/skillseal/policy.json`, or
  `%ProgramData%\skillseal\policy.json` on Windows. It takes precedence over
  the user policy.
- **GitHub Copilot CLI:** copy the contents of `~/.copilot/hooks/skillseal.json`
  into a JSON file in `/etc/github-copilot/policy.d/`, or
  `C:\ProgramData\GitHub\Copilot\policy.d\` on Windows.
  These policy hooks load first and cannot be disabled by `disableAllHooks`.
  On macOS/Linux, the file must be root-owned and not group- or world-writable.
- **Claude Code:** add the Skillseal hooks to managed settings.

System-level configuration is not protection against someone with
administrator control of the device.
