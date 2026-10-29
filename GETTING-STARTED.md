# Get started with Skillseal

[Overview](README.md) | [Set up signing](APPROVAL.md) | [Technical reference](REFERENCE.md)

**Keep control of the skills your AI agent uses—on your own projects or with a team.**
No company account, administrator or central server is required for personal use.
These steps require Skillseal **v0.4.0 or newer**.

<a id="step-1-install-skillseal"></a>

## Install Skillseal

### Windows

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/azurekid/skillseal/main/install.ps1 | iex
```

### macOS or Linux

Open **Terminal** and run:

```bash
curl -fsSL https://raw.githubusercontent.com/azurekid/skillseal/main/install.sh | sh
```

No administrator rights or Python needed. The Mac download is for Apple silicon;
the Linux download is for x64 systems such as Ubuntu 22.04 or newer.
For other machines with Python 3.10+, use [pipx](https://pipx.pypa.io):
`pipx install git+https://github.com/azurekid/skillseal`.
On a managed work device, follow your organization's installation rules.

**Open a new terminal**, then run:

```text
skillseal --version
```

Expected: `skillseal 0.4.0` or newer.

<a id="five-minute-setup"></a>

## Try it first

```text
skillseal demo
```

Expected: three `PASS` lines. The demo shows approved skills passing and edited
or unsigned skills being rejected. It does not change your settings or connect
to your agent.

## Choose your setup

| Your situation | Next step |
| --- | --- |
| I use skills in my own projects | [Set up my own skills](#set-up-my-own-skills) |
| Someone already approves skills for me | [Use an existing setup](#use-an-existing-setup) |
| I want to approve skills for others too | [Set up signing](APPROVAL.md), then share the package |

## Set up my own skills

You decide which skills to approve. Your private GitHub repository can scan and
sign them; Skillseal checks those approvals on your computer.

1. Follow [Set up signing](APPROVAL.md) in your own skills repository.
   A personal GitHub account and private repository are fine.
2. In that same folder, connect your machine using the package setup created:

   ```text
   skillseal setup --bundle skillseal-team.zip
   ```

3. Continue with [Restart your agent](#3-restart-your-agent), then check and
   enable blocking below.

Despite the filenames, `skillseal-team.zip` also works for one person.
The signing command is currently called `setup organization`; it does **not**
require a GitHub organization. Enter your own name or a project name when asked.

<a id="join-your-team"></a>

## Use an existing setup

### 1. Get the setup package

Use the **`skillseal-team.zip`** you created yourself, or one received directly
from someone whose skill approvals you trust.
Do not unzip it.

### 2. Run setup

Open your project in a terminal and run this command.
Replace the example path with the location of the ZIP you received:

```text
skillseal setup --bundle "/path/to/skillseal-team.zip"
```

Check the displayed name, then confirm. If someone sent you the package, check
with them if you are unsure about its origin or the displayed key fingerprint.

This command sets up **Copilot**. For another agent, add one of:

| Your agent | Add to the command |
| --- | --- |
| Claude Code | `--agent claude` |
| Codex | `--agent codex` |
| Gemini CLI | `--agent gemini` |
| OpenCode | `--agent opencode` |

For example:

```text
skillseal setup --bundle "/path/to/skillseal-team.zip" --agent claude
```

Use the same agent option with `check` and `setup enforce` below.

<a id="step-4-connect-skillseal-to-your-agent"></a>

### 3. Restart your agent

Close and reopen it. Check that it loads its Skillseal hooks: these are the
checks Skillseal runs before tool use.

- **VS Code with Copilot:** select the Copilot chat target, open `/hooks` and look for Skillseal.
- **Copilot CLI or Claude Code:** start a new session and check `/hooks`. Claude may first ask you to trust the project.
- **Codex:** open `/hooks` and approve the Skillseal entry.
- **Gemini or OpenCode:** fully restart the application.

Setup starts in **audit mode**. It reports problems but does not block work yet.

## Check and switch on blocking

Use skills you have reviewed and signed, or approved copies from someone you
trust, including their `skill.oms.sig`
files. Open the project that contains those skills, then run:

```text
skillseal check
```

Expected: skills show `OK`. If a skill needs approval, review it and
[run your signing workflow](APPROVAL.md#approve-another-skill), or get an approved
copy from its maintainer. **Do not edit signed files or approve unknown signers to
make an error disappear.**

When all discovered skills pass:

```text
skillseal setup enforce
```

Confirm, then restart your agent. This setting also applies to other projects
using your Skillseal setup.

**Test it once:** create a temporary skill folder named `test-unsigned` in your
project's `.agents/skills` folder. For Claude Code, use `.claude/skills` instead.
Inside it, create `SKILL.md` containing only `This is a test.`
Ask your agent to list the project files. It should refuse with a Skillseal
message. Then delete only the temporary `test-unsigned` folder and start a fresh session.

If the agent still runs the command, do not assume blocking is working.
Check that your agent loads its Skillseal hooks, or ask for help. Copilot hook timeouts can
allow a command through.

## Everyday use

Use your agent normally. Run `skillseal check` when you need to investigate a
blocked skill. Restore an approved copy or review and sign the updated version.
If someone else manages the skills, send them the reported reason.

To update Skillseal, close your agents and rerun the same installer you used
above. Your settings stay.

## Need help?

| Problem | Next step |
| --- | --- |
| `skillseal` is not found | Open a new terminal. If it still fails, rerun the installer. |
| `demo` or `setup` is not recognized | Update Skillseal. |
| `UNSIGNED` | Review and sign the skill, or obtain the complete approved copy with its signature. |
| `INVALID` | Restore an approved copy, or review and sign the changes before using them. |
| `REVOKED` | Stop using it. Approval has been withdrawn. |
| Setup finds a different policy | Keep the existing settings. Check which setup you already use; do not overwrite it to bypass the warning. |
| Setup finds an IT-managed policy | Ask whoever manages the device. |
| No skills found | Open the project containing your skills and check their [folder location](REFERENCE.md#where-each-agent-loads-skills). |

### Where are my settings?

Setup installs them for you. You normally do not need to open or edit them.

| Machine | Default folder |
| --- | --- |
| macOS / Linux | `~/.config/skillseal` |
| Windows | `%USERPROFILE%\.config\skillseal` |

The folder contains `policy.json` and the public approval key, `approval.pub`.
Never put a private key here. Custom or IT-managed locations are shown by
`skillseal check`.

### Stop using Skillseal

Remove its agent connections first:

```text
skillseal uninstall copilot claude codex gemini opencode --scope user
```

Your other agent settings stay. Restart your agents afterward.
For custom policies, manual installation or other integrations, see the
[technical reference](REFERENCE.md) and [advanced administration](ADMINISTRATION.md).
