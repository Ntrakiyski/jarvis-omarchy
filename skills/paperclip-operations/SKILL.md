---
name: paperclip-operations
description: Operate Paperclip for the human's background work.
---

# Paperclip Operations (on your company)

Paperclip (github.com/paperclipai/paperclip) is the authoritative system for
projects, tasks, agent assignments, and background execution. Jarvis coordinates;
background workers execute bounded assignments. the human should not manually create
tickets or relay worker answers — Jarvis manages all of it.
## Identity model — one Jarvis, no second agent

There is exactly ONE Jarvis. the human talks to Jarvis only through Hermes (this desktop
app or voice); he never opens Paperclip. Paperclip is a tool Jarvis operates FOR
the human, not a second person. The **Jarvis** agent in Paperclip's org chart (role `ceo`)
is Jarvis's own seat as coordinator — NOT a separate agent or a second Jarvis. When
Paperclip wakes it (hermes_local adapter), it spawns a background Hermes process that
loads the same SOUL.md / memory / skills: the same identity working in the background.
The only real distinction is session scope — a Paperclip-woken run is a separate
process/session from the one the human is chatting in, so it shares identity and long-term
memory but not that particular live conversation.

## Naming: every job Jarvis starts is marked

Every job Jarvis creates in Paperclip — from voice, from this desktop, from a cron —
is titled `[Jarvis] <topic> · <YYYY-MM-DD HH:MM>`. The marker is load-bearing: the
Jarvis window's board filters on it, so an unmarked job is invisible to the person
watching. Build the string with `omarchy_voice.jobs.job_title(topic)` (repo:
Ntrakiyski/jarvis-omarchy); never rename an existing issue just to match.

## What was built (2026-09-13)

- **Server:** managed per-user install, `paperclipai` CLI at `~/.local/bin/paperclipai`
  (payload `~/.paperclip/cli/installs/npm/<version>`). Node.js v26 already present.
- **Service:** `paperclipai.service` (systemd user unit), enabled + active.
  UI/API on `http://127.0.0.1:3100`. Instance data: `~/.paperclip/instances/default/`
  (embedded Postgres, local file storage, encrypted secrets, logs).
- **Company:** "Example Co" — id `<company-id>`, prefix `FRA`.
- **Project:** "Ops" — id `<project-id>`.
- **Agents (all `hermes_local` adapter = Paperclip shells out to `hermes chat`):**
  - **Jarvis** (coordinator, role ceo) — id `<jarvis-agent-id>`
  - **Researcher** (role researcher; **manages the Scientist**) — id `<researcher-agent-id>`
  - **Engineer** (role engineer) — id `<engineer-agent-id>`
  - **Clients** (role cmo) — id `<clients-agent-id>`
  - **Scientist** (deep evidence work — paper analysis, lit review, code-claim audits,
    replication) — id `<scientist-agent-id>`
  - **Reviewer** (code review — owns the `ocr` / OpenCodeReview CLI; **reports to the
    Engineer**) — id `<reviewer-agent-id>`, role `qa`, hired 2026-09-14.
    Its method is the `open-code-review` skill; its charter is its managed `AGENTS.md`.
  **Org shape (the human's rule, 2026-09-13):** Jarvis keeps **three** direct reports —
  Researcher, Engineer, Clients. The Scientist sits **under Researcher**, and it is the
  Researcher's job to decide when to use it. The **Reviewer sits under Engineer** (the human's
  ask, 2026-09-14). Do not re-parent either seat to Jarvis.

  **Pin `adapterConfig.model` on every agent.** With `model=auto` the provider rejects
the request — HTTP 400 "The supported API model names are deepseek-flash,
deepseek-v4-pro, but you passed auto" — and the run dies as `adapter_failed` with no
worker output at all. When a heartbeat run fails instantly and silently, check the
model pin before suspecting the task.
- **Bridge:** Hermes→Paperclip direction uses the `paperclip-task-bridge` skill
  (`~/.hermes/skills/paperclip-task-bridge/`) + a `task_bridge`-scoped API key.
- **Credentials:** `~/.hermes/.env` — `PAPERCLIP_API_URL`, `PAPERCLIP_BRIDGE_API_KEY`,
  `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_AGENT_ID`. NEVER echo the key.
- **Company-side agent home.** Each Paperclip agent has its own home at
  `~/.paperclip/instances/default/companies/<companyId>/agents/<agentId>/` with
  `MEMORY.md` (tacit lessons), `life/` (PARA knowledge graph) and `memory/YYYY-MM-DD.md`
  (daily timeline), plus a managed `instructions/` bundle. The CEO agent's own
  instructions live at `.../agents/<ceoAgentId>/instructions/AGENTS.md`
  (HEARTBEAT.md / SOUL.md / TOOLS.md alongside it) — read those before acting as that agent.

## Environment (every Paperclip shell command)

```sh
export PATH="$HOME/.paperclip/cli/bin:$PATH"
CID=<company-id>
PROJECT=<project-id>
JARVIS=<jarvis-agent-id>
RESEARCHER=<researcher-agent-id>
ENGINEER=<engineer-agent-id>
CLIENTS=<clients-agent-id>
SCIENTIST=<scientist-agent-id>   # reports to RESEARCHER
REVIEWER=<reviewer-agent-id>    # reports to ENGINEER
```

