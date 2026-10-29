# Getting started

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

## Five-minute setup

**Install once using [Step 1](#step-1-install-skillseal), then choose one box below.**
You do not need to edit JSON or generate keys by hand.
The guided commands require **v0.4.0 or newer**.
If `skillseal demo` is not recognized, update your installation first.
The five-minute target assumes installation, GitHub access and any company approvals
are already in place; GitHub workflow wait times are outside Skillseal's control.

### Just trying it

```text
skillseal demo
```

Expected: three `PASS` lines for approved, modified and unsigned skills.
The two signed examples are included in the application. No extra download, key,
GitHub account or settings change is needed. This is signature verification,
not a test of your agent's enforcement.

### Administrator: prepare once for your team

Before starting: create or open a GitHub repository for your approved skills.
Use a checkout you trust, install [GitHub CLI](https://cli.github.com), and run
`gh auth login` with an account allowed to manage that repository's Actions secrets.
Run this **at the root of that checkout**, not inside Skillseal's own source:

```text
skillseal setup organization --upload-secret
```

The wizard detects the GitHub repository, asks for your organization's display
name, and explains the changes before asking for confirmation. It creates:

* A signing workflow in `.github/workflows/approve-skills.yml`, using a reviewed,
  commit-pinned Skillseal action. It runs only on the `main` branch or manually.
* A signed welcome skill in `.agents/skills/skillseal-welcome`.
* A public approval key in `.skillseal/approval.pub`.
* A public **`skillseal-team.zip`** package to send to developers.

It generates the private key for you, saves a protected backup **outside the
repository** under `~/.skillseal-authorities/`, and uploads it to the repository's
`SKILLSEAL_APPROVAL_PRIVATE_KEY` secret. The exact backup path is printed.
Keep that backup secure; never commit or share it. The team ZIP contains no
private key. The displayed fingerprint is the SHA256 of the public-key file.

**Your remaining steps:**

1. Review the generated public files, commit them and push to `main`.
2. In GitHub's **Actions** tab, confirm **Approve skills** succeeds.
   Branch rules must allow its signature commits. If your reviewed branch has a
   different name, pass `--branch YOUR-BRANCH` during setup.
3. Send `skillseal-team.zip` through your trusted company channel. Publish the
   printed fingerprint separately if developers need to verify the sender.

The scan gate is a basic heuristic, not a human reviewer. Protect the signing
branch and require review before merging skill changes. Restrict changes to the
workflow itself, because it can access the approval secret.

For offline preparation or without GitHub CLI, use
`skillseal setup organization --repository OWNER/REPO --name "Your team"`.
It prints how to add the saved key as a GitHub secret later.
Setup never commits, pushes, replaces an existing authority or overwrites an
existing approval secret. If upload fails after preparation, the local public
files and private backup remain; use the backup to add the secret, rather than
rerunning setup to generate another authority.

### Developer: accept the team package once

Get the ZIP **from your administrator through a trusted channel**. Open your
approved-skills project and run the following command. Pass the ZIP itself;
there is no need to unzip it:

```text
skillseal setup --bundle skillseal-team.zip
```

Check the organization and fingerprint, then confirm. A fingerprint inside an
unknown ZIP does not prove its sender. Copilot is the default agent. For another:

```text
skillseal setup --bundle skillseal-team.zip --agent claude
```

Choose `copilot`, `claude`, `codex`, `gemini` or `opencode`; repeat with another
agent to configure multiple agents. OpenClaw remains an advanced, experimental
integration. Setup installs hooks in your **user** settings, preserving other
hooks and backing up changed files. Trust goes in the normal
[user policy folder](#organization-approval-configuration), not the repository.
Existing different policies, keys and IT-managed policies are never replaced.
This guided package format supports one organization P-256 approval key.
Additional external publishers and certificate authorities use the
[advanced policy settings](REFERENCE.md#the-trust-policy).

**Restart your agent.** Check that it loads its Skillseal hooks.
Initially the policy is in **audit mode**: problems are reported, not blocked.
Open or copy your team's approved skill folders, including their `skill.oms.sig`
files, into an [agent-supported location](REFERENCE.md#where-each-agent-loads-skills).
The administrator's welcome example already works in the repository for Copilot,
Codex, Gemini and OpenCode. Claude Code users copy the complete welcome folder
to `.claude/skills/skillseal-welcome` without changing the files.

When checks pass, enable enforcement from your project, then follow
[the host blocking test](#step-5-test-it-then-switch-on-blocking):

```text
skillseal check --agent copilot
skillseal setup enforce
```

Use the same `--agent` when not using Copilot. Enabling enforcement requires an
installed hook configuration and at least one discovered skill, with every
discovered skill verified. It preserves revocations and other policy settings.
The mode is shared by all guards using that user policy, so other projects can
also become blocked. This readiness check cannot prove the host actually runs
hooks; Copilot timeouts can still fail open.

For automation, supply options such as `--name`, `--repository` and `--agent`,
and use `--yes` only after independently approving the authority and changes.

## Manual setup and installation reference

The sections below cover installation, existing policies and advanced setup.
For normal onboarding, install using Step 1 and return to the building blocks above.

1. [Install skillseal](#step-1-install-skillseal)
2. [Set your trust policy](#step-2-tell-skillseal-whom-to-trust)
3. [Check your existing skills](#step-3-see-what-your-agents-can-load-today)
4. [Connect your agent](#step-4-connect-skillseal-to-your-agent)
5. [Test and enable blocking](#step-5-test-it-then-switch-on-blocking)

**Just exploring?** After installing, [try the already-signed starter skills](#try-the-signed-starter-skills-first).
You can see a successful verification without creating keys or changing your
computer's settings.

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

That is it. Return to [Five-minute setup](#five-minute-setup), or use the manual
steps below for an existing policy.

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

### Try the signed starter skills first

1. Download `skillseal-starter.zip` from the
   [release assets](https://github.com/azurekid/skillseal/releases/latest).
   Choose **v0.4.0 or newer**. Alternatively, download this repository using
   **Code > Download ZIP**, extract it, and open its `examples/starter` folder.
2. Extract the starter ZIP and open the extracted folder containing
   `policy.json` in your terminal.
3. If you have the GitHub CLI, you can check the published ZIP's build provenance:
   `gh attestation verify skillseal-starter.zip --repo azurekid/skillseal`.
   The release's `SHA256SUMS.txt` also includes its download checksum.
4. Run this command (the same in PowerShell, macOS, and Linux):

   ```text
   skillseal verify --no-cache --policy policy.json skills/friendly-greeting skills/writing-checklist
   ```

Expected: both skills show `OK` and `Signer: Skillseal starter examples only`.
They are already signed; you do not need a private key or GitHub secret.
The demonstration policy is used **only for this command**. Nothing is copied
into your real policy folder, and no agent hooks are installed.

Want to see a failure? Edit the greeting's `SKILL.md`, save it, and rerun the
command. That skill should now show `INVALID`. Extract a fresh copy to restore it.
See the [starter instructions](examples/starter/README.md) for details.

The starter public-key file, `starter-approval.pub`, has this SHA256 fingerprint:

```text
b22cd994bc688234edaf8df63f23a923101cb5079e23d1dd0c2ee77c1875ad33
```

Check it against this guide obtained from a source you trust:

```bash
# macOS
shasum -a 256 starter-approval.pub
# Linux
sha256sum starter-approval.pub
```

```powershell
# Windows
(Get-FileHash .\starter-approval.pub -Algorithm SHA256).Hash
```

Hexadecimal letter case does not matter. A checksum supplied with an untrusted
download is not independent proof of who published it.
This demo key is not your organization's approval key. Do not copy the demo
policy over your real policy or add demo trust to managed endpoints. For use
in a real agent, have your team review and re-sign the examples with its own
authority. Verification alone does not demonstrate host enforcement.

### Step 2: Tell skillseal whom to trust

**Recommended for teams:** copy a reviewed organization policy and public key
or dedicated certificate anchor. GitHub Actions signs with your organization's
approval authority; developers do not need workflow trust configuration.
The [approval guide](APPROVAL.md#configure-the-organization-approval-authority)
explains the signing setup.

#### Organization approval configuration

Ask your team for **two files**:

| File | What it is |
| --- | --- |
| `policy.json` | The settings that say whose approvals you trust |
| `approval.pub` | Your organization's public approval key; safe to share |

If your team uses certificates, the second file is `approval-ca.pem` instead.
Your team can start from the [public-key policy example](examples/policies/organization-key.json)
or [certificate policy example](examples/policies/organization-certificate.json).
You do not need to edit JSON or run `skillseal init` when your team provides
these files.

**Where is the policy folder?** It is a settings folder on your computer, not
the `examples/policies` folder in this repository:

| Machine | Open this folder |
| --- | --- |
| macOS | Finder > Go > Go to Folder, then enter `~/.config/skillseal` |
| Linux | Your home folder, then `.config/skillseal` (show hidden files if needed) |
| Windows | File Explorer address bar: `%USERPROFILE%\.config\skillseal` |

Create the folder if it does not exist. After copying, it should look like this:

```text
Your home folder/
  .config/
    skillseal/
      policy.json
      approval.pub
```

For example, the Mac location for user `rogier` is
`/Users/rogier/.config/skillseal/`. A policy containing
`"public_key": "approval.pub"` looks for that public key beside `policy.json`.
Do not rename the file to `organization-key.json`: that is the example's name,
not the installed settings filename.

Obtain both files from your team through a trusted channel, not an untrusted
skill's repository. Never copy `approval-private.pem` to a developer's settings
folder. That secret belongs only in your protected signing setup.

Skip the optional workflow configuration below and continue to step 3 after
installing the policy. Start in audit mode; switch to enforce in step 5.

#### Optional: create a keyless workflow policy

The value uses this format:

```text
OWNER/REPOSITORY/.github/workflows/WORKFLOW-FILE.yml@refs/heads/BRANCH
```

| Part | Meaning | Example |
| --- | --- | --- |
| `OWNER` | GitHub organization **or personal account** that owns the signing repository | `azurekid` |
| `REPOSITORY` | Repository where the approval workflow runs | `agent-skills` |
| `WORKFLOW-FILE.yml` | Exact approval workflow filename | `approve-skills.yml` |
| `BRANCH` | Branch where that workflow signs skills | `main` |

`WORKFLOW-FILE.yml` is a file in **your signing repository**, usually
`.github/workflows/approve-skills.yml`. It is not Skillseal's root `action.yml`.
Create it using the [small reusable-workflow caller](examples/approve-skills.yml)
and the [approval setup guide](APPROVAL.md#2-add-the-approval-workflow).

**If your workflow uses `signing-method: sigstore` through the reusable workflow**, configure both its
identity and your caller:

```bash
skillseal init --mode audit \
  --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main \
  --reusable-workflow azurekid/skillseal/.github/workflows/approve-skills.yml@refs/heads/main
```

Use the shared workflow's exact ref: for a pinned commit use `@COMMIT_SHA`;
for a release tag use `@refs/tags/TAG`. This requires Skillseal newer than
0.3.0. The caller restriction prevents trusting every other repository that
uses the same shared workflow.

**For a workflow that invokes the composite action directly**, use the commands
below without `--reusable-workflow`.

`YOUR-ORG/agent-skills` below is a placeholder for `OWNER/REPOSITORY`, not a required repository name. Replace it with the repository that **signs** your skills, and use the workflow filename and branch your team gives you:

```bash
skillseal init --mode audit --github-workflow YOUR-ORG/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
```

For example, **if you set up** that workflow in `azurekid/agent-skills` on `main`, the command is:

```bash
skillseal init --mode audit --github-workflow azurekid/agent-skills/.github/workflows/approve-skills.yml@refs/heads/main
```

This command trusts signatures from that exact workflow identity. It does **not** create a repository or workflow, download skills, scan files or sign anything. Your team must set up [approval and signing](APPROVAL.md) separately.

#### Do I need this for every repository with skills?

**No. Configure the trusted signer once per developer user on each machine, not once per project.** With user-scope agent hooks installed in step 4, the same policy is used across projects.

* **One central approval workflow:** trust it once. Skills it signs can be copied into many repositories or user skill folders without another trust entry. Copy the complete signed folder, including `skill.oms.sig`, without changing its files.
* **Organization approval:** repositories using the same approval key or dedicated CA need no additional endpoint trust entries.
* **Different keyless workflows sign skills:** each distinct workflow identity you want to trust needs its own entry in `trusted_signers`. This is a policy update, not another installation in every project.
* **A repository only contains copies of signed skills:** no additional signer entry is needed. The signature's signer matters, not the repository you copied the skill from.
* **A skill has no signature:** naming its repository in the policy does not approve it. It must first be signed by a trusted signer.

For example, a skill signed in `azurekid/agent-skills` can be used in both `azurekid/app-one` and `azurekid/app-two` with the same trust entry. Those applications do not need their own approval workflows unless you choose to sign skills there.

For several independent signers, use the [multiple-workflow policy example](APPROVAL.md#trusting-more-than-one-signing-workflow). Do not run `init --force` once per repository: it replaces the policy rather than appending a signer.

The `skillseal init` command writes your user trust policy to the following default location:

| Machine | Policy file |
| --- | --- |
| macOS or Linux | `~/.config/skillseal/policy.json`, for example `/Users/rogier/.config/skillseal/policy.json` on macOS |
| Windows | `%USERPROFILE%\.config\skillseal\policy.json`, for example `C:\Users\rogier\.config\skillseal\policy.json` |

These are user settings, **not files inside your project**. If `SKILLSEAL_POLICY` is set, that variable selects the policy file instead. Otherwise, when `XDG_CONFIG_HOME` is set, the file is in its `skillseal` subfolder. See [policy locations and precedence](REFERENCE.md#the-trust-policy).

We start in **audit** mode: nothing is blocked yet, problems are only written to a log. You switch to blocking in step 5.

#### Use a policy your team gave you

If your team lead sent you `policy.json` and `approval.pub`, copy **both** into
the folder above instead of running `skillseal init`. The commands below assume
both files are in Downloads.

**Already have a policy? Stop before copying.** These commands replace existing
files. Ask your team to preserve existing signers and revocations rather than
overwriting them. Managed devices may use a system-wide policy instead; follow
your IT team's instructions.

macOS or Linux (assuming the file is in Downloads):

```bash
mkdir -p "$HOME/.config/skillseal"
cp "$HOME/Downloads/policy.json" "$HOME/.config/skillseal/policy.json"
cp "$HOME/Downloads/approval.pub" "$HOME/.config/skillseal/approval.pub"
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\skillseal" | Out-Null
Copy-Item "$env:USERPROFILE\Downloads\policy.json" "$env:USERPROFILE\.config\skillseal\policy.json"
Copy-Item "$env:USERPROFILE\Downloads\approval.pub" "$env:USERPROFILE\.config\skillseal\approval.pub"
```

These commands use the default locations and replace an existing policy. If you use either environment override above, copy to that location instead. Only use a policy from someone you trust: it decides who may sign your skills. If the policy references a public key or certificate file, get that file too. Relative paths in the policy are relative to the folder containing `policy.json`.

For certificate-based approval, replace `approval.pub` in the copy commands with
`approval-ca.pem`, using the matching policy supplied by your team.
Run `skillseal check` and look at the `Policy:` line to confirm which settings
file is in use. A system-wide policy at `/etc/skillseal/policy.json` (macOS/Linux)
or `%ProgramData%\skillseal\policy.json` (Windows) takes priority over your user
file. `SKILLSEAL_POLICY` and `XDG_CONFIG_HOME` can also change the user location;
ask IT if your `Policy:` line differs from these examples.

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
Skillseal / Skill verification

  Mode:     audit
  Policy:   ~/.config/skillseal/policy.json
  Signers:  1 trusted
  Agents:   claude, copilot, codex, gemini, opencode, openclaw

Needs approval (2)
  UNSIGNED  ~/.claude/skills/old-helper
    - no skill.oms.sig
  UNSIGNED  ~/.claude/skills/.trash/pdf-tool
    - no skill.oms.sig

Verified (1)
  OK  ~/code/my-project/.github/skills/deploy
    Signer: Organization skill approval

Summary: 3 skills, 1 verified, 2 need approval.
Enforcement: disabled in audit mode; tool calls are not blocked.
Next: remove unapproved skills or have them reviewed and signed.
```

Skills that need attention come first, with explicit `UNSIGNED`, `INVALID`, or
`REVOKED` status labels. Home paths are shortened to `~`; verification reasons
stay visible. Output uses plain text without decorative banners or terminal
control codes, so it remains readable in logs. Use `skillseal check --json` for
the full, unchanged machine-readable results.

Resolve every entry under `Needs approval` before you go to enforce mode. For each one, either delete the folder, or ask your team lead to approve the skill. Watch out for hidden folders such as `~/.claude/skills/.trash`: they are checked too. Use `skillseal check --agent copilot` to only look at one agent.

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

1. Start in audit mode while checking existing skills. Problems are logged in `~/.cache/skillseal/audit.jsonl`.
2. Run `skillseal check --agent copilot` until there are no entries under `Needs approval`.
3. Run `skillseal setup enforce --agent copilot` from your approved-skills project and confirm.
   Substitute your actual agent name. IT-managed policies must be changed by IT.
4. Restart the agent and test its hooks below. A configuration file alone does not prove blocking works.

Advanced/manual policies can also set `"mode": "warn"` for visible nonblocking
warnings, or `"mode": "enforce"` directly in the authoritative policy. Guided
enforcement checks readiness first and preserves the other policy fields.

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
