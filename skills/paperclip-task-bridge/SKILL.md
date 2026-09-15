---
name: paperclip-task-bridge
description: Create, comment on, update, and list Paperclip tasks from Hermes using scoped Paperclip API credentials.
---

# Paperclip Task Bridge

Use this skill when a Hermes-originated request needs to create or update Paperclip work directly. This is the Hermes-to-Paperclip direction, separate from Paperclip waking Hermes through the `hermes_local` or `hermes_gateway` adapter.

## Required Environment

Configure these in Hermes env/profile secrets, not in prompt text:

- `PAPERCLIP_API_URL` - Paperclip base URL, with or without `/api`.
- `PAPERCLIP_BRIDGE_API_KEY` - a Paperclip agent API key created with `scope.kind = "task_bridge"`.

Optional:

- `PAPERCLIP_API_KEY` - fallback env var for older profiles; it must still contain a `task_bridge` scoped key, never a full agent key.
- `PAPERCLIP_COMPANY_ID` - skips one identity lookup when set.
- `PAPERCLIP_AGENT_ID` - skips one identity lookup when set.
- `PAPERCLIP_RUN_ID` - sent as `X-Paperclip-Run-Id` on mutating requests when Hermes is running inside a Paperclip heartbeat.

Never print or paste API keys. The helper reads credentials from environment variables and only prints response summaries. Do not put a normal claimed agent API key in an internet-facing Hermes runtime; normal keys can use broad same-company Paperclip routes.

## Create a Bridge Key

Create the key from a board-authenticated Paperclip API session and store the returned token once:

```sh
curl -X POST "$PAPERCLIP_API_URL/api/agents/$HERMES_AGENT_ID/keys" \
  -H "Authorization: Bearer $BOARD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hermes task bridge",
    "scope": {
      "kind": "task_bridge",
      "parentIssueId": "00000000-0000-4000-8000-000000000000"
    }
  }'
```

Use `parentIssueId` or `parentIssueIds` when Hermes should only create child tasks under approved work. Use `projectId` or `projectIds` when the approved boundary is a project. A bridge key can create tasks only inside that boundary, can comment/update only bridge-created or assigned issues, and cannot use company-wide issue list/search/read surfaces.

## Helper

Run the helper from this skill directory:

```sh
node ./paperclip-task.mjs --help
```

Commands:

```sh
node ./paperclip-task.mjs list-assigned
node ./paperclip-task.mjs create-task --parent-id "00000000-0000-4000-8000-000000000000" --title "Investigate checkout failures" --description "Capture failing request and root cause."
node ./paperclip-task.mjs comment --issue PAP-123 --body "Found the failing request path."
node ./paperclip-task.mjs update-status --issue PAP-123 --status in_review --comment "Ready for review."
```

`create-task` defaults to assigning the task to the authenticated Hermes agent so the work is immediately actionable. Use `--unassigned` to create backlog work instead. Use `--assignee-agent-id <uuid>` only when the Paperclip API key has permission to assign work to that agent.

For multiline bodies, prefer files or stdin:

```sh
node ./paperclip-task.mjs create-task --title "Write rollout note" --description-file ./task.md
node ./paperclip-task.mjs comment --issue PAP-123 --body-file -
```

## Run-Context Guard on Bridge-Dispatched Wakes

A harness/bridge-dispatched Hermes run may arrive with **no Paperclip run context**: `PAPERCLIP_TASK_ID` empty, scratch dir named `paperclip-run-unassigned-<runid>`, and inherited `PAPERCLIP_AGENT_ID`/`PAPERCLIP_RUN_ID` from the dispatching agent (so the env identity can disagree with the injected run JWT — check `GET /api/agents/me` for the truth).

In that state the worker can read everything (identity, issues, comment threads, attachments) but **every issue-influence write is rejected with HTTP 403 `cross_issue_influence_run_context_required`** — comments and `PATCH` alike — even when `X-Paperclip-Run-Id` is set correctly. Allowed from the same run: `POST /api/issues/{id}/checkout`, `POST /api/issues/{id}/release`, `POST /api/companies/{companyId}/issues` (verified 200/200/201).

Practical rules:

- Do the work that only needs reads, then **report the blocked write** in the final response instead of retrying (bounded-write rule: stop after two consecutive failures of the same write).
- **Never `checkout` an already-completed issue from such a run.** `release` demotes `done` to `todo` and clears the assignee, and the guarded `PATCH` cannot put it back until a subtree exists.
- The guard is **subtree-based**: once the run creates a child issue under the target, the same `PATCH` with the same run id and header returns **200**. Issue-create is the durable fallback — create a self-contained child issue carrying the evidence and the exact restore steps, assigned to an agent whose normal assignment run will have real run context.

## Workflow Expectations

- Keep tasks company-scoped by using the company resolved from the scoped agent key.
- Let Paperclip activity logging come from the normal API endpoints; do not write local logs that include credentials.
- Use comments for durable progress.
- Use `update-status` only when the issue has a real disposition: `done`, `in_review`, `blocked`, `todo`, `in_progress`, `backlog`, or `cancelled`.
- Use `list-assigned` before creating duplicate work when the user asks about current Paperclip assignments.
