# Skills: operating Paperclip from Jarvis

These are the skills the reference setup runs to **operate the work plane** — the ones that
make *"start that in the background"* and the window's jobs board actually mean something.
They are the agent's half of Paperclip; Paperclip itself is
[paperclipai/paperclip](https://github.com/paperclipai/paperclip)
([docs](https://docs.paperclip.ing)).

```sh
cp -r skills/* ~/.hermes/skills/          # from the repo root
```

## What ships here

| Skill | What it is | The agent loads it when |
| --- | --- | --- |
| [`paperclip-operations`](paperclip-operations/SKILL.md) | The operating manual for one machine: identity model, environment variables, the task lifecycle with verified commands, run monitoring, recovery, and the conventions that keep two writers off one fact | any Paperclip work at all — creating, assigning, monitoring, unblocking |
| [`paperclip-task-bridge`](paperclip-task-bridge/SKILL.md) + `paperclip-task.mjs` | The Hermes → Paperclip direction: create a task, comment, change status, list assignments, using a scoped `task_bridge` key | the agent needs to *start* or *update* work itself |
| [`paperclip-harness-dispatch`](paperclip-harness-dispatch/SKILL.md) | How a worker run is actually dispatched and what it may write back | the agent is about to hand work to another agent |
| [`paperclip-scoping-and-access`](paperclip-scoping-and-access/SKILL.md) | Org/project scoping, what a bridge key may and may not touch, and why a key that is too broad is worse than a key that is too narrow | setting up a new company, project or seat |

The examples in these files name a company, a project and eight agent seats. Yours will
differ: §Environment in `paperclip-operations` shows the commands that read your own ids, and
every id in this directory is a placeholder (`<company-id>`, `<engineer-agent-id>`, …) — fill
them in from your instance, never the other way round.

## What Paperclip ships (do not copy these)

Installing the CLI gives you its own skills as symlinks into the npm package, and they are the
user-facing half of the same system:

| Skill | What it covers |
| --- | --- |
| `paperclip` | the control plane API and the CLI itself |
| `paperclip-board` | running a company as a board member: hires, budgets, strategy |
| `paperclip-converting-plans-to-tasks` | turning a plan into an executable issue graph |
| `paperclip-create-agent` | hiring a seat with governance rules |

They arrive with `npm install -g paperclipai` and live in
`~/.paperclip/cli/installs/npm/<version>/node_modules/@paperclipai/server/skills/`. Copying
them into your own tree would freeze them at a version and misattribute them — install the CLI
and let them update.

## Configuration

`~/.hermes/.env` (or your profile's), never in a prompt:

| Variable | What it is |
| --- | --- |
| `PAPERCLIP_API_URL` | base URL, e.g. `http://127.0.0.1:3100` |
| `PAPERCLIP_BRIDGE_API_KEY` | a **`task_bridge`-scoped** agent key — create it from a board session; never a full agent key |
| `PAPERCLIP_COMPANY_ID` | skips one identity lookup |
| `PAPERCLIP_AGENT_ID` | the seat the agent acts as |

The bridge key can only create work inside its approved boundary and only touch work it
created or was assigned — that is the point of it. A full agent key in an agent runtime is a
machine-wide write credential; `paperclip-scoping-and-access` explains the difference.

## The two conventions the window depends on

1. **Naming.** Everything Jarvis starts is titled `[Jarvis] <topic> · <YYYY-MM-DD HH:MM>`. The
   marker is load-bearing: the window's board filters on it, so an unmarked job is invisible to
   the person watching.
2. **Sessions.** The board shows the *current* session's jobs, and **New session** cancels
   them. Jobs are cancelled in the work plane first, then forgotten locally — never the other
   way round, or a board could show a job that is still alive.
