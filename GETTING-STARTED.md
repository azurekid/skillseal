# Getting started

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

1. [Install skillseal](#step-1-install-skillseal)
2. [Set your trust policy](#step-2-tell-skillseal-whom-to-trust)
3. [Check your existing skills](#step-3-see-what-your-agents-can-load-today)
4. [Connect your agent](#step-4-connect-skillseal-to-your-agent)
5. [Test and enable blocking](#step-5-test-it-then-switch-on-blocking)

Need help? See [When something is blocked](#when-something-is-blocked) or [Remove skillseal](#remove-skillseal-again).

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

To keep using the current bash or zsh terminal instead, run:

```bash
export PATH="$HOME/.local/bin:$PATH"
skillseal --version
```

That is it. Continue with **Step 2** below.

Good to know:

* Update: close your AI agents and run the same install command again. Your trust policy and agent hooks stay.
* The program lives in `~/.local/share/skillseal`, with a link in `~/.local/bin`. The installer configures both bash and zsh, because VS Code may use a different shell than your account default. When your default shell is fish, it configures fish too. Other shells use `~/.profile`; if your shell does not read it, add `~/.local/bin` to its PATH.
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

Choose one route: create a policy with your team's approval workflow, or copy a policy your team already prepared. The [approval guide](APPROVAL.md) explains what your team lead needs to set up.

#### Create a policy

Replace `YOUR-ORG/agent-skills` with your team's repository and use the exact workflow file and branch your team gives you:

```bash
skillseal init --mode audit --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
```

By default, this writes your trust policy here:

| Machine | Policy file |
| --- | --- |
| macOS or Linux | `~/.config/skillseal/policy.json`, for example `/Users/rogier/.config/skillseal/policy.json` on macOS |
| Windows | `%USERPROFILE%\.config\skillseal\policy.json`, for example `C:\Users\rogier\.config\skillseal\policy.json` |

These are user settings, **not files inside your project**. If `SKILLSEAL_POLICY` is set, that variable selects the policy file instead. Otherwise, when `XDG_CONFIG_HOME` is set, the file is in its `skillseal` subfolder. See [policy locations and precedence](REFERENCE.md#the-trust-policy).

We start in **audit** mode: nothing is blocked yet, problems are only written to a log. You switch to blocking in step 5.

#### Use a policy your team gave you

If your team lead sent you a ready `policy.json`, copy it into the location above **instead of running `skillseal init`**.

macOS or Linux (assuming the file is in Downloads):

```bash
mkdir -p "$HOME/.config/skillseal"
cp "$HOME/Downloads/policy.json" "$HOME/.config/skillseal/policy.json"
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\skillseal" | Out-Null
Copy-Item "$env:USERPROFILE\Downloads\policy.json" "$env:USERPROFILE\.config\skillseal\policy.json"
```

These commands use the default locations and replace an existing policy. If you use either environment override above, copy to that location instead. Only use a policy from someone you trust: it decides who may sign your skills. If the policy references a public key or certificate file, get that file too. Relative paths in the policy are relative to the folder containing `policy.json`.

Check the policy's `mode` before continuing. A shared policy may already use `enforce`, which blocks tools as soon as the hooks are connected. To start with logging only, set `"mode": "audit"` before step 4, if your team allows it.

#### Optional: trust NVIDIA's signer too

The examples below recreate the policy with `--force`. Do not run them over a shared team policy unless you intend to replace its settings and signers.

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

### Step 3: See what your agents can load today

Go to a project you work on and run:

```bash
cd ~/code/my-project        # PowerShell: cd $HOME\code\my-project
skillseal check
```

Example output:

```text
   .-------.
   |  S S  |   SKILLSEAL
   |   v   |   Skill signature check
    \     /
     '---'

  Mode     audit
  Policy   ~/.config/skillseal/policy.json
  Signers  1 trusted
  Agents   claude, copilot, codex, gemini, opencode, openclaw

  NEEDS APPROVAL (2)
  ------------------------------------------------------------
  [FAIL] ~/.claude/skills/old-helper
         unsigned
         - no skill.oms.sig
  [FAIL] ~/.claude/skills/.trash/pdf-tool
         unsigned
         - no skill.oms.sig

  VERIFIED (1)
  ------------------------------------------------------------
  [OK] ~/code/my-project/.github/skills/deploy
         verified | signer: approval workflow

  Summary: 3 skills | 1 verified | 2 not approved
  Audit mode: configured agent guards do not block these skills.
  Next: remove unapproved skills or ask your team lead to sign them.
```

Skills that need attention come first. Home paths are shortened to `~`; verification reasons stay visible. Use `skillseal check --json` for the full, unchanged machine-readable results without the banner.

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

## When something is blocked

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