**Re-equipping a seat** (no re-hire needed): edit the draft under
`~/.hermes/state/paperclip-agents/`, back up the live bundle
(`cp AGENTS.md AGENTS.md.bak.<ts>`), then
`paperclipai agent instructions-file:put <agentId> --path AGENTS.md --content-file <file>`
and read it back with `instructions-file:get` — a 201 is not proof the rule is live.
Hiring a new seat: `paperclipai agent hire -C "$CID" --payload-json "$(cat payload.json)"`
with `instructionsBundle.files["AGENTS.md"]` and `adapterConfig.toolsets` ending in the
agent's own `slm-<name>` server.

**The drafts in `~/.hermes/state/paperclip-agents/` drift behind the live bundles** (they predate
the dispatch-safety block that only the live bundles carry). Treat the live
`…/agents/<agentId>/instructions/AGENTS.md` as the source of truth: refresh the draft *from* it
before re-equipping, or a put from the stale draft silently deletes what the live bundle learned.
Verify with a hash comparison, not a 201 — `instructions-file:get` returns a JSON envelope, so
hash its `content` field, or just compare the on-disk bundle to the file you pushed.

## The two directions

1. **Hermes → Paperclip** (Jarvis creates/assigns/tracks work): use the
   `paperclip-task-bridge` skill helper — `node paperclip-task.mjs <cmd>` from the
   skill dir, with `PAPERCLIP_*` sourced from `~/.hermes/.env`. It reads the key
   from env and prints summaries only. Commands: `list-assigned`, `create-task`,
   `comment`, `update-status`.
2. **Paperclip → Hermes** (a worker executes a task): Paperclip's `hermes_local`
   adapter spawns `hermes chat` for the assigned agent. Triggered by assignment
   (or a `wake`/heartbeat). Workers run autonomously; their results appear as
   issue comments + work products/attachments.

## Task lifecycle (verified)

```sh
# create + assign to Engineer (bridge helper, from the skill dir):
set -a; . <(grep -E '^PAPERCLIP_' "$HOME/.hermes/.env"); set +a
node paperclip-task.mjs create-task \
  --title "..." --description-file /tmp/d.md \
  --assignee-agent-id "$ENGINEER" --project-id "$PROJECT" --priority low

# assignment itself opens an `assignment` run on this build — CHECK before waking anyone:
curl -s "http://127.0.0.1:3100/api/companies/$CID/live-runs"   # a run already on that issue?
paperclipai agent wake "$ENGINEER" -C "$CID" --reason "..."   # only when none exists

# monitor runs:
curl -s "http://127.0.0.1:3100/api/companies/$CID/live-runs"
# or: paperclipai service logs   (tail the server log)

# read a task:
paperclipai issue get FRA-1

# work products (results):
paperclipai issue work-products <issue-id>
```

### Registering a work product from a worker run (verified)

The *read* side is the CLI above; the *write* side is the raw API, callable from a
worker's own run context (`GET /api/openapi.json` is the schema source of truth):

```sh
api="${PAPERCLIP_API_URL%/}"; case "$api" in */api) ;; *) api="$api/api" ;; esac
jq -n '{type:"document", provider:"local-filesystem",
        title:"...", url:"file:///abs/path/artifact.md",
        status:"ready_for_review", isPrimary:true, summary:"..."}' | \
  curl -sS -X POST "$api/issues/$PAPERCLIP_TASK_ID/work-products" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID" \
    -H "Content-Type: application/json" --data-binary @- -w '\nHTTP=%{http_code}\n'
```

- Required: `type` (enum: preview_url · runtime_service · pull_request · branch ·
  commit · artifact · document), `provider`, `title`. Optional but useful:
  `url` (**must be a well-formed URI** — `file:///…` is accepted for an on-disk
  artifact), `status`, `reviewState`, `isPrimary`, `summary`.
- Returns 201 with the work-product id; `type:document` + `provider:local-filesystem`
  is the shape for an analysis written to disk. **Do not** attach a raw filesystem
  path in the `url` field without `file://` — schema validation rejects it.
- Multiline comments: `jq -n --arg comment "$(cat <<'MD' … MD
)"` then PATCH
  `/api/issues/$PAPERCLIP_TASK_ID` with `{status, comment}` — one call sets the
  disposition and posts the evidence, and the run id header is required on the write.
- **The field name differs per endpoint** — this is an easy 400: PATCH on the *issue*
  takes `comment`, while POST on `/issues/{id}/comments` takes `body`. The error is
  explicit (`path: ["body"] … expected string, received undefined`) but only if you
  read the response body; `curl -w '%{http_code}'` alone hides the reason. Note also
  that `GET /issues/{id}/comments` has returned a bare JSON **list** (not
  `{comments:[…]}`) on this server — parse for both shapes.
- **The comment list is newest-first, so a tail slice is not a write check.** Confirming your own
  comment with `jq '.[-2:]'` returns the two *oldest* comments and reads exactly like a failed
  write; verify with `length` plus a search for your own text (FRA-28, 2026-09-14).
- **A mention wake can re-deliver a hand-off a sibling run already executed.** Two runs of the same
  seat on the same issue ~40 s apart, woken by two different comments carrying the same ask
  (FRA-28: `ed1865c9` then `e2a66c92`). Read the applied state off the machine before acting: the
  second run's job is independent re-verification, never re-application, and the comment should say
  plainly that the decision was already taken. A re-apply on a promoted artifact is silent and
  destructive — it overwrites the reviewed file with itself.

## Accepted plan → child issues (the sanctioned decomposition path)

