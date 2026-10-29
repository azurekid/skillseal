# Technical reference

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

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
| OpenClaw (experimental) | `~/.openclaw/policies/skillseal-guard.ts` | same | `before_tool_call` |

Blocking hooks are written as `skillseal hook ... || exit 2` for `sh` and `cmd.exe`, and as `& 'skillseal' hook ...; if (-not $?) { exit 2 }` for PowerShell (see the [Windows table](GETTING-STARTED.md#step-4-connect-skillseal-to-your-agent)). Claude Code hooks also set `"onFailure": "block"`, and on Windows they use exec form. The OpenCode plugin throws on any error. So when skillseal crashes or is missing, the agent is blocked too (fail closed). For Copilot and Claude a `SessionStart` hook also tells the agent why tools are blocked.

The [test suite](tests/test_hooks_install.py) runs the written hook commands in the real shells (`sh` on macOS and Linux; `cmd.exe`, Windows PowerShell 5.1, `pwsh` and exec form on Windows) for an unsigned skill, a signed skill and a missing binary.

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
| `mode` | `enforce` blocks, `warn` shows the problem but allows, `audit` only logs to `~/.cache/skillseal/audit.jsonl`. |
| `trusted_signers` | `sigstore` (identity + issuer), `certificate` (chain of PEM files) or `public_key` (EC PEM). Relative paths are relative to the policy file. |
| `skill_roots` | Extra folders to search for skills. |
| `allow_repo_signers` | Let a repository's `.skillseal/policy.json` add signers. Default `false`. |
| `revoked_skills` | Object mapping lowercase `skillseal digest` SHA256 content identifiers to nonempty incident reasons. Default `{}`. Only the authoritative policy supplies these denials; repository layers cannot add or clear them. |

Sigstore entries can also set `github_workflow` to an exact caller workflow URL.
For shared workflows, `identity` is the reusable workflow URI and
`github_workflow` is your caller URI. Verification checks the caller's signed
Fulcio Build Config URI extension after cryptographic verification. Missing or
mismatched extensions fail. `init --github-workflow CALLER --reusable-workflow SHARED`
creates this pair. Do not trust a cross-repository shared identity without a
caller restriction. Older Skillseal versions do not enforce this field; upgrade
verifiers before adopting shared-workflow signing.

Where policies are read from:

1. System: `/etc/skillseal/policy.json` (Windows: `%ProgramData%\skillseal\policy.json`). If it exists, it wins.
2. User: `$SKILLSEAL_POLICY` or `~/.config/skillseal/policy.json` (uses `XDG_CONFIG_HOME` when set).
3. Repository: `.skillseal/policy.json` (create with `skillseal init --scope repo`). A repository can only add `skill_roots`. It can never change the mode, and it can only add signers when the system or user policy sets `allow_repo_signers: true`. Without a system or user policy nothing is trusted, so everything is blocked.

### What verification checks

For each skill folder (a folder with `SKILL.md`):

* `SKILL.md` and `skill.oms.sig` exist and are normal files.
* No symlinks and no special files anywhere in the folder; at most 2000 files and 64 MiB.
* The signature uses OMS per-file hashing with sha256, blake2 or blake3 and `allow_symlinks: false`.
* No file exists under a path that the signature chose to ignore. OMS ignores `.github/`, `.gitignore` and `.gitattributes` by default; skillseal signs them, and for a third-party signature it rejects any file hidden there.
* The signature is valid for one of the trusted signers, and the folder contains **exactly** the signed files with the signed hashes. No extra, missing or changed files.

Note: `model-signing` on its own skips `.github/`, `.gitignore` and `.gitattributes` while verifying, even when the signer hashed them. skillseal passes an explicit hashing config so these files are always checked.

Good results are cached in `~/.cache/skillseal/verified.json`, keyed by the policy, the signature, configured key/certificate file contents, and the hash of every file. Content revocations are checked before cache hits. Removing a signer or changing its trust file invalidates its old approvals. Every check still hashes local skill files; this is not constant-time verification.

### Certificate trust and operating-system stores

Skillseal deliberately requires explicit certificate-chain files for certificate
signers; it does not automatically trust all certificates in an OS store.
Native stores differ across Windows, macOS, Linux distributions, and Python
builds. A TLS trust anchor is not automatically an authorized skill publisher.

The GitHub action supports `signing-method: key` or `certificate` with PEM
credentials passed explicitly from GitHub secrets. The reusable approval
workflow defaults to `key`; the composite action defaults to `sigstore` for
compatibility. Organization approval policies authorize the key/anchor, not the
GitHub workflow. See [setup](APPROVAL.md#configure-the-organization-approval-authority).

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

See [emergency revocation](APPROVAL.md#emergency-trust-revocation) for content
denials and signer removal. These are local authorization decisions, not a claim
that a CA has revoked a certificate.

### Honest limits

skillseal raises the bar a lot, but it is not a sandbox:

* **A user who controls their machine can remove the hooks.** skillseal protects people and teams against poisoned skills, not against themselves. See [Hooks that users cannot switch off](APPROVAL.md#hooks-that-users-cannot-switch-off).
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

```text
skillseal demo                         # isolated embedded signature demonstration
skillseal setup      [--bundle TEAM.zip] [--agent NAME] [--project DIR] [--yes]
skillseal setup organization [--name NAME] [--repository OWNER/REPO] [--branch main]
                            [--upload-secret] [--project DIR] [--yes]
skillseal setup enforce [--agent NAME] [--project DIR] [--yes]
skillseal init       [--scope user|repo] [--mode enforce|warn|audit] [--github-workflow REF] [--identity ID --issuer URL]
                     [--reusable-workflow REF] [--public-key PEM] [--certificate-chain PEM ...] [--force]
skillseal check      [--agent NAME ...] [--cwd DIR] [--policy FILE] [--json] [--no-cache]
skillseal install    AGENT... [--scope project|user] [--project DIR] [--exe PATH]
skillseal uninstall  AGENT... [--scope project|user] [--project DIR]
skillseal sign       DIR... (--scan CMD | --no-scan) [--method sigstore|key|certificate]
                     [--private-key PEM] [--signing-certificate PEM] [--certificate-chain PEM ...]
skillseal scan       DIR... [--fail-on LOW|MEDIUM|HIGH]
skillseal verify     DIR... [--policy FILE] [--json] [--no-cache]
skillseal digest     DIR...             # content identifiers for revoked_skills
skillseal hook       AGENT [EVENT]      # called by the agent, reads the hook JSON on stdin
```

`AGENT` is one of `claude`, `copilot`, `codex`, `gemini`, `opencode`, `openclaw`. `install` and `uninstall` default to `--scope project`; on a developer machine use `--scope user`.

Guided setup defaults to Copilot and supports the five nonexperimental agents.
See the [onboarding walkthrough](GETTING-STARTED.md#five-minute-setup).
It never treats an imported package's self-declared organization or checksum as
independent proof of identity; accepting it grants authority to its public key.
`--yes` explicitly authorizes that trust and the displayed changes.

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

A tag `v*` runs the [release workflow](.github/workflows/release.yml): it builds the binaries on Windows, Linux and macOS, tests each one (key and Sigstore signing, tamper detection, and on Windows `install.ps1` plus a hook in PowerShell 5.1), and publishes them with `SHA256SUMS.txt` and build provenance.
