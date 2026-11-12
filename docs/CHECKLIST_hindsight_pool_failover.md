# Hindsight Codex pool failover — portable Git artifact

**Started:** 2026-11-11
**Status:** awaiting operator review

## Scope agreed with the operator

- In: move the verified local Hindsight Codex/Hermes-pool failover into an anonymized, portable integration artifact in `hermes-ops`; add a separate Hermes v0.23.0 source patch so Codex refresh re-reads the exact row under its authoritative cross-process store lock; document the Hindsight member-order failover; add isolated tests; update project scope/docs; publish only task-owned files on a dedicated branch.
- Out: personal emails, local absolute paths, OAuth/access/refresh tokens, duplicate auth stores, changes to Hermes pool ordering, account-usage behavior changes, installing/restarting any service from this repository, merging a PR.
- Local runtime Hindsight 1.0.0 already has the integration; this repository artifact must be portable and must not reproduce its private account mapping.

## Portions

### 1. Package the integration safely
- [x] Inspect the local Hindsight 1.0.0 provider delta; define a generic pool-label URI and environment-driven Hermes paths.
- [x] Add a version-scoped provider patch, adapter source, application notes, and isolated tests without private identifiers or credentials.
- [x] Verify the patch against a clean Hindsight 1.0.0 source copy; test exact-ID refresh/429 bookkeeping and ordered failover with fakes.
- [x] Buffer bridge results until pool-order checks finish; emit exactly one response and add a focused isolated regression test.
- [x] Trace Hermes v0.23.0 refresh, persistence, and authoritative-store lock semantics; document verified guarantees and gaps.
- [x] Serialize concurrent adapter refreshes per provider instance and skip a forced refresh if another coroutine has already rotated its token.
- [x] Add a version-scoped Hermes v0.23.0 patch that re-reads the selected Codex pool row under the authoritative profile/root store lock before refreshing; preserve singleton authority, IDs, and priority order.
- [x] Add an isolated stale-manual-row regression, demonstrate it fails before the patch and passes after, and apply/compile the patch against clean Hermes v0.23.0 sources.
- [x] Keep the selected pool account ID out of provider logs and state the unverified host-platform boundary in the integration docs.

**Acceptance:** the repository contains re-applicable, version-labelled Hindsight and Hermes patches; tests use only temporary stores/fake tokens and no live profiles, network, or pool writes; secret scan finds no private account details.

### 2. Reconcile project records and gates
- [x] Add stable requirement/use-case/setup IDs; update project map, architecture, invariants, known errors, backlog, and regression index.
- [x] Replace the `dict(tuple(...))` workaround with a narrow exception for the known public XAI marker; preserve the literal runtime header and cover both the exact exception and nearby non-matches.
- [x] Re-run the configured finish gate after review-driven corrections; verify both version-scoped patches apply and compile, including the final Hermes v0.23.0 artifact.
- [x] After review, stage only task-owned paths, inspect the staged diff, and pass `commit-check`.

**Acceptance:** docs match the artifact and scope; all configured checks and counted evidence are recorded; staged paths are task-owned only.

### 3. Publish the task branch
- [x] Commit only reviewed task-owned files on `feat/hindsight-hermes-pool-failover`.
- [x] Push the branch and verify the remote ref resolves to the committed SHA; do not open or merge a PR.

**Acceptance:** remote branch and SHA are read back; existing dirty `main` work and its three local-only commits remain untouched.

## Deliberate limitations

- The patch targets only `hindsight-api-slim` 1.0.0; another provider version needs a fresh compatibility review and patch.
- Hermes account selection uses configured pool labels rather than guessing by pool order; labels must be unique and stable for the selected account.
- A prior session reported a local smoke through the backup, but that private runtime result was not independently rechecked against this portable bundle; a new upstream HTTP 429 was not induced, so status persistence is verified only with isolated fixtures/source inspection.
- A GitHub push publishes code/docs only; it does not change or install the local Hindsight runtime.

## Handoff

- Owner pause: lifted by the user's direct instruction to continue. Independent review and final checks are complete; the branch is pushed. Checklist remains active pending operator review/acceptance.
- Branch/base: isolated clean worktree, branch `feat/hindsight-hermes-pool-failover`, based on `origin/main` at `d9d8fd146e859bbf076e94624342a31555640e1e`.
- The separate original `main` checkout was left untouched; unrelated working-tree changes and local-only commits are not included in this branch. The installed Hermes checkout was briefly targeted by a failed patch invocation; only the two previously clean target files were restored, its generated `.orig`/`.rej` files removed, and status returned to the pre-existing unrelated dirty-file set.
- Current portion: the Hindsight helper buffers its response until pool-order checks complete, and each manager serializes token-bearing reclaim/refresh calls; isolated regressions prevent duplicate JSON output and duplicate forced refreshes. The Hermes v0.23.0 patch re-reads the exact authoritative profile/root row under its cross-process lock; its stale-manual-row test reproduced the old behavior for both stores and passed after the patch. The final artifact applied to a pristine v0.23.0 archive; 100 focused pool tests passed and `py_compile` succeeded. Independent review found no blockers; all three non-blocking findings were addressed. Commit `f887a7e269cd0bf810fda65365cf945c9550e519` is on the remote branch. No PR was opened; original dirty `main` and pre-existing Hermes checkout changes remain untouched.
- Decisions: target repo `hermes-ops`; user approved a portable anonymized patch and project-scope updates. No PR/merge requested.
- Verified before this checklist: repository itself has no Hindsight code; installed Hindsight distribution is `hindsight-api-slim` 1.0.0. A prior assistant report of live backup failover remains unverified and is not counted here.
- Checks/limitations: `commit-check` passed after staging (31 total tests, 0 skipped, 0 failures/errors); staged heuristic found 0 suspects in 66 text files / 358,015 bytes, with artifacts/history explicitly not checked. `git diff --cached --check` passed. Both patches applied and compiled; the final Hermes v0.23.0 patch passed 100 focused tests plus `py_compile` with one unrelated pytest/anyio deprecation warning. No live upstream 429, live multi-process refresh, or service update was performed. Linux/Windows runtime compatibility remains unverified. The local-only public-repo devlog is created and ignored by Git.
- Commit/push authorization was explicit and the requested push is complete; remote ref was read back at the committed SHA. No PR/merge was requested or opened.

## Product decisions or external authorization still needed

- None currently; the additional source-only Hermes patch was authorized on 2026-11-12.

## Deferred follow-up backlog (separate from this branch)

- [ ] Continue the Hindsight memory-workload estimate, excluding embeddings, using the owner-provided `docs/HINDSIGHT_MEMORY_USAGE_HANDOFF.md` in the original checkout. That handoff is not included in this compatibility branch; keep the estimate separate from account-quota repair and Codex pool failover.