When a `request_confirmation` on an issue's `plan` document is accepted, the next wake
carries an *Accepted plan directive*: create children **from the approved plan only**, no
IC work on the source issue. Use the first-class route rather than ad-hoc issue creation:

```sh
jq -n --arg rid "<plan revisionId>" '{acceptedPlanRevisionId:$rid, children:[{
  projectId:"<project-id>", title:"…", description:"…",
  status:"blocked", priority:"high",
  unblockDescriptor:{owner:"board", action:"…"}}]}' | \
curl -sS -X POST "$api/issues/$PAPERCLIP_TASK_ID/accepted-plan-decompositions" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID" \
  -H "Content-Type: application/json" --data-binary @-
```

- Children are `createChildIssueSchema` objects (1–25); the server forces `parentId` to
the source issue and `requestDepth` +1.
- Guards: the revision must belong to that issue's `plan` document **and** carry an
accepted confirmation interaction, else 422. One decomposition per
`(sourceIssueId, revisionId)`, fingerprinted on the child set — an identical call
replays, a different set returns `409 … with a different child set`. **The child set is
a one-shot decision; do not call it twice.**
- It *creates* issues and cannot reference existing ones: a child dispatched **before**
acceptance (FRA-4 was) must be excluded or it gets duplicated. State that reasoning in
the closing comment so the reviewer can see the child set is complete, not partial.
- `blockedByIssueIds` inside a child object is silently dropped — PATCH the blocker edge
afterwards, then re-`GET` and read the resolved `blockedBy` array (`blockedByIssueIds`
reads back `null` even when the edge exists).
- Work the company cannot do itself (vendor runtime, a board decision) gets
`status: blocked` + `unblockDescriptor {owner:'board'|{agentId}|{userId}, action}` —
`unblockDescriptor` is rejected unless the status is `blocked`. Leave it unassigned so no
agent burns a run on it.
- Audit with `GET /api/issues/{id}/accepted-plan-decompositions` (claim `status`,
`requestedChildCount`, `childIssueIds`).
- Assigning a child of an issue to that issue's own author is refused (`code:
delegation_cycle`); a board operator assigning it is the sanctioned path — escalate that
ask in the plan's board-asks section instead of re-routing the work.

- **`POST /issues/{parentId}/children`** creates a child issue in one call (body:
  `projectId`, `title`, `description`, `priority`, `status`, `assigneeAgentId`) and returns
  **201** with the full issue — identifier assigned, `requestDepth` +1. Assigning it to a
  reporting agent is the wake: `GET /api/companies/$CID/live-runs` then shows a `running`
  run for that agent with `invocationSource: assignment`. Use this instead of the
  accepted-plan route when there is no approved plan to decompose. Verified 2026-09-14 (FRA-24).
- **`GET /issues/{id}/comments` and `/work-products` and `/runs` return bare JSON arrays**, not
  `{comments:[…]}` wrappers — a `jq '.[]'` parse is the right one (the `// .comments` form
  400s the parser).

## Binding a project workspace (so workers run *in* a repo)

A project with no workspace shows `codebase.origin: managed_checkout` and an empty managed
`_default` folder, so a worker's cwd is nothing useful. Bind a `local_path` workspace and every
run for that project gets its execution workspace at that cwd:

```sh
jq -n '{name:"mcp-use", sourceType:"local_path",
        cwd:"~/projects/your-project/mcp-use",
        isPrimary:true, visibility:"default"}' > /tmp/ws.json
paperclipai project-workspace create <projectId> --payload-json "$(cat /tmp/ws.json)" --json
paperclipai project-workspace list <projectId> --json       # verify it landed
```

Verified on FRA-21: the run's execution workspace (`GET /api/execution-workspaces/<id>`)
read back `strategyType: project_primary`, `mode: shared_workspace`, `cwd` = the bound path,
and the worker installed, built and ran the repo there. Pre-clone the repo yourself and tell
the brief not to re-clone — the workspace is used in place.

A bound run's scratch is `/tmp/paperclip-run-<issue-identifier>-<runId>/` and its
`.paperclip-run-scratch.json` carries companyId/agentId/runId/issueId: read that to confirm the
wake is really bound before trusting any env identity. Track a live worker by **evidence on
disk** (the exact paths the brief named, `ls -l <dir>`) plus `GET /api/issues/{id}/runs` for
status — not by polling its chat transcript.

### A repo the human is live in is not a worker's checkout (2026-09-15)

`~/projects/jarvis-voice` (remote `Ntrakiyski/jarvis-omarchy`, upstream `wombatoperator/omarchy-voice`) is a *foreground* project: a session switches branches and
edits files there while a worker may be running, and the repo's own `AGENTS.md` requires a separate
clean worktree when a checkout holds unfinished work. So paperclip work in that repo goes in a
worktree — `git -C ~/projects/jarvis-voice worktree add ~/projects/jarvis-voice-bootstrap -b <branch> main`
— and the brief declares the primary checkout read-only (no branch switching, no stash/reset/clean).
The same rule for any repo the human is live in; it is the working-tree form of "one writer per state layer".
**Publishing is a board decision**: push, visibility change and history
rewrites belong in every brief's forbidden list, and "so a friend can use it" is not authorization to
flip the repo public.

