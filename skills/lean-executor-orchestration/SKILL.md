---
name: lean-executor-orchestration
description: "Use when delegating code. Dispatch once; accept receipt."
version: 1.0.0
author: Trent Halden
license: MIT
metadata:
  hermes:
    tags: [delegation, cursor, claude, review]
    related_skills: [claude-code, hermes-agent]
---

# Lean executor orchestration

## When to Use

Use for a bounded development task delegated to Cursor, or for a narrowly triggered Claude review.

## Goal

The executor spends the implementation tokens and tool calls. The orchestrator sends one closed brief, receives a compact receipt, and decides accept, one correction, or block. Do not build an orchestration platform for normal development tasks.

## Roles

- **Cursor:** sole writer for source, tests, builds and task-scoped documentation.
- **Claude:** read-only plan or review only for a multi-component change, or a change touching security, authority, memory, delivery, runtime or installation. It is not a default second pass.
- **Orchestrator:** dispatches, checks the receipt and actual delta, then accepts, corrects once or blocks; does not recreate implementation work.
- **Owner:** resolves blocked work and separately authorizes commit, push, installation, restart or deployment.

## Dispatch

1. Capture the working-tree state without changing it.
2. Send one self-contained brief with `INTENT`, `DECISIONS`, `ALLOWED`, `FORBIDDEN`, `TASK`, `DONE MEANS`, one `GATE`, a one-pass limit and required receipt fields.
3. Require the final receipt: `FILES`, `GATE` command/result, `BOUNDARIES`, residual risk.
4. Run one executor session. If acceptance fails, send one resume/correction with the exact observed error. Do not start a fresh review cascade.

## Brief template

```text
INTENT: <one sentence>
DECISIONS: <already made; do not reopen>
ALLOWED: <paths/globs>
FORBIDDEN: commit, push, install, service/config/runtime changes, paths outside ALLOWED
TASK: <2–5 concrete steps>
DONE MEANS: <observable outcome>
GATE: <one command>
LIMIT: one pass; stop with the blocker if incomplete
RECEIPT: FILES; GATE command + concise result; BOUNDARIES ok|exception; residual risk
```

## Acceptance

Accept only when:

1. the receipt exists;
2. actual changed paths match `FILES` and remain inside `ALLOWED`;
3. the stated gate is the gate from the brief and succeeds;
4. `DONE MEANS` follows from the delta and gate;
5. a risk-triggered independent gate rerun, when required, succeeds.

Rerun the gate independently only when the task changes a security, authority, memory, delivery or runtime boundary; changes the gate itself; or has a receipt that conflicts with the actual delta. Do not add synthetic edge-case suites for normal work.

## Stop rules

- At most two executor runs per task: original plus one correction.
- At most one Claude review, only when its trigger applies.
- A forbidden effect, second failure or ambiguous outcome is `BLOCKED` for the owner. Do not widen scope, add agents or retry indefinitely.
- Keep any owner-set quota reserve in force.

## Kanban

Use Hermes Kanban only as a manual status journal when several independent tasks are active. Do not make it a required transport layer or build a custom runner/MCP integration unless the owner explicitly reopens that work.

## Limits

This is a cooperative workflow, not a sandbox. An executor may technically attempt writes outside scope; the post-run path check detects that rather than preventing it. Backend-compute cancellation proof, full crash recovery and adversarial executor containment are separate work, not prerequisites for lean delegation.
