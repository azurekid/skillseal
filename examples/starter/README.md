# Try two signed starter skills

These are harmless, already-signed examples. You do not need to generate a
key, set up GitHub Actions, or change your computer's trust settings.

## 1. Install Skillseal

Follow the [installation guide](../../GETTING-STARTED.md#step-1-install-skillseal).
If you are using the downloaded starter ZIP, open:
https://github.com/azurekid/skillseal/blob/main/GETTING-STARTED.md

## 2. Open this folder in a terminal

If you downloaded `skillseal-starter.zip` from a Skillseal release, extract it
first. Open the extracted folder containing this README and `policy.json`.
If you downloaded the whole repository instead, open `examples/starter`.

## 3. Check both examples

This command works in PowerShell, macOS Terminal, and Linux terminals:

```text
skillseal verify --no-cache --policy policy.json skills/friendly-greeting skills/writing-checklist
```

You should see `OK` for both skills and the signer
`Skillseal starter examples only`. No keys are generated and nothing is
installed. This command checks signatures; it does not run an AI agent.

The explicit `--policy policy.json` means "use this demonstration policy for
this command only." It does not replace your normal user or system policy.
It is a demo, not a way to override an organization's enforced agent policy.

## 4. See what happens after an edit

Open `skills/friendly-greeting/SKILL.md` in a text editor, add a sentence,
and save it. Run the same command again.

The edited skill should now show `INVALID`; the other skill should still show
`OK`. Extract a fresh copy of the ZIP to restore the original.

## Optional: use them in your agent

Ask your team to review and re-sign these skills with your organization's
approval key, then copy each complete skill folder into your agent's skill
directory. Include `skill.oms.sig`. Follow the
[agent setup guide](https://github.com/azurekid/skillseal/blob/main/GETTING-STARTED.md#step-4-connect-skillseal-to-your-agent).

Do not copy this demo policy over your real trust policy. The starter public
key is for these examples, not your organization's approval authority.

## What trust means in this demo

Both skill signatures were made before publication. This download contains
only the public key; the demo private key is not included or needed.
The SHA256 fingerprint of the public-key file is published in the main
getting-started guide. Obtain that guide from a source you already trust.

A matching fingerprint from the same untrusted download is not independent
proof of publisher identity. Checksums and signatures establish integrity only
after you decide to trust their source. These examples do not grant default
trust to third-party skills or prove enforcement by a running agent.
