# skillseal

**Only let your AI agents load skills that were approved and signed.**

AI agent skills (`SKILL.md` folders with scripts and references) are executable instructions. Anyone who can drop a folder in `.claude/skills`, `.github/skills` or `~/.agents/skills` can steer your agent. skillseal makes sure that every skill an agent can load was:

1. **scanned** by a scanner you choose, before approval,
2. **signed** by an identity you trust (a GitHub workflow via Sigstore, a certificate chain, or a key), and
3. **unchanged** since signing (every file is hashed, nothing may be added, removed or edited),

and it **blocks the agent** (fail closed) when one of these is not true. It works with Claude Code, GitHub Copilot (CLI and VS Code), OpenAI Codex CLI, Gemini CLI and (experimental) OpenClaw. It needs no MDM, no server and no extra license.

```text
approve (CI)                               run (every developer machine)
------------                               -----------------------------
skill folder                               agent starts / calls a tool
   |                                          |
   v                                          v
scanner (exit 0 = clean)  --fail-->  stop  skillseal hook (agent's own hook system)
   |                                          |
   v                                          v
Sigstore keyless signing                   discover every skill the agent can load
(identity = your workflow)                    |
   |                                          v
   v                                       verify OMS signature + exact file manifest
skill.oms.sig committed next to SKILL.md      |              |
                                           all OK         anything else
                                              |              |
                                           allow          block (exit 2 / deny)
```

## Why this exists (prior art)

Before building this we checked what already exists (October 2026):

