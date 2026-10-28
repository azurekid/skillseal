# skillseal

**Your AI agent only uses skills that your team approved. Everything else is blocked.**

A skill is a folder with a `SKILL.md` file (and sometimes scripts). Agents like Claude Code, GitHub Copilot, Codex, Gemini CLI and OpenCode load skills automatically from folders like `.claude/skills` or `~/.agents/skills`. Anybody who can put a folder there can steer your agent.

skillseal works in two parts:

* **Approve (once, in CI):** a GitHub workflow scans each skill and, if it is clean, signs it. The signature file `skill.oms.sig` is stored next to `SKILL.md`.
* **Check (every time, on your machine):** a small hook inside your agent checks every skill the agent can load. Is it signed by your team, and is no file changed, added or removed since signing? If not, the agent cannot use any tool until you fix it.

It is open source, works on macOS, Linux and Windows, and needs no server, no MDM and no extra license.

**Contents**

* [Part 1: Set up your developer machine](#part-1-set-up-your-developer-machine) (10 minutes)
  * [VS Code](#vs-code) · [GitHub Copilot CLI](#github-copilot-cli) · [Claude Code](#claude-code) · [Codex CLI](#codex-cli) · [Gemini CLI](#gemini-cli) · [OpenCode](#opencode) · [OpenClaw](#openclaw-experimental)
* [Part 2: When something is blocked](#part-2-when-something-is-blocked)
* [Part 3: For the team lead, approve skills](#part-3-for-the-team-lead-approve-skills)
* [Part 4: Reference](#part-4-reference)

---

## Part 1: Set up your developer machine

You do this once per machine. After that it works for every project you open.

On Windows, `~` in this guide means your profile folder `%USERPROFILE%` (for example `C:\Users\you`). So `~/.copilot/hooks` is `C:\Users\you\.copilot\hooks`. The `skillseal` commands are the same in PowerShell, cmd and bash. Where a step is different on Windows, a PowerShell version is shown.

### Step 1: Install skillseal

Pick one option. **You do not need Python** for options A and B.

| Your machine | Use |
| --- | --- |
| Windows | [A. Windows, no Python](#a-windows-no-python-no-admin-rights) |
| macOS (Apple silicon) or Linux x64, no Python | [B. macOS or Linux, no Python](#b-macos-or-linux-no-python) |
| Any machine with Python 3.10+ | [C. With Python](#c-with-python) |

#### A. Windows, no Python, no admin rights

Open **PowerShell** (not as administrator) and run:

```powershell
irm https://raw.githubusercontent.com/azurekid/skillseal/main/install.ps1 | iex
```

The script downloads `skillseal-windows-x64.zip` from the [latest release](https://github.com/azurekid/skillseal/releases/latest), checks its SHA256 checksum, unpacks it to `%LOCALAPPDATA%\Programs\skillseal` and adds that folder to **your user** `PATH`. Nothing is installed for other users and no admin rights are needed. Open a new terminal and check:

```powershell
skillseal --version
```

Not allowed to run scripts from the internet? Do the same steps by hand:

1. Download `skillseal-windows-x64.zip` and `SHA256SUMS.txt` from the [releases page](https://github.com/azurekid/skillseal/releases/latest).
2. Check the hash. The output must match the line for the zip in `SHA256SUMS.txt`:
   ```powershell
   (Get-FileHash .\skillseal-windows-x64.zip -Algorithm SHA256).Hash
   ```
3. Unpack the zip. Move the `skillseal` folder to `%LOCALAPPDATA%\Programs\skillseal`.
4. Add that folder to your PATH: start menu, search **"Edit environment variables for your account"**, select `Path`, **Edit**, **New**, paste `%LOCALAPPDATA%\Programs\skillseal`, **OK**. This is a per-user setting and needs no admin rights.
5. Open a new terminal and run `skillseal --version`.

Or, when you have the zip already (for example on an offline machine), run the script from a copy of this repository: `.\install.ps1 -ZipPath .\skillseal-windows-x64.zip`.

Good to know on Windows:

* The x64 build also runs on Windows 11 on Arm (through x64 emulation).
* `skillseal.exe` is not signed with an Authenticode certificate. On most machines that is no problem when you start it from a terminal. If your company blocks unsigned programs (Smart App Control, AppLocker or WDAC), ask IT to allow it, for example by file hash or by folder, or use option C.
* Each release has [build provenance](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations): GitHub can prove that the zip was built from this repository by the release workflow. With the [GitHub CLI](https://cli.github.com) installed: `gh attestation verify skillseal-windows-x64.zip --repo azurekid/skillseal`.
* Update: run the same install command again. Close your AI agents first, because they use `skillseal.exe`.

#### B. macOS or Linux, no Python

Open **Terminal** and paste this one command:

```bash
curl -fsSL https://raw.githubusercontent.com/azurekid/skillseal/main/install.sh | sh
```

The installer detects your machine, downloads the right build from the [latest release](https://github.com/azurekid/skillseal/releases/latest), checks its SHA256 checksum and installs it for **your user**. It also sets up your shell PATH (bash, zsh or fish). No Python, `sudo`, manual unpacking or copying files.

**Open a new terminal**, then check:

```bash
skillseal --version
```

That is it. Continue with **Step 2** below.

Good to know:

* Update: close your AI agents and run the same install command again. Your trust policy and agent hooks stay.
* The program lives in `~/.local/share/skillseal`, with a link in `~/.local/bin`. PATH setup is saved in your shell config. Other shells use `~/.profile`; if your shell does not read it, add `~/.local/bin` to its PATH.
* Supported builds: macOS on Apple silicon and Linux x64 with glibc 2.35 or newer (for example Ubuntu 22.04 or Debian 12). Intel Macs and other systems: use option C.
* The installer needs `curl`, `tar`, and either `shasum` or `sha256sum`. If one is missing, it stops with a clear message.
* Prefer to read the script first? Download [install.sh](install.sh), inspect it, then run `sh install.sh`. To install a specific release: `sh install.sh v0.2.0`.

#### C. With Python

You need Python 3.10 or newer. Install with [pipx](https://pipx.pypa.io) or [uv](https://docs.astral.sh/uv/):

```bash
pipx install git+https://github.com/azurekid/skillseal
# or
uv tool install git+https://github.com/azurekid/skillseal
```

Check that it works with `skillseal --version`. If the command is not found, run `pipx ensurepath` (or `uv tool update-shell`) and open a new terminal.

### Step 2: Tell skillseal whom to trust

Your team lead gives you the name of the approval workflow (see [Part 3](#part-3-for-the-team-lead-approve-skills)). Run:

```bash
skillseal init --mode audit --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
```

This writes your trust policy to `~/.config/skillseal/policy.json` (on Windows: `%USERPROFILE%\.config\skillseal\policy.json`). We start in **audit** mode: nothing is blocked yet, problems are only written to a log. You switch to blocking in step 5.

Optional: also trust the official [NVIDIA verified skills](https://github.com/NVIDIA/skills):

```bash
curl -fsSLO https://raw.githubusercontent.com/NVIDIA/skills/main/nv-agent-root-cert.pem
skillseal init --force --mode audit \
  --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main \
  --certificate-chain "$PWD/nv-agent-root-cert.pem"
```

In PowerShell:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/NVIDIA/skills/main/nv-agent-root-cert.pem -OutFile nv-agent-root-cert.pem
skillseal init --force --mode audit `
  --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main `
  --certificate-chain "$PWD\nv-agent-root-cert.pem"
```

Did your team lead give you a ready `policy.json` file instead? Just copy it to the path above.

### Step 3: See what your agents can load today

Go to a project you work on and run:

```bash
cd ~/code/my-project        # PowerShell: cd $HOME\code\my-project
skillseal check
```

Example output:

```text
policy: /home/you/.config/skillseal/policy.json  mode: audit  signers: 1
agents: claude, copilot, codex, gemini, opencode, openclaw  skills found: 3
[OK  ] /home/you/code/my-project/.github/skills/deploy  (verified)  signer: approval workflow
[FAIL] /home/you/.claude/skills/old-helper  (unsigned)
       - no skill.oms.sig
[FAIL] /home/you/.claude/skills/.trash/pdf-tool  (unsigned)
       - no skill.oms.sig
```

Clean up every `[FAIL]` line before you go to enforce mode. For each one, either delete the folder, or ask your team lead to approve the skill. Watch out for hidden folders such as `~/.claude/skills/.trash`: they are checked too. Use `skillseal check --agent copilot` to only look at one agent.

### Step 4: Connect skillseal to your agent

Pick the tools you use below. Always use `--scope user`: then the guard is active for **every** project on this machine, including repositories you just cloned. (A project install only lives inside one repository, and a malicious repository will not bring it.)

`skillseal install` merges into the existing config. Your own hooks and settings stay. Running it twice does not add things twice. It writes the full path of `skillseal` into the hook, so it also works when the agent is started from a desktop icon without your shell `PATH`. If you move or reinstall skillseal in another folder later, run the install command again.

On Windows, each agent runs hooks with a different shell. skillseal writes the command in the right form for each one, so you do not need Git Bash or WSL:

| Agent | Runs hooks on Windows with | What skillseal writes |
| --- | --- | --- |
| Copilot (CLI and VS Code) | PowerShell | `& 'C:\...\skillseal.exe' hook copilot preToolUse; if (-not $?) { exit 2 }` |
| Claude Code | no shell (exec form) | `"command": "C:\\...\\skillseal.exe", "args": ["hook", "claude", "PreToolUse"]` |
| Codex CLI | `cmd.exe` | `"C:\...\skillseal.exe" hook codex PreToolUse \|\| exit 2` |
| Gemini CLI | PowerShell (`pwsh`, or Windows PowerShell 5.1) | `& 'C:\...\skillseal.exe' hook gemini BeforeTool; if (-not $?) { exit 2 }` |
| OpenCode | no shell (the plugin starts `skillseal.exe` directly) | path in `skillseal.js` |

#### VS Code

VS Code agent hooks are in **Preview**. The hooks that run depend on the agent you pick in the chat view (the "session target"):

| You pick in VS Code chat | Install this |
| --- | --- |
| **Copilot** (recommended) | `skillseal install copilot --scope user` |
| **Claude** | `skillseal install claude --scope user` |
| **Codex** | `skillseal install codex --scope user` |
| **Local** (legacy) | Not supported. Switch to the Copilot target. |

For the Copilot target:

```bash
skillseal install copilot --scope user
```

This writes `~/.copilot/hooks/skillseal.json`. Then:

1. Restart VS Code (or run **Developer: Reload Window**).
2. Open the chat view and choose the **Copilot** session target.
3. Type `/hooks` in chat. You should see `skillseal` for `sessionStart` and `preToolUse`.

The VS Code settings `chat.useHooks` and `chat.hookFilesLocations` do not change the Copilot target, so you do not need them.

#### GitHub Copilot CLI

```bash
skillseal install copilot --scope user
```

This writes `~/.copilot/hooks/skillseal.json` (or `$COPILOT_HOME/hooks/` when you set `COPILOT_HOME`). Start a new `copilot` session. Nothing else to do.

Why user scope? Copilot CLI only loads hooks from a repository (`.github/hooks/*.json`) when you trust that folder, and only from the root of a git repository. User hooks always load.

#### Claude Code

```bash
skillseal install claude --scope user
```

This adds hooks to `~/.claude/settings.json` for `SessionStart`, `UserPromptSubmit`, `UserPromptExpansion` and `PreToolUse`. Then:

1. Start `claude` in your project.
2. Accept the workspace trust dialog for the folder. Claude Code holds back **all** hooks, also the ones in your own user settings, until you trust the folder.
3. Type `/hooks`. You should see the skillseal hooks with the source "user settings".

Note: in `claude -p` (headless) runs Claude Code treats the folder as trusted, so the hooks run directly.

Use Claude Code 2.1.295 or later. The blocking hooks set `"onFailure": "block"`, so a crash or a timeout of the hook also blocks; older versions ignore that setting. On Windows the hooks start `skillseal.exe` directly (exec form), so it does not matter if Claude Code uses Git Bash or PowerShell.

#### Codex CLI

```bash
skillseal install codex --scope user
```

This writes `~/.codex/hooks.json`. Start `codex`. Codex asks you to review new hooks once: open `/hooks`, check that the command contains `skillseal hook codex PreToolUse`, and approve it.

#### Gemini CLI

```bash
skillseal install gemini --scope user
```

This adds a `BeforeTool` hook to `~/.gemini/settings.json`. Start `gemini`. When a project has its own hooks, Gemini shows a trust warning once.

#### OpenCode

```bash
skillseal install opencode --scope user
```

This writes the plugin `~/.config/opencode/plugins/skillseal.js`. OpenCode loads plugins only at startup, so **quit and restart OpenCode**. The plugin runs before every tool call. When the check fails, or when `skillseal` cannot run at all, the tool call is stopped. OpenCode runs the plugin itself; you do not need to install anything extra.

#### OpenClaw (experimental)

```bash
skillseal install openclaw --scope user
```

This writes `~/.openclaw/policies/skillseal-guard.ts` and prints a `plugins.load.paths` snippet. Add that snippet to your OpenClaw config. The OpenClaw plugin API is experimental and this integration is **not tested** yet. Skillseal assumes the workspace is `~/.openclaw/workspace`; set `SKILLSEAL_OPENCLAW_WORKSPACE` if yours is different.

#### Several tools at once

```bash
skillseal install copilot claude codex gemini opencode --scope user
```

### Step 5: Test it, then switch on blocking

1. Use your agent for a few days in audit mode. Problems are logged in `~/.cache/skillseal/audit.jsonl`.
2. Run `skillseal check` again until there are no `[FAIL]` lines.
3. Open `~/.config/skillseal/policy.json` and change `"mode": "audit"` to `"mode": "warn"`. Now the agent shows the problem but still continues.
4. When that is quiet too, change it to `"mode": "enforce"`. Now the agent is blocked.

Quick test that blocking works (in enforce mode). `.agents/skills` is read by Copilot, Codex, Gemini and OpenCode; for Claude Code use `.claude/skills`:

```bash
mkdir -p ~/code/my-project/.agents/skills/test-unsigned
echo "# test" > ~/code/my-project/.agents/skills/test-unsigned/SKILL.md
```

In PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\code\my-project\.agents\skills\test-unsigned" | Out-Null
Set-Content "$HOME\code\my-project\.agents\skills\test-unsigned\SKILL.md" "# test"
```

Ask your agent to run any command, like `list the files in this folder`. It should refuse with a skillseal message. Then remove the test folder (PowerShell: `Remove-Item -Recurse -Force <folder>`):

```bash
rm -rf ~/code/my-project/.agents/skills/test-unsigned
```

### Remove skillseal again

First remove the hooks. `uninstall` only removes the skillseal entries; your other hooks and settings stay:

```bash
skillseal uninstall copilot claude codex gemini opencode --scope user
```

Then remove the program:

| Installed with | Remove with |
| --- | --- |
| A. Windows | `Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Programs\skillseal"`, then remove that folder from your user `Path` ("Edit environment variables for your account") |
| B. macOS or Linux | `rm -rf ~/.local/share/skillseal ~/.local/bin/skillseal`. Optionally remove the `# skillseal` PATH entry from your shell config. |
| C. Python | `pipx uninstall skillseal` or `uv tool uninstall skillseal` |

Your policy (`~/.config/skillseal`) and cache (`~/.cache/skillseal`) stay. Delete those folders too if you want.

---

## Part 2: When something is blocked

In enforce mode your agent shows a message like this, and cannot use tools:

```text
skillseal: 1 skill not approved (unsigned, changed or untrusted signer):
  - /home/you/code/my-project/.claude/skills/deploy: invalid: approval workflow: changed: SKILL.md
Remove the skill or get it approved and signed. Details: skillseal check
```

What the reasons mean and what to do:

| Message | Meaning | What to do |
| --- | --- | --- |
| `unsigned` / `no skill.oms.sig` | Nobody approved this skill. | Delete the folder, or ask for approval. |
| `changed: SKILL.md` | A file was edited after signing. | `git checkout` the skill folder, or get the new version approved. |
| `added: scripts/x.sh` | A file was added after signing. | Remove the file, or get the new version approved. |
| `removed: ...` | A signed file was deleted. | Restore the file. |
| `<signer name>: ...` with another error | Signed, but not by a signer in your policy (or the signature is broken). | Check your `policy.json`, or ask your team lead. |
| `symlink not allowed` / `not a regular file` | The folder contains a link or a special file. | Replace links by real files and sign again. |
| `no trusted signers configured` | Your policy trusts nobody. | Run [step 2](#step-2-tell-skillseal-whom-to-trust) again. |

Other problems:

| Problem | Fix |
| --- | --- |
| Everything is blocked right after install | You have old or unsigned skills, often in `~/.claude/skills/.trash`. Run `skillseal check` and clean up. |
| Hook does not run in VS Code | Use the **Copilot** session target, reload the window, check `/hooks`. |
| Hook does not run in Claude Code | Accept the folder trust dialog, check `/hooks`. |
| Hook does not run in Codex | Approve the hook in `/hooks`. |
| Hook does not run in OpenCode | Restart OpenCode. The plugin is only loaded at startup. |
| `skillseal: command not found` inside the agent | Run `skillseal install ... --scope user` again from a shell where `skillseal --version` works, or pass `--exe /full/path/to/skillseal`. |
| Windows: `skillseal` is not recognized | Open a **new** terminal after the install (PATH changes only apply to new windows). Check that `%LOCALAPPDATA%\Programs\skillseal` is in your user `Path`. |
| Windows: "This app has been blocked" or "Access is denied" when starting `skillseal.exe` | Your device blocks unsigned programs. Ask IT to allow `skillseal.exe`, or install with Python (option C). |
| Windows: install script says "Cannot replace ..." | An agent is still running `skillseal.exe`. Close VS Code and your agents, then run it again. |
| Windows: `irm ... \| iex` is blocked | Use the manual steps in [option A](#a-windows-no-python-no-admin-rights). |
| You must work right now and cannot wait for approval | Set `"mode": "warn"` in your policy for a moment. Do not forget to set it back. |

---

## Part 3: For the team lead, approve skills

### 1. Create a skills repository

Make one repository (for example `YOUR-ORG/agent-skills`) with one folder per skill:

```text
skills/
  deploy/
    SKILL.md
    scripts/deploy.sh
  code-review/
    SKILL.md
```

### 2. Add the approval workflow

Copy [`examples/approve-skills.yml`](examples/approve-skills.yml) to `.github/workflows/approve-skills.yml`. Do not rename the file later: its name and branch are part of the signing identity. The important part:

```yaml
on:
  push:
    branches: [main]
    paths: ["skills/**"]
permissions:
  contents: write     # commit skill.oms.sig
  id-token: write     # Sigstore keyless signing
jobs:
  sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: seal
        uses: azurekid/skillseal@v0.2.0
        with:
          skills: "skills/*"
          scan: python scan_agents_md.py --fail-on HIGH {path}
      - if: steps.seal.outputs.signed != ''
        run: |
          git config user.name "skillseal[bot]"
          git config user.email "skillseal@users.noreply.github.com"
          git add skills/*/skill.oms.sig
          git commit -m "Sign approved skills: ${{ steps.seal.outputs.signed }}"
          git push
```

The full example also downloads the scanner. Pin the action and the scanner to a commit SHA in production.

On every push to `main` the workflow:

1. runs your scanner on each skill folder (`{path}` is replaced by the folder; exit code 0 means clean),
2. signs every clean skill with Sigstore, without any key to manage: the identity of the signature **is this workflow**,
3. the last step commits `skill.oms.sig` next to each `SKILL.md`.

Any scanner works, for example [SkillVenom](https://github.com/azurekid/AgentTrap), [Cisco skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) or [Snyk agent-scan](https://github.com/snyk/agent-scan). If the scanner fails, the skill is not signed. Want to sign without a scanner? You must say so with `allow-no-scan: true`.

A signature proves **who approved** a skill and that it **did not change**. It does not prove the skill is safe. That is the job of the scan, and of a human review before merge.

### 3. Give your developers the trust command

```bash
skillseal init --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
```

Or share the resulting `~/.config/skillseal/policy.json` file. It is small and contains no secrets, so you can put it in dotfiles, a devcontainer, an onboarding script or a base image.

### 4. Get the skills to developers

Developers copy or clone the signed skill folders into one of the skill folders of their agent (see the [table below](#where-each-agent-loads-skills)), including `skill.oms.sig`. Projects can also commit signed skills in `.github/skills` or `.claude/skills`.

### Sign without GitHub Actions

```bash
skillseal sign --scan "python scan_agents_md.py --fail-on HIGH" skills/deploy     # Sigstore, opens a browser login
skillseal sign --no-scan --method key --private-key key.pem skills/deploy        # your own EC key
skillseal sign --scan "..." --method certificate --private-key k.pem \
  --signing-certificate leaf.pem --certificate-chain ca.pem skills/deploy        # your own PKI
```

Developers then trust the key with `skillseal init --public-key key.pub` or the CA with `skillseal init --certificate-chain ca.pem`.

### Hooks that users cannot switch off

A user who controls their own machine can always remove a user hook. If you need more, place the policy and hook at system level (needs admin rights once, no MDM):

* skillseal reads `/etc/skillseal/policy.json` (Windows: `%ProgramData%\skillseal\policy.json`) first. When it exists, it wins over the user policy.
* GitHub Copilot CLI loads **policy hooks** from `/etc/github-copilot/policy.d/*.json` (Windows: `C:\ProgramData\GitHub\Copilot\policy.d\`). They load before all other hooks and `disableAllHooks` cannot turn them off. On macOS and Linux the file must be owned by root and not writable by group or others. Copy the content of `~/.copilot/hooks/skillseal.json` there.
* Claude Code has managed settings for the same purpose; put the same skillseal hooks in there.

---

## Part 4: Reference

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

Blocking hooks are written as `skillseal hook ... || exit 2` for `sh` and `cmd.exe`, and as `& 'skillseal' hook ...; if (-not $?) { exit 2 }` for PowerShell (see the [Windows table](#step-4-connect-skillseal-to-your-agent)). Claude Code hooks also set `"onFailure": "block"`, and on Windows they use exec form. The OpenCode plugin throws on any error. So when skillseal crashes or is missing, the agent is blocked too (fail closed). For Copilot and Claude a `SessionStart` hook also tells the agent why tools are blocked.

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

* **A user who controls their machine can remove the hooks.** skillseal protects people and teams against poisoned skills, not against themselves. See [Hooks that users cannot switch off](#hooks-that-users-cannot-switch-off).
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

## License

Apache-2.0
