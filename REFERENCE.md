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

Good results are cached in `~/.cache/skillseal/verified.json`, keyed by the policy, the signature and the hash of every file. So a hook normally answers in milliseconds, and any change to any file means a new full check.

### Honest limits

skillseal raises the bar a lot, but it is not a sandbox:

* **A user who controls their machine can remove the hooks.** skillseal protects people and teams against poisoned skills, not against themselves. See [Hooks that users cannot switch off](APPROVAL.md#hooks-that-users-cannot-switch-off).
* **Malicious repositories do not bring the guard.** That is why you install with `--scope user`.
* **Standalone builds** are made with PyInstaller for Windows x64, macOS arm64 and Linux x64 (glibc 2.35+). They are not Authenticode or Apple Developer ID signed; integrity comes from the SHA256 checksums and GitHub build provenance.
* **Copilot hook timeouts fail open** (documented by GitHub). The check is cached and the timeout is 60 seconds, but a hook that hangs lets the call through.
* **Gemini CLI treats exit code 1 as a warning.** skillseal never uses exit 1 to block there; it returns `{"decision":"deny"}`.
* **File permissions are not signed.** OMS hashes file content, not the executable bit.
* **Only skill folders are covered.** Single-file commands such as `.claude/commands/*.md`, and instruction files such as `AGENTS.md` and `CLAUDE.md`, are not. Scan those with a scanner.
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
| [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner), [Snyk agent-scan](https://github.com/snyk/agent-scan), [SkillVenom](https://github.com/azurekid/AgentTrap) | Static scanners for skills and agent files | Scanning only, no signing, no enforcement |
| [Trail of Bits mcp-context-protector](https://github.com/trailofbits/mcp-context-protector) | Trust-on-first-use pinning for MCP servers | MCP only, not skills, no central approval |
| Claude Code plugin marketplaces | `sha` pinning of plugin sources | Pinning at install time only, no signature, no check at load time |

skillseal reuses OMS and adds the missing parts: a trust policy, stricter verification, a scan gate, and enforcement through each agent's own hook system.

### Command reference

```text
skillseal init       [--scope user|repo] [--mode enforce|warn|audit] [--github-workflow REF] [--identity ID --issuer URL]
                     [--public-key PEM] [--certificate-chain PEM ...] [--force]
skillseal check      [--agent NAME ...] [--cwd DIR] [--policy FILE] [--json] [--no-cache]
skillseal install    AGENT... [--scope project|user] [--project DIR] [--exe PATH]
skillseal uninstall  AGENT... [--scope project|user] [--project DIR]
skillseal sign       DIR... (--scan CMD | --no-scan) [--method sigstore|key|certificate]
                     [--private-key PEM] [--signing-certificate PEM] [--certificate-chain PEM ...]
skillseal verify     DIR... [--policy FILE] [--json] [--no-cache]
skillseal hook       AGENT [EVENT]      # called by the agent, reads the hook JSON on stdin
```

`AGENT` is one of `claude`, `copilot`, `codex`, `gemini`, `opencode`, `openclaw`. `install` and `uninstall` default to `--scope project`; on a developer machine use `--scope user`.

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