**Write every brief from the actual checkout, never from memory or a sibling repo.** On FRA-21
the Engineer caught two factual errors in a hand-written brief (a `pnpm` pin and a package path
I had copied from a different repository) and honoured the repo's own pin instead. Cheapest
fix: read the real clone's `package.json` / directory listing while writing the brief, and tell
the worker that a wrong brief is a finding to report, not a rule to obey.

**A parent brief's "verified facts" can still be wrong — re-verify them before anything is
built on top.** FRA-23's brief carried "verified" product-label numbers (20 mg/30 mg) that
turned out to belong to a *different* product variant; the real figures were double that, and
every dose calculation downstream of them would have been wrong. What made the difference:
reading the manufacturer's own product record and PDP directly rather than trusting the label
the brief pointed at — the giveaway was an image **alt tag** naming another flavour while the
panel graphic itself named no flavour at all. So: on a brief whose numbers drive arithmetic,
check the primary record (variant list, SKU, ingredients block), state the correction in the
closing comment as a finding rather than an erratum, and mark which rows are second-hand so the
next agent knows what still needs settling.

## Comment + status (Jarvis's own writes) — IMPORTANT

Jarvis manages task state through the **board-authenticated `paperclipai` CLI**, not
the bridge helper. Both are verified working:

```sh
# comment:
paperclipai issue comment <issue-id> --body "..."
# status (todo/in_progress/in_review/blocked/done/cancelled):
paperclipai issue update <issue-id> --status done --comment "..."
# reassign / move project:
paperclipai issue update <issue-id> --assignee-agent-id "$ENGINEER" --project-id "$PROJECT"
```

The `paperclip-task.mjs comment` / `update-status` subcommands **403** when run from
Jarvis's own shell: comment/status writes require a heartbeat-run context
(`X-Paperclip-Run-Id`, error `cross_issue_influence_run_context_required`), and a
bare bridge call is not inside a run. The bridge helper is for `create-task` +
`list-assigned` (which work fine); use the `paperclipai` CLI for comments and status.
This is the same root cause as the workers' FRA-3 defect (harness-dispatched wakes
have no run context) — but Jarvis is unaffected because the board CLI needs no run id.

### Write-guard facts measured from inside a bound run (2026-09-13)

- **Sibling issues are writable.** A run bound to issue A can `POST /issues/B/comments`
  and `PATCH /issues/B` on a **sibling** B — even one assigned to another agent — and get
  **201/200**. The cross-issue guard discriminates on the actor's own bound run, not on
  where the target sits relative to it (subtree matching is one way to satisfy it, not the
  only one). So a close-out run can fold evidence onto the source issue instead of
  bouncing it through a courier.
- **Document writes are the exception.** `PUT /issues/{id}/documents/{key}` on another
  agent's issue → 403 `Agent cannot mutate another agent's issue`, but on an *unassigned*
  issue it is unguarded and returns **201 even from an unbound run** — a runtime gap, not
  a permission to rely on.
- **`unblockDescriptor.owner` is self-only for agents.** `PATCH /issues/{id}` with
  `{unblockDescriptor:{owner:"board", …}}` → **403** `Agents may only name themselves as
  an unblock owner`. When an escalation's board ask needs amending, post the amendment as
  a comment on that issue and name "extend the unblock descriptor" as the board action;
  do not retry the PATCH.

### Duplicate dispatch: a run that is NOT the issue's execution run cannot write to it

Confirmed again on FRA-33 (2026-09-14) and **self-inflicted that time**: assigning an issue to a
seat already opens the bound `assignment` run, so the extra `paperclipai agent wake` I added to
be safe produced the unbound twin. Both ran the same brief; the unbound one finished first, was
refused `409 Issue run ownership conflict` on the PATCH, the checkout and twice on work-products,
and parked its comment in `COMMENT-not-posted.<run>.md` inside the deliverable directory — the
right call under the doctrine below, and a useful artefact, but a duplicate run is still waste.
Dispatch rule: **assign, then read `live-runs`; wake only if no run exists.**

Observed on FRA-6: one issue got **two** `hermes_local` runs about a second apart
(`edb43e5b…` at 12:47:27.247, `5eff1ad1…` at 12:47:28.277). Only the first was bound to
the issue's checkout; the second executed the same task in parallel and was refused on
both issue-write paths:

- `PATCH /issues/{id}` and `POST /issues/{id}/comments` → **403**
  `cross_issue_influence_run_context_required`, even with the correct
  `X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID`.
- Passing the issue's *own* run id instead → **422** `agent_jwt_run_id_mismatch`
  (`claimRunId` vs `headerRunId`). The header must match the signed JWT's claim, so
  this path is closed by construction — do not try to borrow another run's id.

**Diagnose before assuming a bug:** `GET /api/issues/{id}/runs` lists every run with
status; compare with `$PAPERCLIP_RUN_ID`. If your id is a *sibling* of a `running`/
`succeeded` run for the same issue, you are the duplicate. If your id is **absent from
that list entirely**, the wake was never bound to the issue at all (the duplicate-wake
shape, verified 2026-09-13 on FRA-7: the list held only the bound `assignment` run, and
the duplicate's `checkout` returned **409** with the owner's run id). Both readings end
in the same action: stand down, do not re-checkout, do not redo the work.

**Fast tells that you are the unbound duplicate** (all verified 2026-09-13, FRA-7 and
FRA-9):

- `$PAPERCLIP_SCRATCH_DIR` / `$PAPERCLIP_RUN_SCRATCH_DIR` contains
  `paperclip-run-unassigned-<your-run-id>` — the dispatcher spawned you with **no task
  context** even though your wake reason names an issue. `$PAPERCLIP_TASK_ID` is empty.
- `POST /issues/{id}/checkout` returns **409** whose body carries `checkoutRunId` **and**
  `executionRunId` — that is the id of the run that owns the issue; compare it with
  `$PAPERCLIP_RUN_ID` and `GET /issues/{id}/runs`.

- **Read your own run row first — one call, no forbidden probe.** `GET
  /api/companies/$CID/live-runs` returns every live run with `invocationSource`,
  `triggerDetail` and `issueId`. A genuinely unbound wake shows
  `"invocationSource":"on_demand"`, `"triggerDetail":"manual"`, `"issueId":null` **and**
  is absent from `GET /issues/{id}/runs` for every candidate issue — even when
  `PAPERCLIP_WAKE_REASON` describes a real, substantive brief. That settles it: you own
  no issue, so no comment/status write can succeed and no checkout should be attempted.
- **Match the wake reason against in-flight work.** An unbound manual wake whose reason
  paraphrases a live issue's brief (e.g. "stack audit: what changed in
  Hermes/MCP/Paperclip/SLM/harnesses; delegate version verification to the Scientist"
  vs. the brief of an issue already `running` under a bound run) is a **duplicate** of
  that issue's execution run, not new work. Locate the issue via `inbox-lite`/the
  company issue list, confirm its `activeRun` is `running`, then stand down. Filing a
  fresh issue for the same brief is the same mistake as re-running the first.

**Confirm the owner is actually alive before standing down.** A 409 alone does not prove
the sibling will deliver; two `hermes_local` runs of your own seat show up as two
`hermes chat` processes, and their transcripts are readable on this box:

```sh
ps -eo pid,etime,args | grep -F 'hermes chat' | grep -v grep   # sibling alive?
# map pid -> run id (the run id is inside that process's own -q prompt):
tr '\0' '\n' < /proc/<pid>/cmdline | grep -oE '[0-9a-f-]{36}' | sort -u
# map pid -> Hermes session, then read its last tool results:
#   ~/.hermes/runtime/active_sessions.json lists {pid, session_id, surface}
sqlite3 -readonly ~/.hermes/state.db \
  "select role, substr(content,1,200) from messages where session_id='<session>'
    order by rowid desc limit 5;"
