# Approve skills for your team

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

### 1. Create a skills repository

Make one repository (for example `YOUR-ORG/agent-skills`) with one folder per skill:

Here `YOUR-ORG` means the GitHub owner, either an organization or a personal account. `agent-skills` is an example repository name, not a required name. For example, `azurekid/agent-skills` means owner `azurekid`, repository `agent-skills`.

```text
skills/
  deploy/
    SKILL.md
    scripts/deploy.sh
  code-review/
    SKILL.md
```

Skills can also live in repository agent directories. The caller below includes
all default project skill locations supported by Skillseal; no move to `skills/`
is required:

| Agent | Project skill locations |
| --- | --- |
| Claude Code | `.claude/skills/` |
| GitHub Copilot | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| Codex | `.agents/skills/` |
| Gemini CLI | `.gemini/skills/`, `.agents/skills/` |
| OpenCode | `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` |
| OpenClaw (experimental) | `skills/`, `.agents/skills/` |

### 2. Add the approval workflow

Copy the small caller in [`examples/approve-skills.yml`](examples/approve-skills.yml)
to `.github/workflows/approve-skills.yml` **in your skills repository**.
It calls Skillseal's [reusable workflow](.github/workflows/approve-skills.yml),
which handles checkout, scanning, signing, verification, and committing signatures.
The root [`action.yml`](action.yml) is the lower-level composite action, not the
workflow file you create in your repository.

```yaml
name: Approve skills
on:
  push:
    branches: [main]
    paths:
      - "skills/**"
      - ".claude/skills/**"
      - ".agents/skills/**"
      - ".github/skills/**"
      - ".gemini/skills/**"
      - ".opencode/skills/**"
  workflow_dispatch:
permissions:
  contents: write     # commit skill.oms.sig
jobs:
  approve:
    uses: azurekid/skillseal/.github/workflows/approve-skills.yml@main
    with:
      signing-method: key
      skills: |
        skills/*
        .claude/skills/*
        .agents/skills/*
        .github/skills/*
        .gemini/skills/*
        .opencode/skills/*
    secrets:
      approval-private-key: ${{ secrets.SKILLSEAL_APPROVAL_PRIVATE_KEY }}
```

Keep the push `paths` filters and `skills` patterns in sync when adding custom
repository locations.
These patterns select immediate skill folders containing `SKILL.md`; add
appropriate patterns if your skills are nested more deeply.

