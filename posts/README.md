# Agent Overwatch — launch assets

Marketing images for the repo README and LinkedIn. All images are **local**;
regenerate any time with `bash posts/src/render.sh` (headless Chrome, nothing
uploaded). Every image is a faithful recreation of real runs with machine-specific
details replaced by placeholders (`~/project`, `your-vps`).

## Files

| File | Size | Use |
|---|---|---|
| `01-hero.png` | 1200×1200 | LinkedIn slide 1 — title / what it is |
| `02-architecture.png` | 1200×1200 | LinkedIn slide 2 — how it works |
| `03-proof.png` | 1200×1200 | LinkedIn slide 3 — both agents blocked reading `.env` |
| `../docs/images/architecture.png` | 1600×1180 | README architecture diagram |
| `../docs/images/proof-codex.png` | 1240×820 | README — Codex blocked |
| `../docs/images/proof-claude.png` | 1240×1180 | README — Claude blocked + sandbox |

Sources: `src/*.html` + `src/style.css`. Rebuild: `bash src/render.sh`.

## LinkedIn post (copy/paste)

> An AI coding agent will run whatever it's told to run, and that includes
> `cat .env`, `git push`, or `DROP DATABASE`. A "don't do that" in the system
> prompt is a suggestion the model can talk itself out of.
>
> I wanted a guard that doesn't depend on the model behaving, so I built Agent
> Overwatch.
>
> It sits in front of the agent's tool calls. Every call is checked against a
> plain-text policy before it runs and comes back allow, ask, or deny, with a
> redacted log of every decision. Reads of secrets and keys, git push, package
> publishes, and destructive SQL are blocked outright. sudo and deploys ask a
> human first.
>
> The part I like: one policy file guards both Claude Code and Codex CLI. Slide 3
> shows both of them stopped from reading a .env, blocked before the command runs
> instead of flagged after.
>
> It's MIT-licensed and on GitHub. If you let agents run commands on your machine,
> it might save you a bad afternoon.
>
> github.com/devalinaqvi/agent-overwatch

**Hashtags** (spaced for readability):

```
#AIAgents  ·  #DevSecOps  ·  #AICodeSecurity  ·  #ClaudeCode  ·  #OpenSource
```

## Image alt text (accessibility — paste into LinkedIn's alt field)

- **01-hero**: "Title card — Agent Overwatch, a deterministic guard for AI coding
  agents. It checks each tool call before it runs and returns allow, ask, or deny,
  with a redacted audit log. Works with Claude Code and OpenAI Codex CLI."
- **02-architecture**: "Flow diagram — an agent (Claude Code or Codex CLI) sends a
  PreToolUse event to a fail-closed hook; an adapter turns it into an Action; the
  engine evaluates it against policy.json and returns allow, ask, or deny. A
  redacted audit log and a human-only bypass sit alongside."
- **03-proof**: "Proof — Codex CLI blocked by rule SEC-030 and Claude Code blocked
  by rule SEC-001, both stopped from reading a .env file by the same policy."

## GitHub — About (short description)

A deterministic guard for AI coding agents — checks each tool call before it runs (allow/ask/deny) and blocks secret reads, git push, and destructive commands, with a redacted audit log. Works with Claude Code and OpenAI Codex CLI.

## GitHub — Topics

ai · ai-agents · ai-safety · llm · coding-agent · claude · claude-code · codex ·
openai-codex · security · guardrails · policy-enforcement · hooks ·
developer-tools · sandbox · prompt-injection · devsecops · python · cli