```

If the sibling's transcript shows it reading real sources in its own
`/tmp/paperclip-run-<issue>-<runid>` workspace, the deliverable is being produced: stand
down for real (no artifact, no document, no second rank list — a duplicate brief on the
same issue is worse than silence), and let the bound run own comment and disposition. If
the sibling is dead or silent, the platform's liveness/recovery path owns the retry —
re-checking out is still forbidden.

**The filesystem is the part with no guard (FRA-36).** "Stand down, do not redo the work" protects
the issue and the API; it does **not** protect the disk. On FRA-33 an unbound duplicate executed the
same brief as the bound run and overwrote its one fixed artifact path (both wrote
`…/reviews/reviewer-first-run/out/review.json`; the bound run got no signal and only noticed by
re-reading the file), and the duplicate's residue was still in the shared tree after the issue
closed. The vector is **not** workspace isolation: the path the brief named sat *outside* the project
workspace cwd, so no workspace strategy could have helped. Rules — now in every seat's charter via
`instructions-file:put` (verified by read-back, and by finding the text in a freshly spawned run's
prompt) and in `~/projects/your-project/dispatch-and-artifact-policy.md`:

- A run with no bound issue is never an execution run, and stands down **before its first write**.
- Artifacts are run-scoped: write `…/out/runs/<run-id>/<file>`; only the issue's execution run
  promotes a canonical path, **last**, atomically (`<name>.tmp` then `mv`); every artifact carries
  `run_id` + `session_id`, and a run re-reads its own artifact before handoff instead of handing
  over someone else's file.
- A brief must never name one fixed absolute canonical path as the sole deliverable, and never a
  path outside the run's execution workspace — the Reviewer's own charter said "artifacts only
  inside the run workspace" and the brief overrode it, with the worker reasonably obeying the brief.
- **Ownership probe, one call:** `GET /api/issues/{id}` → `executionRunId` (and `checkoutRunId` while
  live) vs `$PAPERCLIP_RUN_ID`. Measured 2026-09-14 (all 37 issues, plus twice on FRA-36): non-null
  while a run is executing the issue, `null` for everything else — including FRA-37 seconds after its
  run finished and **FRA-36 the moment it was set to `done` while its closing run was still
  `running`**. The window closes *before* the run does, and an earlier note here claiming the field
  "stays set after the run finishes" was wrong. Treat it as a refusal gate, not as proof of liveness
  (`/companies/{cid}/live-runs` is liveness), and promote artifacts **before** the final status
  write or the guard refuses (exit 3, fail-closed). `/issues/{id}/runs` keys the id as
  **`runId`**, not `id` — reading `.id` returns null and invents a phantom duplicate.
- Duplicate dispatch is self-inflicted on this build: `issue create --assignee-agent-id` already
  wakes the seat, so the extra manual `agent wake` **is** the duplicate. Check live-runs first.
- Mechanical guard: `~/projects/your-project/bin/run-artifacts.sh` (`stage` / `promote` / `verify`) —
  built under FRA-37 (Engineer), independently re-verified by the FRA-36 execution run (30/30,
  `~/projects/your-project/evidence/fra-36/fra-36-guard-verification-20260914-1706.txt`), and named
  in all six seat charters. `stage <dir> <name>` prints the run-unique path; `promote <issue-id>
  <staged>` re-checks ownership and replaces the canonical path atomically; `verify <file>` re-reads
  provenance. It fails closed: exit 2 = no `$PAPERCLIP_RUN_ID`, 3 = REFUSED and nothing written,
  4 = foreign `run_id`. Use it instead of hand-rolling `tmp`+`mv` — a refusal is a finding to
  report, not a step to work around.
- **`run-artifacts.sh` stamps `run_id` only into JSON-object artifacts.** A markdown or text
  artifact is copied verbatim, and `verify` then prints `run_id: (absent)` yet still **exits 0** —
  so a clean verify proves nothing about provenance for those. Stamp `run_id` inside the artifact
  body yourself (state `session_id` as absent when the adapter does not export
  `$PAPERCLIP_SESSION_ID`) or the re-read before handoff is vacuous.

**What still works from an unbound run** (all returned 201 in the FRA-6 case):
`POST /companies/{cid}/issues/{id}/attachments`, `POST /issues/{id}/work-products`, and
`PUT /issues/{id}/documents/{key}`. **Only on an issue your own agent is assigned to:**
the same `PUT` against another agent's issue 403s `Agent cannot mutate another agent's
issue` (verified 2026-09-13 against FRA-3, owner Jarvis, `in_review`) — so evidence about
a defect on someone else's issue travels through the run response or your manager, not a
document write. On your own issue the write succeeds even while a bound sibling run owns
the checkout (201 on FRA-7). So the deliverable can still be placed on the issue
in full — put the artifact and the write-up there, then report in your final run
response, which is the sanctioned fallback channel. Do **not** re-PATCH, do not
`/release` the sibling's checkout, and do not retry a 409 checkout: the bound run owns
comment and disposition, and it will close the issue itself. State in the final
response that the status write FAILED and name this exact cause.

## The task_bridge key (gotchas)

- A `task_bridge` key REQUIRES a boundary: `projectId` or `parentIssueId`. With no
  boundary the API 400s.
- To ASSIGN work, the key's scope needs `allowedAssigneeAgentIds` listing the
  target agents — otherwise `create-task --assignee-agent-id` returns 403
  `deny_scope` ("Task bridge key cannot assign work to that agent").
- `paperclipai token agent create` only makes `standard` keys (no scope flag). For
  a `task_bridge` key use the raw API: `curl -X POST
  http://127.0.0.1:3100/api/agents/$JARVIS/keys -H 'Content-Type: application/json'
  -d '{"name":"...","scope":{"kind":"task_bridge","projectId":"$PROJECT",
  "allowedAssigneeAgentIds":["$JARVIS","$ENGINEER","$RESEARCHER"]}}'`. Capture the
  token to a mode-600 temp file, write it into `~/.hermes/.env`, never print it.
