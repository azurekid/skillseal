# Skillseal

**You gave your AI agent tools. Be deliberate about who gives it instructions.**

A useful skill can save you hours. But once you've copied it into your project,
how do you know it's still the version you reviewed? What about the next skill
you install, or the one that arrives with a repository you just cloned?

Skillseal gives approved skills a signature, then checks that signature before
your agent uses tools. An unsigned skill, an unexpected edit, or a withdrawn
approval shouldn't quietly become part of your workflow.

Built for your own laptop and private repos, not just company rollouts.
Works on **Windows, macOS and Linux**. No central server required.

## See it for yourself

[Install Skillseal](GETTING-STARTED.md#install-skillseal) in an isolated Python
environment with **pipx or uv**. Release wheels and source packages have GitHub
build provenance; standalone downloads remain optional. Then run:

```text
skillseal demo
```

You'll see an approved skill pass, an edited skill fail, and an unsigned skill
fail. The examples are already signed. No keys to create, no GitHub setup,
and no changes to your agent or trust settings.

Prefer a menu? Run **`skillseal`** in a terminal (or `skillseal menu`) for guided
checks, protection setup, local signing, and enforcement. You can create a
personal signing key without GitHub; existing trust restrictions still apply.
See [local signing](GETTING-STARTED.md#local-signing-without-github).

**[Try it on your own projects →](GETTING-STARTED.md#set-up-my-own-skills)**

## Keep the skills. Add an approval check.

You don't need to give up community skills or build everything yourself.
Review the skills you want, approve those exact files, and let Skillseal spot
when something no longer matches.

1. **Review and sign.** Your GitHub workflow scans skills and signs them with
   your approval key. You decide what reaches the signing branch.
2. **Connect your agent.** Accept your setup package once on your machine.
3. **Check, then block.** Start in audit mode to see what needs attention.
   Enable enforcement when your skills are ready.

In enforce mode, any discovered skill that fails verification causes the
configured guard to request blocking of tool calls—not just calls from that skill.

### Choose an enforcement mode

Set `mode` in your policy, or choose one when creating it with
`skillseal init --mode enforce|warn|audit`. The default is `enforce`.

| Mode | When a skill fails verification |
| --- | --- |
| `enforce` | Blocks tool calls through the configured guard. |
| `warn` | Shows a warning, but allows tool calls. |
| `audit` | Records the check in `~/.cache/skillseal/audit.jsonl`; does not warn or block. |

Use `audit` to observe results before enabling blocking, or `warn` when you want
visible feedback without blocking. See the [policy reference](REFERENCE.md#the-trust-policy)
for policy locations and precedence.

Already approved a skill and copied it to another project? Its signature travels
with it. Copy the whole folder, including `skill.oms.sig`, without editing the files.

## Just you? That's enough.

Your personal GitHub account and a private repository are all you need on the
GitHub side. No organization account or administrator required.

Follow the [short signing setup](APPROVAL.md), starting in your own skills repo:

```text
skillseal setup organization --upload-secret
```

Yes, the command is called `organization`. It works for one person too.
Enter your name or your project's name, follow the prompts, then review and push
the generated public files.

Connect your machine with the package it creates. Use the full path printed by
setup, replacing `OWNER/REPO` below:

```text
skillseal setup --bundle "~/.skillseal/exports/OWNER/REPO/skillseal-team.zip"
```

Despite its name, `skillseal-team.zip` works perfectly well for a team of one.
If someone already approves skills for you, use their trusted package instead.

Restart your agent. Once your skills pass `skillseal check`, use
`skillseal setup enforce` to enable blocking and
[test it](GETTING-STARTED.md#check-and-switch-on-blocking).

Working with others later? Share that public package through a trusted channel.
They can verify your approvals without receiving your private signing key.

**Supports GitHub Copilot, Claude Code, Codex, Gemini CLI and OpenCode.**
Copilot is the default; the [setup guide](GETTING-STARTED.md#join-your-team)
shows how to choose another agent. Guided setup requires **v0.4.0 or newer**.

## What this does—and doesn't—promise

Skillseal checks **who signed a skill, whether its files changed, and whether
your local policy has withdrawn approval**. You still need to review what you
sign. A valid signature on a bad skill is still a bad skill.

It's a guard, not a sandbox. It doesn't stop an agent from reading Markdown,
undo past actions, or magically make every agent integration fail closed.
Blocking depends on working hooks; Copilot timeouts can allow commands through.
And a withdrawn approval only reaches an offline machine when its policy is updated.

That's why [testing your agent's blocking behavior](GETTING-STARTED.md#check-and-switch-on-blocking)
is part of setup, not an optional finishing touch.
Read the [full limits](REFERENCE.md#honest-limits) before relying on enforcement.

To verify skills before an agent process starts, launch it through Skillseal:

```text
skillseal run --agent copilot -- copilot
```

Replace `copilot` with the agent and its command. This startup gate refuses to
launch if any discovered skill fails verification, regardless of policy mode.
It only applies when you start the agent through `skillseal run`; hooks remain
useful as defense in depth. This is not a sandbox and doesn't prevent files from
changing between verification and agent access.

## Pick your next step

- [Get started on your machine](GETTING-STARTED.md)
- [Set up signing for yourself or a team](APPROVAL.md)
- [Troubleshooting](GETTING-STARTED.md#need-help)
- [Advanced administration and emergency withdrawal](ADMINISTRATION.md)
- [Technical reference](REFERENCE.md)
- [Reproducible trust and revocation lab](examples/TRUST-LAB.md)
- [Release notes](CHANGELOG.md)

## License

Apache-2.0