Approval selection and runtime discovery are separate: signing a folder does
not make an agent discover it. The [runtime locations table](REFERENCE.md#where-each-agent-loads-skills)
lists defaults for each agent. In particular, `~/.copilot/skills/` is a
user-directory location, not the repository's `.copilot/skills/`. The latter
requires explicit `skill_roots` configuration if you want Skillseal to check
it. GitHub CI only signs checked-out repository files, not developers' home
directories; distribute signed skills to those locations afterward.

This development example requires the organization-signing changes on `main`;
older released actions do not accept these credentials. Existing verifiers
already support the public-key and certificate trust policies below.
For production, pin both the caller's reusable-workflow reference and the action
reference inside that shared workflow to reviewed commits. Pinning the outer
workflow does not pin an inner `uses: ...@main`.

| Input | Default | Meaning |
| --- | --- | --- |
| `skills` | Required | Space/newline separated folders or glob patterns |
| `signing-method` | `key` | Organization EC key; alternatively `certificate` or optional `sigstore` |
| `scan` | `skillseal scan --fail-on HIGH {path}` | Nonzero exit blocks signing |
| `only-changed` | `true` | Skip signing when the current authority still verifies the signature; scanning still runs |
| `commit-signatures` | `true` | Commit signatures to the caller's branch |

The `signed` workflow output lists signed skill folders. Empty `scan` is rejected;
to deliberately sign without scanning, use the lower-level action and its explicit
`allow-no-scan` option. Custom scanners must already be available on the runner;
use the lower-level action if you need additional setup steps.

Run approval only on reviewed, trusted branches, not pull requests. The shared
workflow rejects pull-request events and tags. Repository rules must permit its
token to push signature commits; otherwise pushing fails explicitly. Do not
weaken branch protection just to bypass this: use a reviewed custom PR-based
publishing workflow where required.

#### Configure the organization approval authority

Generate one approval key in a secure administrative environment (OpenSSL):

```bash
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out approval-private.pem
chmod 600 approval-private.pem
openssl pkey -in approval-private.pem -pubout -out approval.pub
```

Upload `approval-private.pem` as the GitHub Actions secret
`SKILLSEAL_APPROVAL_PRIVATE_KEY`. Use a restricted organization secret shared
only with approved signing repositories, or a repository secret. Never commit
the private key or distribute it to developer machines. Protect workflow and
scanner changes with review rules: anyone able to run arbitrary code in a job
receiving this secret can steal the key. Prefer ephemeral hosted runners; this
is not HSM-backed signing or isolation from malicious runner code.

The action removes PEM inputs from the environment before launching scanners,
scans before writing key files, writes temporary credential files with restricted
permissions, and removes them on normal success or failure. Forced runner
termination can prevent cleanup; do not rely on deletion as secure erasure.
Scanners still run on the signing runner, so only use reviewed scanners.

Distribute only the public key and a reviewed policy as described below.
The same authority can approve skills in multiple repositories without adding
workflow trust entries to endpoints.

For certificate signing, obtain an EC signing certificate and matching private
key from your approved PKI. Use a dedicated skill-approval CA, not your complete
OS certificate store. Change the caller to:

```yaml
    with:
      signing-method: certificate
      skills: ".claude/skills/* .agents/skills/* .github/skills/*"
    secrets:
      approval-private-key: ${{ secrets.SKILLSEAL_APPROVAL_PRIVATE_KEY }}
      approval-certificate: ${{ secrets.SKILLSEAL_APPROVAL_CERTIFICATE }}
      approval-certificate-chain: ${{ secrets.SKILLSEAL_APPROVAL_CERTIFICATE_CHAIN }}
```

Pass the leaf certificate as PEM and the approved CA chain as a concatenated
PEM bundle. No `id-token` permission is required for key/certificate signing.
The lower-level composite action accepts the same names as inputs but keeps
`signing-method: sigstore` as its default for backward compatibility.

On every push to `main` the workflow:

1. runs Skillseal's heuristic checks on each skill folder (`{path}` is replaced by the folder; exit code 0 means no findings at or above the selected severity),
2. signs accepted skills using the configured organization key or certificate
   and verifies the resulting signatures against that authority,
3. the last step commits `skill.oms.sig` next to each `SKILL.md`.

The built-in scan is a small heuristic check for obvious prompt-injection phrases and risky shell/network commands. It can miss harmful content and can flag benign examples; it is not a safety guarantee. You can also supply another scanner. If scanning fails, the skill is not signed. Want to sign without a scanner? You must say so with `allow-no-scan: true`.

A signature proves **who approved** a skill and that it **did not change**. It does not prove the skill is safe. That is the job of the scan, and of a human review before merge.

### 3. Distribute the organization trust policy

No `init` command or workflow identity is required. Distribute
[`organization-key.json`](examples/policies/organization-key.json) as
`policy.json`, with `approval.pub` beside it in the user/system policy directory.
The policy contains:

```json
{
  "mode": "audit",
  "allow_repo_signers": false,
  "trusted_signers": [
    {
      "name": "Organization skill approval",
      "type": "public_key",
      "public_key": "approval.pub"
    }
  ],
  "revoked_skills": {}
}
```

For PKI, distribute the
[`organization-certificate.json`](examples/policies/organization-certificate.json)
policy and `approval-ca.pem` instead. Use the
[policy copy instructions](GETTING-STARTED.md#use-a-policy-your-team-gave-you).
Start in audit mode and switch to enforce after checking the deployment.
Do not distribute private keys.

Workflow renames and additional signing repositories do not change endpoint
trust while they use the same authority. Each authorized repository can approve
any skill: restrict secret access accordingly. Rotate the key by distributing a
new public trust entry, switching signing credentials, and removing the old
entry after migration. For compromise, remove old trust immediately; follow the
[revocation runbook](#emergency-trust-revocation).

Signing replaces the root `skill.oms.sig`; organizational approval does not
preserve a separate vendor signature. Verify vendor provenance before approval
and retain that evidence outside the skill folder if required.

### Optional: keyless workflow trust

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

Fulcio uses the reusable workflow as the certificate identity. The additional
`github_workflow` policy field checks its authenticated Build Config URI
extension against **your caller**. Never configure the shared workflow identity
alone: that would authorize other repositories invoking it. Renaming the caller,
changing its branch, or changing the shared workflow ref requires a policy update.

If you use the composite action directly in your own workflow instead, omit
`--reusable-workflow`; the ordinary `--github-workflow` command remains valid.

Or share the resulting `~/.config/skillseal/policy.json` file. It is small and contains no secrets, so you can put it in dotfiles, a devcontainer, an onboarding script or a base image. Developers copy it to their own user policy location using the [copy instructions](GETTING-STARTED.md#use-a-policy-your-team-gave-you). Include any public key or certificate files it references. Do not distribute your own machine's absolute paths to those files.

#### Trusting more than one signing workflow

Trust follows the **signing workflow**, not the repository where a developer uses a skill. One central approval workflow can sign skills for many projects. With the reusable setup, trust entries also restrict the caller as described above.

If different repositories run their own approval workflows, add each trusted identity to the **same user policy**. For example:

```json
{
  "mode": "audit",
  "allow_repo_signers": false,
  "trusted_signers": [
    {
      "name": "central skills approval",
      "type": "sigstore",
      "identity": "https://github.com/azurekid/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main",
      "issuer": "https://token.actions.githubusercontent.com"
    },
    {
      "name": "app-specific skills approval",
      "type": "sigstore",
      "identity": "https://github.com/azurekid/app-one/.github/workflows/approve-skills.yml@refs/heads/main",
      "issuer": "https://token.actions.githubusercontent.com"
    }
  ]
}
```

These are example identities, not preconfigured approval services. Replace them with workflows you actually control and trust. When editing an existing policy, add entries to its `trusted_signers` array and preserve its other settings. Running `skillseal init --force` replaces the file; it does not append another signer.

Every listed workflow is trusted to sign any discovered skill. Entries do not restrict a signer to skills in a particular application repository. Only add workflows whose approvals you accept across the projects using this policy.

### 4. Get the skills to developers

Developers copy or clone the signed skill folders into one of the skill folders of their agent (see the [skill locations table](REFERENCE.md#where-each-agent-loads-skills)), including `skill.oms.sig`. Projects can also commit signed skills in `.github/skills` or `.claude/skills`.

### Sign without GitHub Actions

```bash
skillseal scan --fail-on HIGH skills/deploy                                      # heuristic scan only
skillseal sign --scan "skillseal scan --fail-on HIGH" skills/deploy               # Sigstore, opens a browser login
skillseal sign --no-scan --method key --private-key key.pem skills/deploy        # your own EC key
skillseal sign --scan "..." --method certificate --private-key k.pem \
  --signing-certificate leaf.pem --certificate-chain ca.pem skills/deploy        # your own PKI
```

Developers then trust the key with `skillseal init --public-key key.pub` or the CA with `skillseal init --certificate-chain ca.pem`.

### Emergency trust revocation

No server is required. The authoritative local/system policy controls trust
for every project checked by that installation. Distribute policy updates with
your existing endpoint management, configuration management, or another
authenticated administrative channel.

#### Withdraw a specific skill release

1. Obtain the affected release's exact files from a known copy. Compute its
   content identifier:

   ```bash
   skillseal digest path/to/affected-skill
   ```

2. Add the printed lowercase SHA256 digest to `revoked_skills` in the
   authoritative policy, preserving its other fields:

   ```json
   {
     "mode": "enforce",
     "allow_repo_signers": false,
     "trusted_signers": [],
     "revoked_skills": {
       "REPLACE_WITH_THE_64_CHARACTER_LOWERCASE_DIGEST": "INC-123: withdrawn release"
     }
   }
   ```

   This is a structure illustration, not a ready-to-load policy: replace the
   digest placeholder and preserve your actual `trusted_signers` entries.
   The reason must be nonempty. An invalid digest or malformed denylist is an
   explicit policy error, not an ignored entry.
   Do not use `skillseal init --force` to add revocations or signers: it replaces
   the policy and would discard existing denials.

3. Distribute the complete policy through your trusted administrative channel.
   Stage and validate it, then replace the live policy atomically. Do not
   rewrite it partially while hooks are reading it.
4. Run `skillseal verify --policy PATH/TO/POLICY path/to/affected-skill` and
   expect `revoked` with exit 1, including when that skill was previously cached.
   Check the effective system/user policy with `skillseal check` too.
5. Remove the affected skill from agents' loadable folders. Restart affected
   sessions if its instructions might already have entered their context.

The digest covers relative file paths and bytes, excluding the root
`skill.oms.sig` and the root `.git/` directory. It does not depend on installation
path, signer, or signature encoding. Copying, renaming the containing folder, or
re-signing unchanged files cannot bypass the denial. Any file/path/content
change creates a different digest; this is a release-content denylist, not a
semantic detector or publisher-wide revocation.

#### Revoke a compromised publisher

Remove **all** entries authorizing that publisher from the authoritative
`trusted_signers`, including alternate keys, certificate-chain entries, and
Sigstore identities. Set `allow_repo_signers` to `false` so a repository cannot
add the removed signer back. Removing an entry invalidates cached approvals
on the next check; replacing a configured key/certificate file also changes
the cache fingerprint.

For certificate trust, a shared CA entry may authorize more publishers than
the compromised one. Remove that trust path or migrate unaffected publishers
to narrower explicit keys/dedicated trust anchors. This release has no native
per-leaf certificate revocation, CRL, or OCSP integration. Do not describe a
content denial or removed local trust entry as CA-level certificate revocation.

Investigate and remove other copies and already-loaded instructions. Skillseal
does not undo previous tool actions or terminate running agents.

#### Recover and scale the rollout

Review a replacement release and sign it with an uncompromised, explicitly
configured signer. Keep withdrawn content digests denied. Restore publisher
trust only after investigation; do not remove denials merely to make a check
pass.

Use one managed policy per endpoint/group, not a policy per skill or repository.
The same configured publishers apply across discovered projects. External and
internal publishers follow identical verification rules; neither gains trust
because a signature is cryptographically valid or its certificate is public.
Use exact Sigstore issuer/identity pairs, pinned keys, or appropriately dedicated
certificate anchors. A certificate anchor authorizes its eligible signing chain,
not a particular vendor name or a specific skill.

There is no automatic broadcast, policy expiry, anti-rollback mechanism, or
delivery confirmation in this release. An offline endpoint retains its last
local policy and cannot know about a new withdrawal until it receives an
update. Track distribution/compliance externally and protect system policies
with administrator-managed permissions. Revocations are reported in every
mode, but only `enforce` requests blocking; `warn` and `audit` retain their
existing nonblocking behavior.

For an offline demonstration, run the [trust lab](examples/TRUST-LAB.md).

### Hooks that users cannot switch off

A user who controls their own machine can always remove a user hook. If you need more, place the policy and hook at system level (needs admin rights once, no MDM):

* skillseal reads `/etc/skillseal/policy.json` (Windows: `%ProgramData%\skillseal\policy.json`) first. When it exists, it wins over the user policy.
* GitHub Copilot CLI loads **policy hooks** from `/etc/github-copilot/policy.d/*.json` (Windows: `C:\ProgramData\GitHub\Copilot\policy.d\`). They load before all other hooks and `disableAllHooks` cannot turn them off. On macOS and Linux the file must be owned by root and not writable by group or others. Copy the content of `~/.copilot/hooks/skillseal.json` there.
* Claude Code has managed settings for the same purpose; put the same skillseal hooks in there.
