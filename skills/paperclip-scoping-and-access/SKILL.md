---
name: paperclip-scoping-and-access
description: Use when scoping Paperclip orgs, projects, or agent skills.
---

# Paperclip scoping and access

Companion to `paperclip-operations` (task lifecycle, bridge, monitoring). This one
answers **"what is scoped to what, and can I give a capability to just one agent or one
org?"** — the question where the intuitive answer is usually wrong on this stack.

## Rule one: verify the mechanism before designing around it

Before planning anything of the form *"give X only to agent Y"*, read the adapter or
server source for that capability. A per-agent plan the runtime cannot honour is worse
than no plan: it produces config that looks correct and behaves differently, and it
misleads the user about what they just enabled. On the `hermes_local` adapter the
decisive files are
`@paperclipai/hermes-paperclip-adapter/dist/server/skills.js` and
`@paperclipai/adapter-utils/dist/server-utils.js`.

The same rule runs the other way: when the user reports that the UI offers a control you
believe is impossible, **test it** instead of arguing from your reading. On this exact
point the UI was right and the reading was wrong.

## What a scoped key may READ (a bridge key is boundary-shaped, not just write-shaped)

A key's boundary constrains **reads as much as writes**, and the refusals read like URL
problems when they are scope problems — so stop re-shaping the URL and change credential:

- `GET /api/companies/{cid}/issues` → `Task bridge keys cannot use company-wide issue
  list APIs`.
- `GET /api/issues?companyId=…` → `Missing companyId in path. Use
  /api/companies/{companyId}/issues.` — following that hint lands on the first error.
- The read that works is the **board CLI**, not the key:
  `paperclipai issue list --project-id <uuid>` (the flag is `--project-id`; `--project`
  is rejected as an unknown option). One line per issue, so it greps and filters cleanly.
