# Known errors — Hermes Account Usage Plugin

**What this is:** every known bug, limitation, and piece of technical debt.
**Read it before** "fixing" anything or explaining odd behaviour — the thing may already
be recorded, with a workaround and a reason.
**Update when:** any bug or limitation is found, during development, testing, or review.
See `AGENTS.md` section 3.

## Entry format

Identifier: `KE-YYYY-MM-DD-SHORT-SLUG`. Stable, so code comments can quote it — that is
how the reason for a non-obvious defence survives the next refactor.

```
### KE-2026-01-31-EXAMPLE-SLUG — one-line summary

**Where:** path/to/file.ext:123
**Introduced / detected:** commit or unknown / date and evidence
**Impact:** what the user or the data actually loses. Not "it is wrong" — what breaks.
**Cause:** the mechanism, in one or two sentences.
**Status:** not fixed / fixed in <commit or version>
**Workaround:** what to do until it is fixed, or "none".
**Verification:** regression test, observed result and coverage limitations
```

Rules:

- A fixed entry is **marked** fixed, with the commit or version. It is not deleted:
  the same mistake gets made again, and the record is what makes it recognisable.
- State the affected scope precisely. A local fix is not proof every consumer is fixed.
  Separate confirmed defects, hypotheses and accepted risks; do not invent dates.
- If a defence in the code exists because of an entry here, the code comment names the ID.

## Open

### KE-2026-11-11-HINDSIGHT-CODEX-POOL-ADAPTER — Hindsight Codex provider does not natively use Hermes' rotating credential pool

**Where:** Hindsight `hindsight-api-slim` 1.0.0 Codex provider; optional artifact in `integrations/hindsight-codex-pool/`
**Introduced / detected:** detected 2026-11-11 by source inspection; the provider reads one Codex auth file while Hermes exposes a multi-row pool
**Impact:** without an adapter, Hindsight cannot bind each failover member to a distinct Hermes pool row without duplicating rotating tokens into separate auth files
**Cause:** Hindsight's provider expects one auth file; Hermes pool selection, refresh, and status methods are version-specific. Calling Hermes `load_pool()` may normalize and persist priorities, so the adapter must use a non-normalizing construction path and verify the stored order.
**Status:** version-scoped workaround documented for Hindsight 1.0.0 / Hermes v0.23.0; upstream-native support remains open
**Workaround:** apply both optional version-scoped patches after checking exact versions, ensure every Hermes process sharing the selected pool uses the refresh patch, and configure stable pool labels; do not copy OAuth values into another auth store
**Verification:** ten isolated adapter tests; Hindsight patch application/compile against a clean 1.0.0 provider; paired Hermes v0.23.0 patch application and focused 100-test pool suite. A prior session reported a local backup-member smoke but it was not independently rechecked against this bundle; no new upstream 429 was induced

### KE-2026-11-12-HERMES-CODEX-STALE-POOL-REFRESH — a waiting process can refresh a stale manual Codex row

**Where:** Hermes v0.23.0 `agent/credential_pool.py` (`CredentialPool._refresh_entry`, `_sync_entry_from_auth_store`)
**Introduced / detected:** detected during read-only source review on 2026-11-12; the refresh selects an in-memory row before acquiring the cross-process lock, while the locked sync only follows matching singleton-backed sources
**Impact:** after another process rotates a manual row's single-use refresh token, a waiter may submit the consumed token and fail or misclassify the credential
**Cause:** the auth-store lock serializes refresh POSTs and writes, but manual pool rows are not re-read from their authoritative pool store after the lock is acquired; a borrowed global-root row may also require a root-target lock
**Status:** mitigated by the optional version-scoped Hermes v0.23.0 patch in this branch; unpatched Hermes processes sharing the same pool remain affected
**Workaround:** apply the patch to every Hermes process sharing the pool; until then, avoid overlapping refreshes of the same manual Codex row across processes
**Verification:** synthetic RED before the patch showed duplicate refresh-token submissions for both profile-owned and borrowed-root stores, including a stale simulated global-root fallback; the patched direct-store-read regression passed for both. Patch applied to clean v0.23.0 sources; focused Hermes pool suite passed 100 tests. No live multi-process refresh or service update was performed

### KE-YYYY-MM-DD-... — ...

**Where:**
**Introduced / detected:**
**Impact:**
**Cause:**
**Status:** not fixed
**Workaround:**
**Verification:**

## Fixed

### KE-YYYY-MM-DD-... — ...

**Status:** fixed in ...

### KE-2026-11-12-HINDSIGHT-BRIDGE-RESPONSE — bridge could emit success before an order-check error