| Project | What it does | What is missing for this use case |
| --- | --- | --- |
| [OpenSSF Model Signing (OMS)](https://github.com/sigstore/model-transparency), `model-signing` | Signs a whole directory: a Sigstore bundle with every file's digest | No agent integration, no trust policy, default config skips `.github/` |
| [NVIDIA verified skills](https://github.com/NVIDIA/skills) | Ships skills with `skill.oms.sig` (OMS) and a root certificate | Verification is manual (`model_signing verify`), nothing enforces it at runtime |
| [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner), [Snyk agent-scan](https://github.com/snyk/agent-scan), [SkillVenom](https://github.com/azurekid/AgentTrap) | Static scanners for skills and agent files | Scanning only, no signing or runtime enforcement |
| [Trail of Bits mcp-context-protector](https://github.com/trailofbits/mcp-context-protector) | Trust-on-first-use pinning for MCP servers | MCP only, not skills, no central approval |
| Claude Code plugin marketplaces | `sha` pinning of plugin sources | Pinning at install time only, no signature, no check at load time |

skillseal reuses the OMS format and the `model-signing` library (so NVIDIA's signed skills verify as they are) and adds the missing parts: a trust policy, stricter verification, a scan gate, and enforcement through each agent's own hook system.

## Quick start

```bash
pipx install git+https://github.com/azurekid/skillseal      # or: uv tool install git+https://github.com/azurekid/skillseal

# 1. Trust your approval workflow (and optionally NVIDIA)
skillseal init --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
#   add --certificate-chain nv-agent-root-cert.pem to also trust NVIDIA verified skills

# 2. See what your agents can load today
skillseal check

# 3. Turn on enforcement for your agents (user scope = every project on this machine)
skillseal install claude copilot codex gemini --scope user
```

From then on, while any skill an agent can load is unsigned, changed, or signed by someone you do not trust, the agent cannot call tools (and Claude Code cannot expand prompts or slash commands). The agent shows why:

```text
skillseal: 1 skill not approved (unsigned, changed or untrusted signer):
  - /work/repo/.claude/skills/deploy: invalid: approval workflow: changed: SKILL.md; added: scripts/x.sh
Remove the skill or get it approved and signed. Details: skillseal check
```

Tip: start with `--mode audit` (only logs) or `--mode warn` (shows the problem, allows), then switch to `enforce`.

## Approving skills

Add [`examples/approve-skills.yml`](examples/approve-skills.yml) to the repository that holds your skills. On every push to `main` it scans each skill folder, signs the clean ones with Sigstore keyless signing, and commits `skill.oms.sig` next to `SKILL.md`. The signing identity is the workflow itself:

```text
identity: https://github.com/YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
issuer:   https://token.actions.githubusercontent.com
```

The action:

```yaml
permissions:
  contents: write
  id-token: write
steps:
  - uses: actions/checkout@v4
  - uses: azurekid/skillseal@v0.1.0
    with:
      skills: "skills/*"
      scan: python scan_agents_md.py --fail-on HIGH {path}   # any scanner: exit 0 = clean
```

Any scanner works: skillseal runs the command, replaces `{path}` with the skill folder (or appends it), and refuses to sign on a non-zero exit code. Without a `scan` you have to pass `allow-no-scan: true` on purpose. Skills whose existing signature still matches are skipped.

You can also sign locally or with your own PKI:

```bash
skillseal sign --scan "python scan_agents_md.py --fail-on HIGH" skills/deploy        # Sigstore (browser login)
skillseal sign --no-scan --method key --private-key key.pem skills/deploy           # EC key
skillseal sign --scan "..." --method certificate --private-key k.pem \
  --signing-certificate leaf.pem --certificate-chain ca.pem skills/deploy           # X.509
```

A signature proves **who approved** a skill and that **it did not change**. It does not prove the skill is safe; that is the job of the scan (and a human review) before signing.

## The trust policy

`skillseal init` writes a JSON policy. Example ([`examples/policies/user-policy.json`](examples/policies/user-policy.json)):

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
| `mode` | `enforce` blocks, `warn` allows and shows the problem, `audit` only logs to `~/.cache/skillseal/audit.jsonl`. |
| `trusted_signers` | `sigstore` (identity + issuer), `certificate` (chain of PEM files) or `public_key` (EC PEM). Relative paths resolve from the policy file. |
| `skill_roots` | Extra folders to search for skills. |
| `allow_repo_signers` | Let a repository's `.skillseal/policy.json` add signers. Default `false`. |

Where policies are read from:

1. System: `/etc/skillseal/policy.json` (Windows: `%ProgramData%\skillseal\policy.json`). If present, it wins.
2. User: `$SKILLSEAL_POLICY` or `~/.config/skillseal/policy.json` (honors `XDG_CONFIG_HOME`).
3. Repository: `.skillseal/policy.json`. A repository can only add `skill_roots`. It can never change the mode, and it can add signers only when the system or user policy sets `allow_repo_signers: true`. Without a system or user policy nothing is trusted, so everything is blocked.

Distributing the policy is one small file: put it in your dotfiles, a devcontainer, an onboarding script or a base image. No device management needed.

## What verification checks

For each skill folder (a folder with `SKILL.md`):

* `SKILL.md` and `skill.oms.sig` exist and are regular files.
* No symlinks and no special files anywhere in the folder; at most 2000 files and 64 MiB.
* The signature uses OMS per-file serialization with sha256, blake2 or blake3 and `allow_symlinks: false`.
* No file exists under a path the signature chose to ignore. OMS ignores `.github/`, `.gitignore` and `.gitattributes` by default; skillseal signs them, and when it verifies a third-party signature it rejects any file hidden there.
* The signature is valid for one of the trusted signers, and the folder contains **exactly** the signed files with the signed digests (no extra, missing or changed files).

Note: `model-signing` on its own skips `.github/`, `.gitignore` and `.gitattributes` while verifying, even when the signer hashed them. skillseal passes an explicit hashing config so these files are always checked.

Successful results are cached in `~/.cache/skillseal/verified.json`, keyed by the policy, the signature and the hash of every file, so a hook normally answers in milliseconds. Any change to any file is a cache miss.

## How enforcement works per agent

`skillseal install <agent> --scope project|user` merges skillseal into the agent's own hook config. Existing hooks and settings are kept, and running it again does not duplicate anything. Blocking hooks are written as `skillseal hook ... || exit 2`, so a crash or a missing `skillseal` binary also blocks.

| Agent | Config written | Blocking events | Notes |
| --- | --- | --- | --- |
| Claude Code | `.claude/settings.json` or `~/.claude/settings.json` | `PreToolUse` (all tools), `UserPromptSubmit`, `UserPromptExpansion` | `SessionStart` tells Claude why tools are blocked. Project hooks need folder trust. |
| GitHub Copilot CLI / VS Code | `.github/hooks/skillseal.json` or `~/.copilot/hooks/skillseal.json` | `preToolUse` | Repository hooks only load in trusted folders; prefer `--scope user`. Hooks are in preview in VS Code. |
| Codex CLI | `.codex/hooks.json` or `~/.codex/hooks.json` | `PreToolUse` | Codex asks you to review new hooks once (`/hooks`). |
| Gemini CLI | `.gemini/settings.json` or `~/.gemini/settings.json` | `BeforeTool` | Answers with `{"decision":"deny"}`. Project hooks show a trust warning once. |
| OpenClaw (experimental, untested) | `~/.openclaw/policies/skillseal-guard.ts` plugin | `before_tool_call` | Plugin API is experimental; add the printed `plugins.load.paths` config. Workspace is assumed at `~/.openclaw/workspace` (override with `SKILLSEAL_OPENCLAW_WORKSPACE`). |

Skills that are injected into the prompt without a tool call (Copilot, Codex, OpenClaw) are covered by the same rule: while any loadable skill fails verification, the agent can do nothing with tools.

Skill folders searched per agent (project folders are searched from the working directory up to the repository root):

| Agent | Project | User |
| --- | --- | --- |
| claude | `.claude/skills` | `~/.claude/skills`, `~/.claude/plugins` |
| copilot | `.github/skills`, `.claude/skills`, `.agents/skills` | `~/.copilot/skills`, `~/.claude/skills`, `~/.agents/skills` |
| codex | `.agents/skills` | `~/.agents/skills`, `/etc/codex/skills` |
| gemini | `.gemini/skills`, `.agents/skills` | `~/.gemini/skills`, `~/.agents/skills`, `~/.gemini/extensions` |
| openclaw | `skills`, `.agents/skills` | `~/.agents/skills`, `~/.openclaw/skills` |

Tested end to end with the GitHub Copilot CLI: with an unsigned skill present and `--allow-all-tools`, the `preToolUse` hook denied the shell call and the agent reported the skillseal message. Real NVIDIA-signed skills verify with their published root certificate, and fail after any edit.

## Honest limits

skillseal raises the bar a lot, but it is not a sandbox. Know these limits:

* **A user who controls their machine can remove the hooks.** skillseal protects users and teams against poisoned skills, not against themselves. For hooks a user cannot switch off, Copilot CLI reads policy hooks from a system directory and Claude Code supports managed settings; place the same skillseal hook there.
* **Malicious repositories do not bring the guard.** Project hooks travel with the repository; use `--scope user` so the guard is active for every repository you open.
* **Copilot hook timeouts fail open** (documented by GitHub). Verification is cached and normally takes milliseconds, and the timeout is set to 60 s, but a hook that hangs lets the call through.
* **Gemini CLI treats exit code 1 as a warning.** skillseal never uses exit 1 to block there; it returns `{"decision":"deny"}`.
* **File permissions are not signed.** OMS hashes file content, not the executable bit.
* **Single-file legacy commands** such as Claude Code `.claude/commands/*.md`, and `AGENTS.md` / `CLAUDE.md` instruction files, are not skill folders and are not covered. Scan them with a scanner.
* **Everything in a skill root is checked**, including folders such as `~/.claude/skills/.trash`. Empty them or move old skills out.
* **The cache is protected by normal file permissions** (`0600`). Someone who can write to your home folder can already change your agent configuration.
* **Sigstore verification** uses the public-good trust root, which `sigstore` downloads and caches (TUF) on first use. `certificate` and `public_key` signers work fully offline.

## Command reference

```text
skillseal init     [--scope user|repo] [--mode enforce|warn|audit] [--github-workflow REF] [--identity ID --issuer URL]
                   [--public-key PEM] [--certificate-chain PEM ...] [--force]
skillseal sign     DIR... (--scan CMD | --no-scan) [--method sigstore|key|certificate]
                   [--private-key PEM] [--signing-certificate PEM] [--certificate-chain PEM ...]
skillseal verify   DIR... [--policy FILE] [--json] [--no-cache]
skillseal check    [--agent NAME ...] [--cwd DIR] [--policy FILE] [--json] [--no-cache]
skillseal install  AGENT... [--scope project|user] [--project DIR] [--exe PATH]
skillseal hook     AGENT [EVENT]        # called by the agent, reads hook JSON on stdin
```

Verify NVIDIA's signed skills:

```bash
curl -fsSLO https://raw.githubusercontent.com/NVIDIA/skills/main/nv-agent-root-cert.pem
skillseal init --certificate-chain nv-agent-root-cert.pem
skillseal verify path/to/NVIDIA/skills/skills/accelerated-computing-cudf
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest -q
```

CI runs the tests on Linux, macOS and Windows, plus a real Sigstore keyless sign and verify round trip through the action.

## License

Apache-2.0
