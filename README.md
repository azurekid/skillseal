# skillseal

**Check that your AI agent's skills are signed by someone you trust, and have not changed.**

## The goal

Use AI agent skills without trusting every folder someone copied into a project or installed on a developer machine. Your team decides which signers it trusts. skillseal checks the skills against that trust policy before the agent can use tools.

It is open source, works on macOS, Linux and Windows, and needs no server, no MDM and no extra license. Standalone builds work without Python on supported machines.

**[Get started on your machine](GETTING-STARTED.md)**

## The challenge

A skill is a folder with a `SKILL.md` file and sometimes scripts or other files. Agents like Claude Code, GitHub Copilot, Codex, Gemini CLI and OpenCode discover skills in project and user folders.

That is useful, but it creates a trust problem:

* A skill can contain instructions that steer an agent in the wrong direction.
* A skill that passed a scan yesterday can be edited today.
* A skill copied from another repository may never have been approved.
* A signature helps only when somebody actually checks it before use.

Scanning alone does not close this gap. You need to connect approval to the exact files the agent will use.

## The solution

skillseal works in two parts:

1. **Approve and sign.** Your approval workflow scans a skill. If the scanner accepts it, the workflow signs the folder and writes `skill.oms.sig` next to `SKILL.md`. You can also sign with your own key or certificate.
2. **Verify on the developer machine.** You install a guard through your agent's hook system. It discovers skills, checks whether a trusted signer signed them, and checks that no file was changed, added or removed.

```text
  APPROVE                               CHECK
  -------                               -----
  Skill folder                          Agent tool call
       |                                      |
       v                                      v
  Scan and review                       Discover skills
       |                                      |
       v                                      v
  Sign exact files                      Verify signer + file hashes
       |                                      |
       v                                      v
  Distribute skill + signature           Pass: allow | Fail: block*

  * Blocking requires enforce mode and a working agent integration.
```

In **enforce** mode, any unapproved skill stops tool use through the configured guard. Start in **audit** mode to find existing problems without blocking your work, then switch to enforce when your skills are ready.

A signature proves who signed the files and whether they changed. **It does not prove that the skill is safe.** The quality of your scanning, review and trusted signers still matters.

Skillseal includes a small heuristic scanner for obvious prompt-injection phrases and risky shell/network commands. It can miss harmful content and flag benign examples; it is not a safety guarantee.

### Trust and withdraw skills without a server

Configure approved external publishers and internal signers in the same managed
policy. A valid signature alone never grants trust. Withdraw a release using
`skillseal digest` and the policy's `revoked_skills`, or remove a compromised
publisher from the trusted signers. Updated policies take effect on the next
check, including previously cached approvals.

For managed teams, configure one organization approval public key or dedicated
CA in that policy. GitHub Actions signs reviewed skills using the corresponding
protected private key; endpoints do not need to trust individual workflows.
See [organization approval setup](APPROVAL.md#configure-the-organization-approval-authority).

Run the [offline trust and revocation lab](examples/TRUST-LAB.md), or follow the
[emergency revocation runbook](APPROVAL.md#emergency-trust-revocation). Policy
distribution is your responsibility: offline devices cannot learn about a new
revocation until their local policy is updated.

For GitHub approval, use the [small caller workflow](examples/approve-skills.yml)
in your skills repository. It delegates to Skillseal's
[reusable approval workflow](.github/workflows/approve-skills.yml). Follow the
[setup instructions](APPROVAL.md#2-add-the-approval-workflow).
The shared workflow defaults to organization-key approval. Optional keyless
shared-workflow verification requires a version newer than 0.3.0.

## Read the guide you need

| Guide | What it covers |
| --- | --- |
| [Getting started](GETTING-STARTED.md) | Install on Windows, macOS or Linux, set your trust policy, connect your agent, test blocking and troubleshoot |
| [Approval guide](APPROVAL.md) | Set up scanning and signing, share the policy and distribute signed skills |
| [Technical reference](REFERENCE.md) | Agent hooks, skill locations, policy precedence, verification rules, limits and commands |
| [Trust lab](examples/TRUST-LAB.md) | Reproduce internal/external trust, tamper detection, withdrawal, and recovery without a server |
| [Release notes](CHANGELOG.md) | Changes and validation requirements for the next release |

Using VS Code? Start with [the VS Code instructions](GETTING-STARTED.md#vs-code). Other tools: [Copilot CLI](GETTING-STARTED.md#github-copilot-cli), [Claude Code](GETTING-STARTED.md#claude-code), [Codex](GETTING-STARTED.md#codex-cli), [Gemini](GETTING-STARTED.md#gemini-cli) and [OpenCode](GETTING-STARTED.md#opencode). OpenClaw support is experimental and not tested.

## Know the limits

skillseal is a guard, not a sandbox. Users who control their machine can remove user hooks. Only skill folders are covered, not every instruction or command file an agent can read. Copilot hook timeouts fail open, and VS Code hooks are still in Preview.

Read the [full limits](REFERENCE.md#honest-limits) before treating this as an enforcement boundary.

## License

Apache-2.0