- Ids are not all in `~/.hermes/.env`: it carries `PAPERCLIP_API_URL`,
  `PAPERCLIP_BRIDGE_API_KEY`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_AGENT_ID` — **no
  `PAPERCLIP_PROJECT_ID`**. Take company/project/agent ids from the env block in
  `paperclip-operations`.
- When reporting board state to the user, give **only the rows that are not
  `done`/`cancelled`** (`blocked` first) and say plainly when nothing is running; a dump of
  closed issues reads as noise.

## Instance vs company (the "organisation" in the UI)

| Level | What it is | Shared across companies? |
|---|---|---|
| **Instance** | One deployment: a data dir, its own embedded Postgres, one server + port, logs, backups | — |
| **Company** | A tenant *inside* an instance | Yes: same DB, same server, same port, same `secrets/master.key` |

- Instances are created by **onboarding**, not the UI:
  `paperclipai onboard --data-dir ~/.paperclip/instances/<name>`.
- Company-scoped records (projects, agents, skills, goals, issues, routines, work
  products, budget) live under `/api/companies/<id>/…`. The tell: `/api/skills` 404s
  while `/api/companies/<id>/skills` returns 200.
- **Companies are not a security boundary.** Two companies in one instance share the
  database and the master key. Workstreams that must not touch each other (a client vs
  your own) need a second *instance*, not a second company — companies are for
  organisational separation and a shared cost view.

### Letting another person see the dashboard

Four gates. The two obvious ones are both necessary and neither is sufficient:

1. **Network path** — they must be able to reach the host at all (e.g. the tailnet).
2. **Server reachability** — the UI binds **loopback** by default, so even a peer on the
   same VPN cannot reach it. A non-loopback bind is what engages the auth gate.
3. **Hostname allowlist** — `paperclipai allowed-hostname <host>`, required for
   authenticated/private-mode access.
4. **Account + membership** — a Paperclip user, then membership of the company
   (`membershipRole` plus per-`permissionKey` grants such as `agents:configure`).
   Without membership they sign in and see nothing.

**Say this before enabling it:** a board member can drive the agents, and our agents run
`hermes_local` with `terminal` and `file` toolsets on this laptop — so org membership is
effectively *indirect shell access to the machine*, not a read-only dashboard share. If
the intent is "let them watch progress", a one-way digest or read-only surface is the
right shape; ask which one they actually want before opening a bind.

## Projects

A project is the container that **groups issues toward a deliverable**. Fields: `name`,
`description`, `status` (`planned`, `in_progress`, …), `urlKey`, one `leadAgentId`,
`goalIds` (goals are company-level), `targetDate`, `color`, `env`,
`executionWorkspacePolicy`, `archivedAt`, and **`workspaces` / `primaryWorkspace`**.

**`workspaces` is empty by default, and it is the field that matters.** Each entry is a
`cwd` (local folder), a `repoUrl` + `repoRef` (branch), or both; the first is primary.
Agents resolve their execution context from `primaryWorkspace`.

- A project with **no workspace** gives its tasks no project working directory. Workers
  still run — the adapter falls back — but they are working blind rather than in a
  checkout. Correct for ops/research work; wrong the moment tasks must edit code.
- Bind one with `POST /api/projects/{projectId}/workspaces`, or inline at create time as
  `"workspace": {name, cwd, repoUrl, repoRef, isPrimary}`.
- Routines are project-scoped: `projectId` is **required**, and each firing creates an
  execution issue for the routine's agent, picked up in a normal heartbeat.
- A bound workspace is also an **approved root for skill import** — binding a repo
  unlocks local imports from that checkout (see below).

Verify with `GET /api/projects/{projectId}` and read `workspaces` /
`primaryWorkspace` — not merely that the project exists.

## Skills: per-agent attachment, org-wide delivery

Depth, commands and exact error strings: `references/skills-delivery.md`.

All verified on this stack:

- The Skills-tab toggle **is genuinely per-agent** — it writes
  `paperclipSkillSync.desiredSkills` on that one agent, and the library reports an
  `attachedAgents` count per skill. Do not tell the user this control does not exist.
- But an attached skill is materialised as a **symlink into the shared
  `~/.hermes/skills/`**, which every agent reads. The attachment is per-agent; the
  *delivery* is not. On a shared Hermes home, "enabled on one agent" means "in
  everyone's library".
- Worse, attachments are **not stable**: each agent's run reconciles the shared home to
  its own desired set and unlinks the others' managed symlinks, so the library reflects
  whichever agent ran last. Never assert that a previously-attached skill is still there —
  re-read the home.
- Every skill already in the Hermes home is reported `desired: true` / `readOnly: true`:
  Paperclip cannot toggle Hermes-installed skills, and **every skill in that home costs
  context in every agent's every turn**. Curate the *total* library size; a bulk import
  degrades all agents at once.
- Real per-agent skill scoping needs a per-agent `config.env.HOME` — and verify that the
  *run's* HOME actually follows it first, or the skill lands where the agent cannot read
  it.

State the trade-off plainly and let the user pick: one shared curated library (simple, no
machinery, no isolation) versus per-agent homes (real isolation, heavier, and it isolates
sessions and memory too).

**Default when the user just wants the skills available:** install them straight into
`~/.hermes/skills/` as real directories. Hermes-installed skills are `readOnly` to
Paperclip, so nothing evicts them and the library stops flapping — and on a shared home
that is the same coverage the toggles give, without the instability. Reach for the toggle
only when you actively want per-agent add/remove and accept the flapping.

## Adapting third-party skill collections

Generic collections written for other runtimes (the `npx skills` ecosystem and similar)
need auditing, not installing:

- Expect **near-duplicates** (several skills for one job) and **overlap with skills you
  already have**. Pick one winner per job and skip anything already covered.
- Audit each candidate's assumptions — paths, CLIs, runtime layout, which agent product
  it targets — and adapt it for this setup rather than installing it raw. A skill naming
  tooling we do not have is clutter that also misleads.
- Judge by the `description` field, because that is what is loaded every turn; the body
  is only paid for on demand. Keep the total small enough that descriptions stay cheap.
- `npx skills` auto-detects Hermes as `hermes-agent` and installs to `~/.agents/skills/`.
  Confirm the target agent can actually see it afterwards: the CLI lists that path as a
  Hermes Agent location, but if the skill does not turn up in the agent's skill list,
  symlink it into the Hermes home rather than assuming the install landed where Hermes looks.
- Check `trustLevel` on imported skills (`markdown_only` vs `scripts_executables`) before
  attaching anything that ships scripts.
- **A framework offered as a Hermes plugin may be refused by the install scanner**
  (`Decision: BLOCKED — community source + dangerous verdict`, and `--force` does not
  override it — it is a deliberate gate, not a bug). The skills are the substance: install
  them as plain directories under `~/.hermes/skills/<pack>/` instead. Then say so **inside
  the pack's own entry skill** — a bootstrap-style skill that claims to be always loaded
  is actively misleading once its `pre_llm_call` hook does not exist, so record that its
  mandate is advice rather than an enforced hook.

## Auditing the installed library for contradictions

An inherited or bulk-imported library accumulates skills that assume a *different* setup.
Audit by grep, not by reading 150 skills:

1. Scan every loaded `SKILL.md` for patterns that would actively mislead — another
   issue tracker (`gh issue create`, `Closes #123`), another runtime (`CLAUDE.md`,
   `.claude/hooks`, Cursor rules), another OS (`/Users/`, `brew install`), a viewer you
   dropped, per-agent profile paths.
2. **Triage each hit before deleting.** Most hits are legitimate subject matter: a skill
   *about* the Claude Code CLI, or one explaining the `CLAUDE.md` file format, carries
   knowledge. Only a skill that would *instruct* the agent to do the wrong thing, or that
depends on something removed, is a contradiction. Deleting on a keyword match destroys
knowledge.
3. **Fix before deleting where the skill is only misconfigured.** A pack that looks like it
   hard-codes GitHub is often **tracker-agnostic** — it reads a tracker description from a
doc and merely has none written. Write that doc declaring the real tracker, then repoint
   the skills that reference it. Deleting a capable skill because its default is wrong is
the expensive mistake.
4. When you delete a skill, **grep for dangling references to it** in every other skill —
   `related_skills:` lists and prose pointers both survive the deletion and leave the
   library internally inconsistent.
5. Use **absolute paths** in cross-skill pointers. A relative path that is correct inside
   its own skill directory breaks the moment a sibling references it.