- Revoke old keys: `curl -X DELETE http://127.0.0.1:3100/api/agents/$JARVIS/keys/<keyId>`.

## CLI shape pitfalls

- `paperclipai agent list -C <id>` uses `-C`; but `agent heartbeat:invoke` does NOT
  accept `-C` (it takes only the agentId positional). `agent wake` DOES take `-C`.
- `company create` and `agent create` take `--payload-json`; `project create` does
  NOT — it takes `--name`, `--description`, etc. as flags.
- `issue get` / `issue work-products` take the identifier/ID as a positional with NO
  `-C` (they resolve company from the instance; only one company here).
- Watch shell quoting: payloads with apostrophes break `--payload-json '...'`;
  write JSON to a file and `--payload-json "$(cat file)"` instead.

## Monitoring — the attention watcher (LIVE)

Worker questions, plan approvals, failed runs and blockers land in Paperclip's
`attention` feed. Nothing surfaces them by itself, so a **systemd user timer** polls
it and notifies the human:

- `~/.hermes/scripts/paperclip-watch.sh` — reads
  `GET /api/companies/$CID/attention`, prints + `notify-send`s only items not seen
  before. Silent when nothing is new. State:
  `~/.hermes/state/paperclip-watch-seen.txt` (one `sourceKind:subjectId` per line).
- `~/.config/systemd/user/paperclip-watch.service` + `.timer` — every 15 min,
  `Persistent=true`, `enabled`. Manual run: `systemctl --user start paperclip-watch`.

**Why a systemd timer and not a Hermes `cronjob`:** Hermes cron delivery needs a
messaging platform (none is configured: `delivery_outcome: not_configured`), so a cron
job's *output* has nowhere to go. That is a delivery limit, **not** a scheduling one:
verified 2026-09-14, `~/.hermes/cron/ticker_heartbeat` refreshes every tick even while
`hermes gateway status` says "not running", and two manually fired jobs both returned
`status: completed`. So Hermes cron fires fine on this box as long as the desktop
backend runs — route the output to a file (as `self-improve-nightly.sh` does with
`learning/brief.md` + the served report page) and keep the systemd timer for things
that must survive a full desktop restart, or run `hermes gateway install`.

**To read the feed by hand:** `curl -s "$PAPERCLIP_API_URL/api/companies/$CID/attention"`,
or the UI at `/FRA/…`. Pending items block nothing but wait on the human — bring them to him.

## Worker instructions (current state)

