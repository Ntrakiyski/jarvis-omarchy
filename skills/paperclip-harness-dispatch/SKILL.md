---
name: paperclip-harness-dispatch
description: >
  Use when dispatching a Paperclip worker run (agent wakeup / harness dispatch)
  that must write back to its issue. Bind the wake with payload.issueId, or the
  worker's every comment, PATCH and close returns 403
  cross_issue_influence_run_context_required / 409 ownership.
---

# Dispatching a Paperclip worker wake that can write

Verified on your company: Paperclip 2026.831.1 managed install
(`~/.paperclip/cli/installs/npm/2026.831.1/node_modules/@paperclipai`),
`hermes_local` adapter, 2026-09-13 (FRA-4 / FRA-3 / FRA-14 / FRA-15).

Run the dispatch commands exactly as written here. Do not invent a path.

## Rule 1 — bind the wake to the issue the worker acts for

`payload.issueId` (or `payload.taskId`) is the only field that gives a dispatched
run a source issue. `server/dist/services/heartbeat.js` → `enrichWakeContextSnapshot()`
copies `payload.issueId ?? payload.taskId` into `contextSnapshot.issueId` and
`contextSnapshot.taskId`; the guard reads it back.

```bash
api="${PAPERCLIP_API_URL%/}"; case "$api" in */api) ;; *) api="$api/api" ;; esac
ISSUE=<target-issue-uuid>            # the issue the worker writes on / closes
TARGET=${TARGET_AGENT_ID:-$PAPERCLIP_AGENT_ID}

jq -n --arg i "$ISSUE" '{source:"on_demand", triggerDetail:"manual",
  reason:"<what the worker should do>",
  payload:{issueId:$i, taskId:$i},
  forceFreshSession:true}' > /tmp/wake.json

curl -sS -X POST "$api/agents/$TARGET/wakeup" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID" \
  -H "Content-Type: application/json" --data-binary @/tmp/wake.json \
  | jq '{id,status,issueId:.contextSnapshot.issueId,scratch:.contextSnapshot.paperclipScratch.dir}'
```

Assert on the response: a **new** run id, `contextSnapshot.issueId` = your issue.
A bound run's scratch dir is named `paperclip-run-<issue-identifier>-*`; an
unbound one is `paperclip-run-unassigned-<runid>`.

**The target issue must be assigned to the worker's agent.** A bound run claimed
from the queue is cancelled before it starts when
`issue.assigneeAgentId !== run.agentId` (`errorCode: issue_assignee_changed`,
`heartbeat.js:9763-9771`; observed on runs `5261326b` and `a94a439d`, both bound
to unassigned issues). Binding alone is not enough: unassigned target → the wake
is created, stays `queued`, then dies silently.

The worker then gets `PAPERCLIP_TASK_ID` set to that issue and can
`POST /issues/{id}/comments` (200/201), `PATCH /issues/{id}` (200) and close it.
Cross-issue writes from a bound run are allowed up to 20 per run
(`CROSS_ISSUE_INFLUENCE_LIMIT`).

## Rule 2 — an unbound wake is write-dead (this is the classic failure)

With `payload.issueId` absent, `contextSnapshot.issueId`/`taskId` are null and
`server/dist/services/cross-issue-influence-limit.js` → `observeCrossIssueInfluence()`
throws for every comment/status write:

```
POST /api/issues/{id}/comments -> 403
{"error":"Cross-issue writes need a run to attribute them to (Heartbeat run context)...",
 "code":"cross_issue_influence_run_context_required"}
```

The 403 copy tells you to "send the X-Paperclip-Run-Id header" — that is
misleading. The header is fine; the run has no source issue. Fix the binding, not
the header.

Still allowed from an unbound run (do not mistake these for the fix):
`POST /api/companies/{cid}/issues` (201), `POST /issues/{id}/checkout` on a free
issue, and `PUT /issues/{id}/documents/{key}` on an issue nobody has checked out
(documents are not run-attributed) — that last one is a useful escape hatch for
leaving a record, and a gap worth reporting to the harness owner.

## Rule 3 — an unbound self-dispatch creates NO run (silent no-op)

`heartbeat.js` (non-issue wake path) coalesces a wake into an existing run of the
same agent when the **task key matches**: `sameScopeQueuedRun ?? sameScopeScheduledRetryRun
?? sameScopeRunningRun`, then `mergeCoalescedContextSnapshot()` writes the new
context into that run and returns it. Unbound wakes all share one heartbeat task
key, so dispatching an unbound "worker wake" while you are running merges into
*your own* run: the run's `contextSnapshot.wakeReason` is overwritten and the API
returns your existing run id — which looks like success.

Always compare the returned run id with your own, and bind the wake (Rule 1) so
the task key differs. On the issue path, `shouldDeferFollowupWakeForSameIssue()`
defers a same-agent wake that carries `wakeCommentId` or `forceFreshSession` into
a `deferred_issue_execution` wakeup row instead of starting a run.

## Rule 4 — checkout ownership blocks writes too