**Where:** `integrations/hindsight-codex-pool/hermes_pool_codex_auth.py` (`_BRIDGE_CODE`)
**Introduced / detected:** detected during review on 2026-11-12; a synthetic mutation made the priority guard fail after the success response had already been printed
**Impact:** the Hindsight parent could not parse the helper's two JSON lines and could report an ambiguous result after a pool operation
**Cause:** reclaim/refresh/quota branches printed before the final in-memory and persisted pool-order checks
**Status:** fixed in the version-scoped adapter artifact; branch publication is tracked in `docs/CHECKLIST_hindsight_pool_failover.md`
**Workaround:** none
**Verification:** `test_bridge_emits_one_error_when_order_guard_rejects_mutation` failed on the old helper with two lines and passes after response buffering (one JSON error only); project `finish` passed with 29 tests, 0 skipped, 0 failures/errors

### KE-2026-11-12-HINDSIGHT-REFRESH-SINGLE-FLIGHT — adapter could force multiple sequential refreshes for one manager

**Where:** `integrations/hindsight-codex-pool/hermes_pool_codex_auth.py` (`HermesPoolCodexAuthManager.refresh_tokens`)
**Introduced / detected:** detected during review on 2026-11-12; a synthetic concurrent forced-refresh test observed two bridge refreshes before the guard
**Impact:** overlapping Hindsight calls could cause an unnecessary second rotation of a single-use OAuth token and race updates to the manager's in-memory token
**Cause:** the adapter override bypassed `CodexAuthManager`'s single-flight behavior while delegating to the pool directly
**Status:** fixed in the version-scoped adapter artifact; branch publication is tracked in `docs/CHECKLIST_hindsight_pool_failover.md`
**Workaround:** none
**Verification:** `test_concurrent_forced_refreshes_are_single_flight_per_manager` fails with two bridge refreshes before the guard and passes with one refresh afterward; project `finish` passed with 29 tests, 0 skipped, 0 failures/errors

### KE-2026-09-19-AGENT-QUOTA-ARCHAEOLOGY — agent needs 20 tool calls to answer a quota question without this plugin
**Where:** Hermes core v0.20.0 — `/usage` is a user slash command; no agent tool, no `hermes usage` CLI (also absent on upstream main, checked 2026-09-19)
**Introduced / detected:** detected 2026-09-19, `D:\DEV\Hermes\docs\research\gpt-account-limit-answer-audit.md`
**Impact:** 449 s, 17 model cycles, 20 tool calls, source-code reading and JWT parsing by the model for a one-line answer
**Cause:** capability exists only on the user-facing surface; the bundled `hermes-agent` skill points to "the internal account usage mechanism" without naming a command
**Status:** worked around by this plugin (2 calls / 56 s); root cause open upstream
**Workaround:** install this plugin; or type `/usage` yourself
**Verification:** end-to-end run on `mastermind`, session `20260919_212926_ad1a57`

### KE-2026-09-19-SUBPROCESS-CP1251 — `--all-profiles` printed a replacement character instead of the middle dot on Windows
**Where:** `plugin/account-usage/usage_core.py` (`all_profiles_reports`)
**Introduced / detected:** first `--all-profiles` run, 2026-09-19
**Impact:** cosmetic mojibake in per-profile headers when the child process used the console code page
**Cause:** `subprocess.run(text=True)` decoded stdout with the locale encoding (cp1251) while the child printed UTF-8
**Status:** fixed in v0.1 (`encoding="utf-8"` + `PYTHONIOENCODING=utf-8` for the child)
**Workaround:** none needed
**Verification:** re-run of `--all-profiles`; no automated test (needs a Windows console)

### KE-2026-09-19-PROVIDER-WITHOUT-FETCHER — resolved for xai-oauth (v0.4)

- **Owner, 2026-09-20:** «а почему xai не получаем лимит? должен быть способ его увидеть».
- **Found:** the official grok-cli reads its quota from the billing proxy `GET https://cli-chat-proxy.grok.com/v1/billing?format=credits` with the same OAuth bearer Hermes stores for `xai-oauth` plus a static header `X-XAI-Token-Auth: xai-grok-cli`. Core has no fetcher; upstream PR NousResearch/hermes-agent#114949 (open) adds one. Verified live: `creditUsagePercent 36`, weekly period with `end` timestamp, `productUsage[GrokBuild]`, `prepaidBalance`.
- **Fix:** `usage_for_xai()` in the plugin (`resolve_xai_oauth_runtime_credentials` → bearer → one GET → `xai_windows()` pure mapper → a `Weekly` window). Token never printed. Fail-soft like the other providers.