Each agent has a **managed** instructions bundle at
`~/.paperclip/instances/default/companies/<cid>/agents/<agentId>/instructions/AGENTS.md`
(CEO 4.7 KB, workers 4.0 KB). These are Paperclip's **generic** defaults — they do NOT
yet carry the your company operating contract (user-space-only writes, never
`/usr/share/omarchy/`, GitHub = `Ntrakiyski`, reply in English). A worker that ignores
that could write outside user space. Fix when it matters: edit the bundle via
`paperclipai agent instructions-file:put <agentId> --path AGENTS.md --content-file …`.

## Skills across agents — the model, proven 2026-09-13

**All agents share ONE Hermes skill library.** Paperclip's per-agent skill toggles are
real (they write `paperclipSkillSync.desiredSkills` on that one agent, and the UI shows
`attachedAgents` per skill) — but on a shared `HERMES_HOME` the **delivery is not
isolated**: the adapter materialises an attached skill as a symlink into the shared
`~/.hermes/skills/`, so every agent loads it. Worse, each agent's run *reconciles* that
shared dir to its own desired set, so skills a different agent attached get pruned —
the library **thrashes** to whichever agent ran last. Observed: attaching `agent-browser`
to Researcher+Scientist removed Clients' `email-draft-polish` from the shared home.

So: **scope per-agent behaviour with TOOLSETS, never with skills.** Toolsets are genuinely
per-agent (proven with the `slm-*` MCP identities); skills are global.

The reconciliation seam (`hermes-paperclip-adapter/dist/server/skills.js`):

- `readPaperclipRuntimeSkillEntries` reads `config.paperclipRuntimeSkills` or the
  **adapter's own bundled** dir — *never* the company library.
- Anything already in `~/.hermes/skills/` is reported `desired: true` + `readOnly: true`
  (*"Hermes loads all available skills"* / *"Paperclip can't toggle them"*). That is why
  the UI lists them under **"Detected on adapter (read-only)"**.
- The prune only unlinks symlinks resolving to a Paperclip-managed source
  (`targetPath !== available.source` → skip), so it **cannot** delete your own skills.
- **Skills installed directly into `~/.hermes/skills/` are stable** — Paperclip treats
  them as read-only and never touches them. That is the recommended way to add skills.

Company skill library on disk: `~/.paperclip/instances/default/skills/<companyId>/` —
`<name>/` for UI-created or imported, `__catalog__/<name>--<hash>/` for catalog installs
(with a pristine copy in `__catalog_origins__/`). **Local import requires the source to
sit under that managed root or a project workspace `cwd`** (`skill_workspace_boundary_denied`),
and a **GitHub import of a private repo fails** (the server has no token).

Per-agent **skill** isolation is only reachable by giving an agent its own `HERMES_HOME`
(= a Hermes profile). That trades away the Paperclip skill UI, because the adapter's
reconcile writes to `<config.env.HOME or os.homedir()>/.hermes/skills` and does not know
about profiles.

## The Reviewer seat and its tool (`ocr`)

A second **code** seat exists under the Engineer: **Reviewer** (`<reviewer-agent-id>`, role `qa`,
`hermes_local`, model pinned `deepseek-flash`, toolsets ending in its own `slm-reviewer`).
Hired 2026-09-14 on the human's ask so no change lands on the Engineer's own say-so.

Its tool is **OpenCodeReview** (`ocr` v1.12.1) — installed from npm in user space, wired to
the DeepSeek provider (`deepseek-flash`, review `effort=high`, telemetry off, English
output), config at `~/.opencodereview/config.json` with the key pulled at run time from
`~/.hermes/.env` by the CLI's own `api_key_cmd` (never copied into that file).

- Command: `~/.local/bin/ocr` (symlink → mise node bin → the package launcher). A worker
  reporting `ocr: command not found` means that symlink is missing, not a broken install.
- Procedure, output contract, pitfalls, and the vendored upstream corpus: the
  **`open-code-review`** skill. Verify the CLI's own path with `ocr llm test`.
- Review task shape that works: brief names the **absolute** repo path and an **absolute**
  artifact directory under `~/projects/your-project/reviews/<slug>/`, the exact `ocr review`
  command, and demands the coverage receipt (`session_id`, `summary`, `manifest.coverage`) in
  the closing comment. First run: FRA-33.

### Graph-first + a bounded run (2026-09-15, after the Greptile head-to-head)

Both seat charters now carry this (verified by read-back from the live bundles):

- **Engineer builds the graph on handoff.** `graft build <repo>` (0.18.0, local tree-sitter, no
  network/install) writes `<repo>/graft/`; the handoff names that path, or writes **"graph absent"**.
  Built 2026-09-15 for `~/projects/your-project/mcp-use` (46 MB graph) and `~/projects/jarvis-voice`.
- **Reviewer navigates the graph first** — `graft INDEX.md` / `skeleton` / `callers` / `ask` — and
  passes the graph paths to the tool via `--background-file`, so the review agent doesn't rediscover
  the repo by grepping it. A missing graph is a gap it reports, not a blocker, and a review run writes
  nothing into the repository.
- **House review rules live in `~/.opencodereview/rule.json`** (global): graph-first, verify
  existence before claiming absence, anchor every finding, report-only, name what wasn't covered.
  Repo-local `<repo>/.opencodereview/rule.json` overrides it. **OCR applies only the FIRST matching
  rule** — keep the whole policy in one rule text.