`server/dist/services/issues.js` (`adoptStaleCheckoutRun` / "Issue run ownership
conflict"): if another **live** run holds `checkoutRunId`/`executionRunId` on the
issue, even a correctly bound run gets `409` on `PATCH` and on document writes
(a stale/zombie checkout is adopted automatically; a live one is not). Comments
route precedence differs — it reports the cross-issue `403` first.

So: one live run per issue. If your sibling run owns the checkout, hand the write
to it instead of fighting for it.

## Rule 5 — the child env is not the child's identity

`hermes-paperclip-adapter/dist/server/execute.js` builds the child env as
`{...process.env, ...config.env, ...buildPaperclipEnv(ctx.agent)}` and re-asserts
only `PAPERCLIP_RUN_ID`, `PAPERCLIP_API_KEY` and (when bound) `PAPERCLIP_TASK_ID`.
`PAPERCLIP_AGENT_ID` / `PAPERCLIP_COMPANY_ID` can therefore be the **dispatching**
agent's values. Request bodies built from `$PAPERCLIP_AGENT_ID` then fail
(`403 Agent can only checkout as itself`). The API actor identity always comes
from the run JWT; check `GET /api/agents/me` before trusting the env var.

## Rule 6 — how to get a standalone `on_demand` run that can write (backlog seeding)

Every wake coalesces into an existing run of the same agent in the same task scope, so a
bound manual wake normally comes back as that existing run (usually the
`assignment/system` run the issue-create fired). To get a genuine `on_demand`/`manual`
run — the lane the FRA-3 defect lives in — seed the vehicle issue in **`backlog`** with
`assigneeAgentId` set to the worker:

```bash
# 1. POST /api/companies/$PAPERCLIP_COMPANY_ID/issues
#    {status:"backlog", assigneeAgentId:$ME, projectId:…, title:…, description:…} -> 201
#    queueIssueAssignmentWakeup() returns early for backlog
#    (services/issue-assignment-wakeup.js:4), so no assignment run holds this scope.
# 2. POST /api/agents/$ME/wakeup {source:"on_demand",triggerDetail:"manual",
#    payload:{issueId:$ID}} -> 202, status queued, invocationSource on_demand,
#    triggerDetail manual, contextSnapshot.issueId = $ID
```

Verified: run `711047c3-…` (FRA-20) — `succeeded`; the worker's comment returned **201**
and its `PATCH {"status":"done"}` returned **200** (`changes.status: in_progress → done`).
The same call shape against an already-woken assigned issue (FRA-14, FRA-18) returns that
issue's assignment run instead — the coalesced lane, not this one.

## Rule 7 — `checkout` rebinds *your own* run, not just the issue

`POST /api/issues/{id}/checkout` rewrites the calling run's `contextSnapshot.issueId`,
`taskId` and `taskKey` to the checked-out issue (observed on run `8bf30a3a`: FRA-4 →
FRA-15 after a self-checkout). Consequences:

- the cross-issue guard's "source issue" for a live run is whatever it last checked out;
- that issue's task scope now coalesces into your run, so a bound manual wake for it
  returns **your own run id** and starts no worker (observed: `8bf30a3a` returned itself
  after checking out FRA-15);
- checking out a vehicle issue just to assign it is self-defeating — use backlog seeding
  (Rule 6) instead.

Verified alongside: the 403 body in Rule 2 is the vendor's own denial copy
(`shared/dist/issue-write-denial.js:163-176`, `status:403`,
`boundary:"Heartbeat run context"`), and its "send the `X-Paperclip-Run-Id` header" advice
is wrong for a run-scoped JWT — a differing header is rejected with 422
`agent_jwt_run_id_mismatch` (`middleware/auth.js:263-278`).

## Open runtime defects to escalate (do not patch the managed install)

1. Env precedence leak above — `PAPERCLIP_AGENT_ID`/`PAPERCLIP_COMPANY_ID` are
   never re-asserted from `ctx.agent`.
2. The `cross_issue_influence_run_context_required` copy names the run header as
   the fix when the real cause is a missing issue binding.
3. Issue-document writes bypass the cross-issue guard entirely.
4. Coalesced / deferred wakes return a run object, so a dispatch that started
   nothing is indistinguishable from one that started a worker.

## Worked evidence (2026-09-13, company your company)

| run | dispatch | binding | result |
| --- | --- | --- | --- |
| `7ee731e1` | board `POST /agents/{id}/wakeup`, no payload | none | comment 403, PATCH 403, docs 201, self-wake coalesced into itself |
| `67568a6e` | agent wakeup + `payload.issueId`, target issue assigned | FRA-18 | comment 201, PATCH 200, issue closed — verified |
| `f21e681a` | agent wakeup + `payload.issueId`, target issue assigned | FRA-14 | worker wrote and closed FRA-14 |
| `5261326b` | agent wakeup + `payload.issueId`, target **unassigned** | FRA-15 | cancelled before start, `issue_assignee_changed` |
| `a94a439d` | agent wakeup + `payload.issueId`, target **unassigned** | FRA-16 | cancelled before start, `issue_assignee_changed` |
| `8bf30a3a` | assignment wake (issue comment) | FRA-4 | writes 200 (holds checkout) |

Source files: `server/dist/services/cross-issue-influence-limit.js`,
`server/dist/services/heartbeat.js` (`enrichWakeContextSnapshot`,
`shouldDeferFollowupWakeForSameIssue`, coalesce target),
`server/dist/services/issues.js` (run ownership), `hermes-paperclip-adapter/dist/server/execute.js:396-413`.
Read-only inspection only — the install is vendor-managed and replaced on update.
