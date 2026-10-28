# Approve skills for your team

[Overview](README.md) | [Getting started](GETTING-STARTED.md) | [Approval guide](APPROVAL.md) | [Reference](REFERENCE.md)

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

Or share the resulting `~/.config/skillseal/policy.json` file. It is small and contains no secrets, so you can put it in dotfiles, a devcontainer, an onboarding script or a base image. Developers copy it to their own user policy location using the [copy instructions](GETTING-STARTED.md#use-a-policy-your-team-gave-you). Include any public key or certificate files it references. Do not distribute your own machine's absolute paths to those files.

### 4. Get the skills to developers

Developers copy or clone the signed skill folders into one of the skill folders of their agent (see the [skill locations table](REFERENCE.md#where-each-agent-loads-skills)), including `skill.oms.sig`. Projects can also commit signed skills in `.github/skills` or `.claude/skills`.

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