- **Bounded invocation**: `--max-tokens-budget 4000000 --timeout 8 --concurrency 8` plus
  `--exclude '**/node_modules/**,**/dist/**,**/build/**,**/*.min.js,**/*.snap,**/*.map'` (never
  exclude `tests/`). Measured spread before the bounds: 0.4 M–11.6 M tokens, 2–15 min per PR; the
  budget is the knob for both, and `manifest.coverage.failed[].classification` (`budget`, …) is what
  a partial run reports. Never read a partial run as "no defects here".
- **The human's decision (2026-09-15): no GitHub-Actions trigger for now** — reviews stay seat-initiated
  (Engineer handoff child issue; Jarvis creates it when verifying if the Engineer forgot).

**Standing rule (the human, 2026-09-14): repo work is not finished until it has been reviewed — local
work is not reviewed at all.** the human's words: *"the engineer when he gets a task should know to use
the reviewer at the end … this is for cases where we have a github repo attached to the project.
when we are doing local things we don't care about a review."*

The decision is made on the repo the change lands in, with one command:
`git -C <repo> remote get-url origin` — contains `github.com` ⇒ hand off to the Reviewer; no remote
(or a non-GitHub one) ⇒ local-only, no review. **Do not decide from the project record:**
`codebase.repoUrl` is `null` on this instance even for the GitHub clone
(`workspaces[].sourceType = local_path`), so the clone's remote is the truth.

There is **no platform trigger** for any of this — Paperclip routine triggers are `schedule` |
`webhook` | `api` only (read off the OpenAPI document; no issue-event kind), and the human explicitly
does not want one. The default lives in two places and both are needed:

- **Engineer's charter** (`## Code review — GitHub-backed repos only`): hands off by child issue with
  `assigneeAgentId` = Reviewer and keeps its own issue `in_review` until that child closes; writes
  "local-only, no review" when it skips.
- **Jarvis's check** (this skill, and §7 of `foundation`): when verifying an Engineer issue that
  changed code **in a GitHub-backed repo** and no review child exists, create it before closing the
  parent. A charter rule is a default, not a guarantee — the coordinator is the backstop.
- **`in_review` needs a first-class path, and a review child is not one.** `PATCH … {status:in_review}`
  is refused with `invalid_issue_disposition: missing review_path` when the only thing owning the next
  action is a review child plus `blockedByIssueIds` (the accepted paths are a pending issue-thread
  interaction, a linked pending approval, `assigneeUserId`, a typed
  `executionState.currentParticipant`, or `monitorNextCheckAt`). Send both in the one PATCH:
  `blockedByIssueIds:[child]` **and** `executionPolicy.monitor` with `nextCheckAt`, `timeoutAt`,
  `maxAttempts`, `serviceName`, `externalRef`, and `kind` exactly `"external_service"` —
  `kind:"issue_review"` is rejected with a 400 `invalid_value`. Confirm from that same response that
  `status`, `monitorNextCheckAt` (non-null), `assigneeAgentId` (set) and `assigneeUserId` (null) all
  landed. Verified 2026-09-15 on the Engineer's FRA-42 → review child FRA-50.

Both seat charters were re-equipped and read back (`instructions-file:put` → `…:get`) on
2026-09-14; backups in `~/.hermes/backups/paperclip-instructions/<seat>/`.

## Opening the UI — web app + shortcut (LIVE)

Paperclip is installed as a **web app** so it opens as a chromeless window:

- **`SUPER + SHIFT + J`** — focuses the Paperclip window if open, else launches it.
  (Bound in `~/.config/hypr/bindings.lua` via
  `o.launch_sole("Paperclip", "$HOME/.local/bin/orch-browser --app=http://127.0.0.1:3100")`.)
- **App menu** — a **Paperclip** launcher at
  `~/.local/share/applications/Paperclip.desktop` (icon
  `~/.local/share/icons/hicolor/256x256/apps/paperclip-icon.png`, made from the
  server's `favicon.ico`).
- Both exec the **Orch Browser** with `--app=…` — NOT `omarchy-launch-webapp`, which
  falls back to `chromium.desktop` (the human's OLD profile). Keep the custom exec if this
  is ever regenerated.

## Service / recovery

```sh
paperclipai service status      # supervisor + health
paperclipai service logs        # server log tail
paperclipai service restart     # hot-restart, preserves active runs
paperclipai doctor             # diagnostics
```

- Reconnect after reboot: the service is `enabled`, so it auto-starts. Just
  `paperclipai health` (or open http://127.0.0.1:3100) to confirm.
- Re-running setup is idempotent: `onboard --yes` keeps existing config;
  `company create` with the same name would make a duplicate — check `company list`
  first and reuse the `your company` company rather than recreating.
- The UI is a React SPA; right after `orch-cdp open <url>` it briefly reads
  "Loading…" while it hydrates. Read the current tab's body with
  `orch-cdp eval "document.body.innerText.slice(0,2000)"` (no URL arg = no re-nav)
  instead of re-opening the URL each time.

## Operating model (the human's rules)

- Answer directly for quick questions; open a Paperclip task for substantive work.
- Hand longer jobs to a worker promptly; stay available in the foreground chat.
- A background job keeps running if the human interrupts speech or changes topic —
  "stop talking" ≠ "cancel that task."
- Bring worker questions to the human with minimal context; route his answer back.
- Keep task status in Paperclip, durable knowledge in local files/Obsidian; link
  them, don't duplicate.
- Workers must not fight over the foreground desktop or switch the human's tabs.
