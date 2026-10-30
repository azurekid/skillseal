# Technical reference

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

For custom signing workflows, certificates and incident response, see
[Advanced administration](ADMINISTRATION.md).

### How it works

```text
approve (CI)                               run (every developer machine)
------------                               -----------------------------
skill folder                               agent starts / calls a tool
   |                                          |
   v                                          v
scanner (exit 0 = clean)  --fail-->  stop  skillseal hook (agent's own hook system)
   |                                          |
   v                                          v
Sigstore keyless signing                   find every skill the agent can load
(identity = your workflow)                    |
   |                                          v
   v                                       verify OMS signature + exact file list
skill.oms.sig committed next to SKILL.md      |              |
                                           all OK         anything else
                                              |              |
                                           allow          block
```

skillseal uses the [OpenSSF Model Signing (OMS)](https://github.com/sigstore/model-transparency) format and the `model-signing` library, so NVIDIA's signed skills verify as they are.

### What the hook adds per agent

| Agent | File written (`--scope user`) | File written (`--scope project`) | Blocking events |
| --- | --- | --- | --- |
| GitHub Copilot CLI / VS Code (Copilot target) | `~/.copilot/hooks/skillseal.json` | `.github/hooks/skillseal.json` | `preToolUse` |
| Claude Code / VS Code (Claude target) | `~/.claude/settings.json` | `.claude/settings.json` | `PreToolUse` (all tools), `UserPromptSubmit`, `UserPromptExpansion` |
| Codex CLI / VS Code (Codex target) | `~/.codex/hooks.json` | `.codex/hooks.json` | `PreToolUse` |
| Gemini CLI | `~/.gemini/settings.json` | `.gemini/settings.json` | `BeforeTool` (answers `{"decision":"deny"}`) |
| OpenCode | `~/.config/opencode/plugins/skillseal.js` | `.opencode/plugins/skillseal.js` | `tool.execute.before` (plugin throws) |
| OpenClaw (experimental) | `~/.openclaw/policies/skillseal-guard.ts` | Same user-wide file | `before_tool_call` |

`~` means your home directory (`%USERPROFILE%` on Windows). Project paths are
relative to the project root. Claude Code, Codex and Gemini store hooks in
their configuration files; OpenCode uses a JavaScript plugin. Restart the
agent after installation, especially OpenCode, which loads its plugin at startup.

These are hook/plugin locations, not trust-policy files. The user trust policy
normally lives at `~/.config/skillseal/policy.json`, including on Windows.
See [policy locations and precedence](#the-trust-policy).

Blocking hooks are written as `skillseal hook ... || exit 2` for `sh` and `cmd.exe`, and as `& 'skillseal' hook ...; if (-not $?) { exit 2 }` for PowerShell. Claude Code hooks also set `"onFailure": "block"`, and on Windows they use exec form. The OpenCode plugin throws on any error. The generated commands request blocking on a crash or missing binary; host timeout behavior still applies, as described under [limits](#honest-limits). For Copilot and Claude a `SessionStart` hook also tells the agent why tools are blocked.

### Verify before agent startup

Hooks run inside an agent lifecycle and may run after it has loaded skill
instructions. To verify first, launch the agent through Skillseal:

```text
skillseal run --agent copilot -- copilot
```

The command discovers skills for the selected agent and fully verifies each
signature and file hash without using the verification cache. It refuses to
start the child command on any failure, including when policy mode is `warn` or
`audit`. The command is passed directly to the operating system; no shell is
used. Replace `copilot` with the agent name and its executable.

This gate only covers launches made through `skillseal run`. It does not sandbox
the agent or prevent skill files from changing between verification and agent
access; hooks remain useful as defense in depth.

#### Cross-platform test coverage

[CI](.github/workflows/ci.yml) runs the Python test suite, installed demo and
trust/revocation lab on **Linux, Windows and macOS**, with Python 3.10 and 3.13.

The [hook tests](tests/test_hooks_install.py) cover:

- Generated configurations and hook commands for Copilot, Claude Code, Codex
  and Gemini, using signed skills, unsigned skills and a missing executable.
- Real shell execution: `sh` on Linux/macOS; `cmd.exe`, Windows PowerShell 5.1,
  `pwsh` and exec-form commands on Windows. Shell-specific tests skip when
  that shell is unavailable.
- The OpenCode plugin in a Node.js harness. These tests skip if Node.js or
  the required installed Skillseal executable is unavailable.

This is not an end-to-end test of every agent application. Test blocking in
your installed agent too. **OpenClaw is experimental and untested.**

Skills that an agent puts in the prompt without a tool call are covered by the same rule: while any loadable skill fails, the agent cannot use tools.

The VS Code Copilot target also reads a repository's `.claude/settings.json`. So a project-scope Claude install also runs in VS Code Copilot sessions.

### Where each agent loads skills

Project folders are searched from the working directory up to the repository root.

| Agent | Project | User |
| --- | --- | --- |
| claude | `.claude/skills` | `~/.claude/skills`, `~/.claude/plugins` |
| copilot | `.github/skills`, `.claude/skills`, `.agents/skills` | `~/.copilot/skills`, `~/.claude/skills`, `~/.agents/skills` |
| codex | `.agents/skills` | `~/.agents/skills`, `/etc/codex/skills` |
| gemini | `.gemini/skills`, `.agents/skills` | `~/.gemini/skills`, `~/.agents/skills`, `~/.gemini/extensions` |
| opencode | `.opencode/skills`, `.claude/skills`, `.agents/skills` | `~/.config/opencode/skills`, `~/.claude/skills`, `~/.agents/skills` |
| openclaw | `skills`, `.agents/skills` | `~/.agents/skills`, `~/.openclaw/skills` |

### Manual setup

Prefer [guided setup](GETTING-STARTED.md#join-your-team). If an administrator
supplies separate policy files instead of a team package:

1. Obtain `policy.json` and its referenced public-key or certificate files
   through a trusted channel. Never install a private signing key on endpoints.
2. Create the user policy directory: `~/.config/skillseal` on macOS/Linux or
   `%USERPROFILE%\.config\skillseal` on Windows. Use `XDG_CONFIG_HOME` or
   `SKILLSEAL_POLICY` overrides if configured. A system policy takes precedence.
3. If a policy already exists, merge changes with your administrator; do not
   discard signers, revocations or other settings.
4. Put the reviewed policy there as `policy.json`, with the public files it
   references beside it. Relative paths resolve from this directory.
5. Run `skillseal install AGENT --scope user`, replacing `AGENT` with your agent,
   then restart it and check its hooks. Begin in audit mode.

Use `copilot` for the VS Code Copilot chat target or Copilot CLI, `claude` for
Claude Code and `codex` for Codex. The legacy VS Code Local target is unsupported.
Claude Code must trust the project before it runs hooks; use version 2.1.295+
for its `onFailure` blocking behavior. Codex requires approval of new hooks.
OpenCode loads its plugin only at startup.

For experimental OpenClaw, run `skillseal install openclaw --scope user` and
apply the printed `plugins.load.paths` snippet. This integration is not tested.

### Installation alternatives

The [recommended installation](GETTING-STARTED.md#install-skillseal) uses an
isolated Python environment managed by pipx or uv. Python 3.10+ is required.
Release wheels include the signed starter examples, and source distributions
are available for environments that build their own packages. There is no PyPI
publishing configured.

#### Verify a Python release

Use the [GitHub CLI](https://cli.github.com/) to download a specific release's
wheel and checksum manifest. Replace `VERSION` with its version number.
Python packages and the attested checksum manifest are available in releases
created after the Python package release workflow was added.

```text
gh release download vVERSION --repo azurekid/skillseal --pattern "skillseal-VERSION-py3-none-any.whl" --pattern SHA256SUMS.txt
gh attestation verify skillseal-VERSION-py3-none-any.whl --repo azurekid/skillseal --signer-workflow azurekid/skillseal/.github/workflows/release.yml --source-ref refs/tags/vVERSION
gh attestation verify SHA256SUMS.txt --repo azurekid/skillseal --signer-workflow azurekid/skillseal/.github/workflows/release.yml --source-ref refs/tags/vVERSION
```

Stop if verification fails. Check the wheel's SHA256 against its entry in the
verified manifest, using `sha256sum` on Linux, `shasum -a 256` on macOS, or
`Get-FileHash -Algorithm SHA256` in PowerShell. Then install the local wheel:

```text
pipx install ./skillseal-VERSION-py3-none-any.whl
```

Attestations establish that the artifact was built by the repository's release
workflow; they are not an independent code review or an OS publisher signature.
pipx and uv do not automatically verify these GitHub attestations. Dependencies
are resolved separately and are not covered by the Skillseal artifact attestation.
Source archives can be verified the same way, but installing them executes the
build backend; prefer the wheel when no source build is needed.

When switching from a standalone install, remove its old command from PATH
according to your organization's rules. Confirm `command -v skillseal` (Unix)
or `Get-Command skillseal` (PowerShell) resolves to the new installation. Rerun
`skillseal install AGENT --scope user` and/or `--scope project` for each scope
where you installed hooks, because existing hooks may point at the old binary.

#### Standalone archives

The optional shell and PowerShell installers download standalone release
archives, check SHA256 checksums and install for the current user. They do not
verify GitHub attestations automatically.
Standalone builds support Windows x64, macOS Apple silicon and Linux x64 with
glibc 2.35+; use a Python 3.10+ installation on other systems.
Close running agents before updating. If `skillseal` is not on PATH, open a
new terminal. For a Python install use `pipx ensurepath` or `uv tool update-shell`.

For an offline or manually reviewed installation, download the appropriate
archive and `SHA256SUMS.txt` from the [release page](https://github.com/azurekid/skillseal/releases).
Compare the archive's SHA256 with the published value before unpacking it:

```bash
# macOS
shasum -a 256 skillseal-macos-arm64.tar.gz
# Linux
sha256sum skillseal-linux-x64.tar.gz
```

```powershell
# Windows
(Get-FileHash .\skillseal-windows-x64.zip -Algorithm SHA256).Hash
```

For GitHub build provenance, before unpacking or executing an archive, use:

```text
gh attestation verify ARCHIVE --repo azurekid/skillseal --signer-workflow azurekid/skillseal/.github/workflows/release.yml
```

For new releases, also verify `SHA256SUMS.txt` with the same command.
For Windows offline installation, run a reviewed copy of
`install.ps1 -ZipPath .\skillseal-windows-x64.zip`.
Installers and standalone programs are not Authenticode or Apple Developer ID
signed; follow company software approval rules if they are blocked.

### Downloadable starter examples

`skillseal demo` includes everything needed for a quick test. For a reusable
copy, download `skillseal-starter.zip` from a v0.4.0+ release and follow its
[instructions](examples/starter/README.md).
The demo-only public-key file SHA256 is:

```text
b22cd994bc688234edaf8df63f23a923101cb5079e23d1dd0c2ee77c1875ad33
```

Compare this fingerprint through a source you trust. Do not install demo trust
as your organization policy. The demo proves signature verification, not host
enforcement.

### The trust policy

Example ([`examples/policies/user-policy.json`](examples/policies/user-policy.json)):

```json
{
  "mode": "enforce",
  "allow_repo_signers": false,
  "trusted_signers": [
    { "name": "our approval workflow", "type": "sigstore",
      "identity": "https://github.com/YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main",
      "issuer": "https://token.actions.githubusercontent.com" },
    { "name": "NVIDIA verified skills", "type": "certificate",
      "certificate_chain": ["nv-agent-root-cert.pem"] }
  ],
  "skill_roots": []
}
```

| Field | Meaning |
| --- | --- |
| `mode` | `enforce` blocks tool calls, `warn` shows a warning but allows calls, and `audit` records checks in `~/.cache/skillseal/audit.jsonl` without warning or blocking. Set it with `skillseal init --mode enforce|warn|audit`; default: `enforce`. |
| `trusted_signers` | `sigstore` (identity + issuer), `certificate` (chain of PEM files) or `public_key` (EC PEM). Relative paths are relative to the policy file. |
| `skill_roots` | Extra folders to search for skills. |
| `allow_repo_signers` | Let a repository's `.skillseal/policy.json` add signers. Default `false`. |
| `require_ca_issued` | Require CA-issued signing certificates or Sigstore. Reject raw-key signatures, self-issued signing certificates, and CA certificates used as signing certificates. Default `false`; only the authoritative policy controls this requirement. |
| `revoked_skills` | Object mapping lowercase `skillseal digest` SHA256 content identifiers to nonempty incident reasons. Default `{}`. Only the authoritative policy supplies these denials; repository layers cannot add or clear them. |

For a complete third-party example, see
[trusting NVIDIA's existing DiffDock signature](ADMINISTRATION.md#trust-an-existing-nvidia-signature),
including certificate placement, preserving existing signers and trust scope.

Sigstore entries can also set `github_workflow` to an exact caller workflow URL.
For shared workflows, `identity` is the reusable workflow URI and
`github_workflow` is your caller URI. Verification checks the caller's signed
Fulcio Build Config URI extension after cryptographic verification. Missing or
mismatched extensions fail. `init --github-workflow CALLER --reusable-workflow SHARED`
creates this pair. Do not trust a cross-repository shared identity without a
caller restriction. Older Skillseal versions do not enforce this field; upgrade
verifiers before adopting shared-workflow signing.

For multiple signing repositories, create a user policy with repeated
`--github-workflow` options; each entry becomes a separate trusted signer and
the policy applies across projects checked by that user. A single
`--reusable-workflow` can be paired with multiple caller workflows. To add
signers to an existing policy, preserve its settings and edit the
`trusted_signers` array; `init --force` replaces the policy rather than merging.

Where policies are read from:

1. System: `/etc/skillseal/policy.json` (Windows: `%ProgramData%\skillseal\policy.json`). If it exists, it wins.
2. User: `$SKILLSEAL_POLICY` or `~/.config/skillseal/policy.json` (uses `XDG_CONFIG_HOME` when set).
3. Repository: `.skillseal/policy.json` (create with `skillseal init --scope repo`). A repository can only add `skill_roots`. It can never change the mode, and it can only add signers when the system or user policy sets `allow_repo_signers: true`. Without a system or user policy nothing is trusted, so everything is blocked.

### What verification checks

For each skill folder (a folder with `SKILL.md`):

* `SKILL.md` and `skill.oms.sig` exist and are normal files.
* No symlinks and no special files anywhere in the folder; at most 2000 files and 64 MiB.
* No `.git` directories or pointer files anywhere inside the skill, including
  case variants. Git configuration and hooks must not bypass approval. A parent
  repository's `.git` outside the skill folder is unaffected.
* The signature uses OMS per-file hashing with sha256, blake2 or blake3 and `allow_symlinks: false`.
* No file exists under a path that the signature chose to ignore. OMS ignores `.github/`, `.gitignore` and `.gitattributes` by default; skillseal signs them, and for a third-party signature it rejects any file hidden there.
* The signature is valid for one of the trusted signers, and the folder contains **exactly** the signed files with the signed hashes. No extra, missing or changed files.

Note: `model-signing` on its own skips `.github/`, `.gitignore` and `.gitattributes` while verifying, even when the signer hashed them. skillseal passes an explicit hashing config so these files are always checked.

Signing also rejects embedded Git metadata. Deploy skill folders without it;
do not use an entire Git checkout as a loadable skill. Existing signatures for
metadata-free folders remain compatible, including signatures that list `.git`
as an ignored path. Adding Git metadata invalidates approval before any cache
hit can be accepted.

Good results are cached in `~/.cache/skillseal/verified.json`, keyed by the policy, the signature, configured key/certificate file contents, and the hash of every file. Content revocations are checked before cache hits. Removing a signer or changing its trust file invalidates its old approvals. Every check still hashes local skill files; this is not constant-time verification.

### Certificate trust and operating-system stores

#### Optional CA-issued certificate requirement

Set `"require_ca_issued": true` in your authoritative system or user policy to
reject raw public-key signatures and self-issued signing certificates. Existing
policies are unchanged unless this option is enabled. To create a new policy:

```text
skillseal init --require-ca-issued --certificate-chain approval-ca.pem
```

Or use `--require-ca-issued` with the existing Sigstore identity/workflow
options. Do not use `init --force` to enable it on an existing policy: edit that
policy to preserve its signers and revocations. `skillseal check` displays the
requirement. Changing it invalidates cached verification results. It applies
to `verify`, `check`, hooks, and the pre-launch `run` gate. As with other
verification failures, hook blocking still depends on `mode`; `run` always
refuses failures.

Certificate signers must supply a leaf with a different subject and issuer,
and `BasicConstraints` explicitly declaring `ca: false`. Self-issued rollover
certificates are conservatively rejected too. The normal OMS cryptographic
signature and chain checks must still succeed against your configured anchors.
Self-signed **root CAs are allowed**; they are normal trust anchors, not the
signing leaf. Sigstore continues to use its issuer, identity, chain and
transparency verification.

This option does **not** mean publicly trusted CAs only: an explicitly authorized
private CA is allowed. It does not add OS-store trust, online revocation checks,
or a trusted timestamp, and it cannot prevent an authorized CA from approving
unsafe content. The key-based team packages generated by `setup organization`
do not meet this requirement; use a certificate or Sigstore policy instead.

Skillseal deliberately requires explicit certificate-chain files for certificate
signers; it does not automatically trust all certificates in an OS store.
Native stores differ across Windows, macOS, Linux distributions, and Python
builds. A TLS trust anchor is not automatically an authorized skill publisher.

The GitHub action supports `signing-method: key` or `certificate` with PEM
credentials passed explicitly from GitHub secrets. The reusable approval
workflow defaults to `key`; the composite action defaults to `sigstore` for
compatibility. Organization approval policies authorize the key/anchor, not the
GitHub workflow. See [manual authority setup](ADMINISTRATION.md#configure-the-organization-approval-authority).

The inspected `model-signing` 1.1.1 certificate verifier uses `certifi` when
no chain is supplied, not a portable native-store interface. It checks the
chain at the signing certificate's `notBefore` time. That is not proof of a
trusted signing timestamp, current certificate validity, or current revocation
status. Skillseal does not add online OCSP/CRL checking. Sigstore is a separate
verifier with issuer/identity and transparency verification; do not apply
ordinary current-time leaf-expiry assumptions to its short-lived certificates.

For managed internal PKI, provision a dedicated approved certificate bundle
through your administrative channel, or pin an approved public key. If you
export a certificate from a native store, validate the chosen anchor and scope
before configuring it. Do not export/trust the entire OS store. A future native
store adapter would still need explicit publisher authorization, signing-usage
checks, revocation/freshness semantics, and cross-platform tests; it is not just
a performance optimization.

See [emergency revocation](ADMINISTRATION.md#emergency-trust-revocation) for content
denials and signer removal. These are local authorization decisions, not a claim
that a CA has revoked a certificate.

### Honest limits

skillseal raises the bar a lot, but it is not a sandbox:

* **A user who controls their machine can remove the hooks.** skillseal protects people and teams against poisoned skills, not against themselves. See [Hooks that users cannot switch off](ADMINISTRATION.md#hooks-that-users-cannot-switch-off).
* **Malicious repositories do not bring the guard.** That is why you install with `--scope user`.
* **Standalone builds** are made with PyInstaller for Windows x64, macOS arm64 and Linux x64 (glibc 2.35+). They are not Authenticode or Apple Developer ID signed; integrity comes from the SHA256 checksums and GitHub build provenance.
* **Copilot hook timeouts fail open** (documented by GitHub). The check is cached and the timeout is 60 seconds, but a hook that hangs lets the call through.
* **Gemini CLI treats exit code 1 as a warning.** skillseal never uses exit 1 to block there; it returns `{"decision":"deny"}`.
* **File permissions are not signed.** OMS hashes file content, not the executable bit.
* **Only skill folders are covered.** Single-file commands such as `.claude/commands/*.md`, and instruction files such as `AGENTS.md` and `CLAUDE.md`, are not covered by signature verification.
* **The built-in scanner is heuristic.** `skillseal scan` checks for a small set of obvious prompt-injection and risky shell/network patterns. It can miss harmful content and flag benign examples; do not treat it as a safety guarantee.
* **Hooks are Preview in VS Code**, and the legacy Local harness is not supported.
* **OpenClaw is not tested.** Copilot CLI and OpenCode were tested end to end (blocked with an unsigned skill, allowed with a signed one). Real NVIDIA-signed skills verify with their root certificate and fail after any edit.
* **The cache is protected by normal file permissions** (`0600`). Someone who can write to your home folder can already change your agent config.
* **Sigstore verification** downloads and caches the public-good trust root on first use. `certificate` and `public_key` signers work fully offline.

### Why this exists (prior art)

Before building this we checked what already exists (October 2026):

| Project | What it does | What is missing for this use case |
| --- | --- | --- |
| [OpenSSF Model Signing (OMS)](https://github.com/sigstore/model-transparency), `model-signing` | Signs a whole folder: a Sigstore bundle with the hash of every file | No agent integration, no trust policy, default config skips `.github/` |
| [NVIDIA verified skills](https://github.com/NVIDIA/skills) | Ships skills with `skill.oms.sig` (OMS) and a root certificate | Checking is manual (`model_signing verify`); nothing enforces it when the agent runs |
| [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner), [Snyk agent-scan](https://github.com/snyk/agent-scan) | Static scanners for skills and agent files | Scanning only, no signing, no enforcement |
| [Trail of Bits mcp-context-protector](https://github.com/trailofbits/mcp-context-protector) | Trust-on-first-use pinning for MCP servers | MCP only, not skills, no central approval |
| Claude Code plugin marketplaces | `sha` pinning of plugin sources | Pinning at install time only, no signature, no check at load time |

skillseal reuses OMS and adds the missing parts: a trust policy, stricter verification, a scan gate, and enforcement through each agent's own hook system.

### Command reference

Run `skillseal` without arguments, or `skillseal menu`, in an interactive
terminal for the numbered menu. It wraps the existing checks, setup and
enforcement flows and adds guided local scanning/signing. Existing commands
remain noninteractive unless they already have a setup confirmation.

Personal-key setup asks for permission before generating an EC P-256 key
outside the project, adding its public key to the user policy and installing
hooks. These are separate confirmations. Existing policies are backed up and
keep their mode, signers and revocations; new policies start in audit mode.
It refuses managed system policies and `require_ca_issued` policies.

Local signing requires confirmation before scanning (a failed/rejected scan
removes prior approval) and again before replacing a signature. HIGH/CRITICAL
findings block signing. The menu verifies each new signature against the
effective policy and explicitly reports when a signed skill is still untrusted.
It never automatically trusts an existing key or certificate. Menu actions
report failures and return to the menu; Ctrl+C exits and EOF ends input.

```text
skillseal [menu]                       # interactive terminal only
skillseal demo                         # isolated embedded signature demonstration
skillseal setup      [--bundle TEAM.zip] [--agent NAME] [--project DIR] [--yes]
skillseal setup organization [--name NAME] [--repository OWNER/REPO] [--branch main]
                            [--upload-secret] [--private-key ORIGINAL.pem] [--project DIR] [--yes]
skillseal setup enforce [--agent NAME] [--project DIR] [--yes]
skillseal init       [--scope user|repo] [--mode enforce|warn|audit] [--github-workflow REF ...] [--identity ID --issuer URL]
                     [--reusable-workflow REF] [--public-key PEM] [--certificate-chain PEM ...] [--require-ca-issued] [--force]
skillseal check      [--agent NAME ...] [--cwd DIR] [--policy FILE] [--json] [--no-cache]
skillseal install    AGENT... [--scope project|user] [--project DIR] [--exe PATH]
skillseal uninstall  AGENT... [--scope project|user] [--project DIR]
skillseal sign       DIR... (--scan CMD | --no-scan) [--method sigstore|key|certificate]
                     [--private-key PEM] [--signing-certificate PEM] [--certificate-chain PEM ...]
skillseal scan       DIR... [--fail-on LOW|MEDIUM|HIGH]
skillseal verify     DIR... [--policy FILE] [--json] [--no-cache]
skillseal digest     DIR...             # content identifiers for revoked_skills
skillseal hook       AGENT [EVENT]      # called by the agent, reads the hook JSON on stdin
skillseal run        --agent AGENT [--cwd DIR] [--policy FILE] -- COMMAND [ARG...]
```

`AGENT` is one of `claude`, `copilot`, `codex`, `gemini`, `opencode`, `openclaw`. `install` and `uninstall` default to `--scope project`; on a developer machine use `--scope user`.

Guided setup defaults to Copilot and supports the five nonexperimental agents.
See the [onboarding walkthrough](GETTING-STARTED.md#five-minute-setup).
It never treats an imported package's self-declared organization or checksum as
independent proof of identity; accepting it grants authority to its public key.
`--yes` explicitly authorizes that trust and the displayed changes.

Organization setup can reuse an original, unencrypted EC P-256 private key
outside the repository using `--private-key`. In this mode an existing workflow
is preserved rather than rewritten. With `--upload-secret`, an existing approval
secret is kept and only a missing secret is uploaded. GitHub secrets are
write-only: the wizard cannot prove the saved value matches the supplied key.
Verify a GitHub-produced signature with the generated public policy before
distribution. This is not an authority-rotation or general overwrite option.

Team packages use format `skillseal-team-v1`: a ZIP containing exactly
`team.json`, `policy.json` and `approval.pub`. The manifest identifies the
organization and SHA256 of the public PEM file. The policy must be audit mode,
disallow repository signers, and contain exactly that single P-256 key, named
with the organization. The public key must use canonical SubjectPublicKeyInfo
PEM with no trailing content. No roots, extra signers, scripts, private keys or policy
overrides can be imported. Packages larger than 3 MiB or with entries larger
than 1 MiB, duplicate/unexpected names, encryption or symlinks are rejected.
Entries are read as data, never extracted or executed.

Setup stages hook merges before changing live files, writes settings atomically,
and retains `.backup-<id>` copies when changing existing files. An I/O failure
rolls back files already written; a crash or power loss is not a multi-file
transaction. Organization key backup and GitHub upload are separate operations.
An interrupted or failed upload may require adding the saved key as the secret
manually; do not rotate an authority simply to retry onboarding.

### Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest -q
```

CI runs the tests on Linux, macOS and Windows, plus a real Sigstore keyless sign and verify round trip through the action.

Build the standalone binary (into `dist/skillseal/`):

```bash
./packaging/build.sh
```

A tag `v*` runs the [release workflow](.github/workflows/release.yml): it builds
wheel and source distributions, checks their metadata, and tests both installed
outside the checkout, including pipx and uv wheel installations. It also builds
the optional binaries on Windows, Linux and macOS and tests each one (key and
Sigstore signing, tamper detection, and on Windows `install.ps1` plus a hook in
PowerShell 5.1). Python packages, standalone
archives, starter ZIP and `SHA256SUMS.txt` receive GitHub build provenance.
Manual workflow runs build and test artifacts without publishing or attesting
them. No PyPI credentials or OS publisher-signing credentials are required.