### KE-2026-09-19-PROVIDER-WITHOUT-FETCHER (original entry) — providers other than openai-codex/anthropic/openrouter/nous report `unavailable`
**Where:** `plugin/account-usage/usage_core.py` (`usage_for`)
**Introduced / detected:** design limitation, 2026-09-19 (the `default` profile on `nous` first showed "no snapshot" before the Nous credits branch was added)
**Impact:** a profile on gemini/kimi/copilot etc. gets no numbers
**Cause:** the host's `fetch_account_usage` covers three providers; we deliberately add no fetchers of our own
**Status:** accepted limitation
**Workaround:** `rarf/hermes-quota-plugin` covers 9 providers
**Verification:** message text asserted by `test_unavailable_snapshot_renders_reason`

### KE-2026-09-20-DESKTOP-USAGE-NO-LIMITS — Desktop `/usage` shows no account limits for openai-codex
**Where:** Hermes Desktop 0.20.0 (backend v0.20.0), `/usage` slash command in chat
**Introduced / detected:** detected 2026-09-20 by the owner during UC-001 acceptance (screenshot); matches upstream issues #45713 and #42904 (open)
**Impact:** in Desktop the operator cannot see Codex Session/Weekly windows at all without this plugin — `/usage` prints "Session Token Usage" with zeros before any agent turn and no Account limits block
**Cause:** upstream: the Desktop `/usage` no-agent path omits the account-usage fetch (per #42904 title); not investigated here
**Status:** not fixed upstream; worked around by asking the agent (tool `account_usage`)
**Workaround:** ask the agent in chat, or run `hermes -p <profile> usage`
**Verification:** manual, regression R-06; candidate for an upstream bug report with this repro

### KE-2026-09-20-PANE-STALE-ON-UNREGISTERED-USAGE — pane froze at "100% left" with `No number after minus sign in JSON at position 2`

- **Symptom (owner, 2026-09-20 16:04):** the pane kept showing Session 100 % / Weekly 89 % for an hour while the API said 41 % / 80 %; a red line `No number after minus sign in JSON at position 2 (line 1 column 3)` sat above a stale snapshot.
- **Mechanism:** `cli.exec` runs `hermes usage --json` in the Desktop's *active* profile. When that profile has no `account-usage` plugin (owner switched to a profile where it was not installed), the CLI prints argparse help `usage: hermes [-h] ...`; the old `parseJson` cut at the first `[` (= `[-h]`) and failed. The pane kept the last good reports and showed them as if current.
- **Fix:** `parseJson` starts at the first line that is exactly `[`/`{` and names the real cause (`usage` command not registered in the active profile); the error line now says "showing the last good snapshot". Plugin installed into every local home (`--profile mastermind --profile daria --global`) so `usage` exists whichever profile is active.
- **Prevention:** `python install.py` with no target now installs into every home (root + `profiles/*`). A profile created later: run the installer once more — the pane names the cause until then.

### KE-2026-09-20-CRON-BARE-INTERVAL-ONE-SHOT — `hermes cron create 60m` is a one-shot delay, not a schedule

- **Symptom:** the watchdog job showed `Schedule: once in 60m, Repeat: 0/1` — it would have run once and vanished.
- **Mechanism:** Hermes cron parses a bare `30m`/`2h` as "run once in"; recurring needs `every 60m` or a cron expression (`hermes cron create --help`).
- **Fix:** `install.py` normalises a bare `\d+[smhd]` to `every <interval>`; cron expressions and `every …` pass through unchanged. Verified: `Repeat: ∞`.
- **Watch for:** any other `cron create` call in scripts/docs using a bare interval.

### KE-2026-09-20-DESKTOP-SLASH-OUTPUT-DIM — Desktop renders every slash-command result at 11px and 60 % opacity
**Where:** Hermes Desktop 0.20.0, `apps/desktop/src/components/assistant-ui/thread/system-message.tsx:47-49` (`text-[0.6875rem] text-muted-foreground/60 w-[60%]`)
**Introduced / detected:** detected 2026-09-20 by the owner (`/usage` and `/quota` output barely readable)
**Impact:** multi-line command output (usage tables, quota reports) is hard to read; plain text only, no markdown
**Cause:** one style for all system lines, designed for one-line statuses; the code comment acknowledges multiline output needs more room but keeps the colour/size
**Status:** not fixed upstream; worked around by the Desktop pane (v0.3) and by asking the agent in words
**Workaround:** open the `quota` pane, or ask the agent — a normal assistant bubble
**Verification:** manual; candidate upstream PR: full colour and 12–13 px for multiline output
