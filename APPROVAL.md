# Set up signing for your skills

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Technical reference](REFERENCE.md)

**For your own private projects, an open-source project, or a team.**
Set up signing once, then connect your own machine. Sharing with others is optional.

## 1. Open your skills repository

You need:

- [Skillseal v0.4.0 or newer](GETTING-STARTED.md#install-skillseal).
- A GitHub repository for skills you review and approve. A personal account
  and private repository work; a GitHub organization is not required.
- [GitHub CLI](https://cli.github.com), signed in with `gh auth login`.
- Permission to add Actions secrets to that repository.

Open the repository's folder in your terminal.
**Use your own skills repository, not Skillseal's own source repository.**

Need a new one? Replace `YOUR-ACCOUNT` with your GitHub account or organization:

```bash
gh repo create YOUR-ACCOUNT/approved-skills --private --clone
cd approved-skills
```

## 2. Run setup

```text
skillseal setup organization --upload-secret
```

The command is named `organization`, but works for individual users too.
Enter your name, a project name or a team name when prompted, then confirm.
Setup creates a signing workflow, a signed welcome skill and `skillseal-team.zip`.
The package is saved outside the repository, under
`~/.skillseal/exports/OWNER/REPO/`; setup prints the full path and command to use.
It also saves a private-key backup outside the repository and prints its location.

**Keep the private-key backup safe. Never commit or share it.**

If your signing branch is not `main`, add `--branch YOUR-BRANCH`.

## 3. Publish and check

1. Review the generated files, then commit and push them using your usual Git tool.
   Setup does not do this for you.
2. Open the repository on GitHub and select **Actions**.
3. Wait for **Approve skills** to show a green check.

If it fails, open the failed step to read its error. Check repository permissions
and branch rules, or ask the repository owner if that is someone else.
Do not remove protections just to make it pass.

Review skill and workflow changes before they reach the signing branch.
The included scan helps spot common problems; it does not replace review.

## 4. Connect your machine

Use the full package path printed by setup, replacing `OWNER/REPO` below:

```text
skillseal setup --bundle "~/.skillseal/exports/OWNER/REPO/skillseal-team.zip"
```

The package works for one person too; there is no need to send it anywhere.
This step installs your public approval key and configures `trusted_signers`;
creating the signing workflow alone does not configure your machine's trust.
Continue with [Restart your agent](GETTING-STARTED.md#3-restart-your-agent)
and enable blocking.

**Sharing with others?** Send `skillseal-team.zip` through a channel they trust.
They follow [Getting started](GETTING-STARTED.md#use-an-existing-setup).
They do not need your private key or GitHub access to verify signed skills.

The welcome skill is ready to use in this repository for Copilot, Codex, Gemini
and OpenCode. Claude Code users copy its complete folder from
`.agents/skills/skillseal-welcome` to `.claude/skills/skillseal-welcome`.

## Approve another skill

1. Add it to the appropriate [skill folder](REFERENCE.md#where-each-agent-loads-skills).
   The generated workflow checks skill folders directly inside these locations.
2. Review and merge it into the signing branch.
3. Wait for **Approve skills** to finish and commit `skill.oms.sig`.
4. Use or share the complete folder, including that signature. Do not edit the files
   after signing; changed files need approval again.

## Already have a signing key?

If setup says **"The GitHub approval secret already exists"**, keep it.
Do not delete the secret or generate a new key.

With the original private-key file saved outside your repository, use:

```text
skillseal setup organization --upload-secret --private-key "/path/to/original-approval-private.pem"
```

Replace the example path with your saved key's location.
**This option requires v0.4.1 or newer.**

Setup keeps an existing workflow and secret. GitHub cannot show the saved secret,
so you must use the original matching key.
Before using or sharing the package, extract its ZIP to a temporary folder and check a
skill that your GitHub workflow has signed:

```text
skillseal verify --no-cache --policy /path/to/extracted-team/policy.json /path/to/github-signed-skill
```

Expected: `OK`. Do not use the locally generated welcome skill for this check.
If it fails, check that the saved key is the one your workflow uses, or ask whoever
set up signing. Do not replace the secret just to bypass the error.

## Setup stopped?

| Message | What to do |
| --- | --- |
| Setup already exists | Keep the existing setup. If this is Skillseal's source folder, switch to your own skills repository. |
| Approval secret already exists | Follow [Already have a signing key?](#already-have-a-signing-key). |
| Secret upload failed | Keep the key backup and generated files. Check your repository access, then add that same key as `SKILLSEAL_APPROVAL_PRIVATE_KEY` in GitHub's Actions secrets. |
| `--force` is not recognized | There is no force-overwrite option. Do not replace working keys or workflows to bypass setup checks. |

## Emergency trust revocation

Stop using or sharing the affected skill. Notify anyone you shared it with.
Follow the
[withdrawal runbook](ADMINISTRATION.md#emergency-trust-revocation)
to update trust on your machine and any other machines using your approvals.

Need certificates or custom workflows? Use [Advanced administration](ADMINISTRATION.md).
