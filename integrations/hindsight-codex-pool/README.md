# Hindsight Codex ↔ Hermes credential-pool adapter

Optional, version-specific compatibility patch. It is separate from the `account-usage`
plugin and does not change Hermes pool priorities or the plugin's report behavior.

## Compatibility boundary

- Hindsight: `hindsight-api-slim` **1.0.0** only. The provider patch targets the exact
  `hindsight_api/engine/providers/codex_llm.py` layout in that release.
- Hermes: **v0.23.0** only. The integration uses internal pool APIs that are not a stable
  public extension surface (`CredentialPool`, `try_refresh_matching`, `_mark_exhausted`).
  Apply `patches/hermes-agent-v0.23.0-codex-pool-refresh.patch` to the Hermes source before
  using the adapter: it directly re-reads the exact Codex row from the authoritative profile
  or borrowed-root auth store under its lock (bypassing the cached fallback) and fails closed
  if that row cannot be read.
- Apply the Hermes patch to every Hermes process that can refresh the same Codex pool row.
  An unpatched process can still refresh from a stale in-memory manual row. Re-review both
  source patches before upgrading Hermes.
- Each Hindsight manager also serializes token-bearing reclaim/refresh operations across
  concurrent calls, preserving single-flight behavior within that provider instance.
- Python: use the same interpreter/environment that the Hermes launcher uses for pool API
  calls. The adapter itself uses only the standard library plus the installed Hindsight
  and Hermes packages.
- Host validation: the artifact was exercised on macOS only; Linux and Windows were not
  verified. The bridge passes a curated child environment, and Windows-specific values such
  as `SystemRoot` and `APPDATA` are not forwarded; do not assume Windows support without a
  separate compatibility check.

This is a source patch, not an official Hindsight plugin interface, automatic installer,
service manager, or supported compatibility promise for future versions.

## Behavior and data boundaries

1. Hindsight `codex_home` values of `hermes-pool://<pool-label>` opt into the adapter;
   all normal `codex_home` values keep the existing `auth.json` path.
2. The adapter reads the persisted `openai-codex` rows with Hermes'
   `read_credential_pool()` and binds each Hindsight member to one unique label. Configure
   distinct stable labels. Do not rely on the first row, current account, or Hermes pool
   order to select an account.
3. Pool tokens and the selected Hermes account ID travel only through a private subprocess
   pipe into Hindsight memory. They are not command-line arguments, written to a second
   `auth.json`, or intentionally logged. The refresh token remains owned by Hermes.
4. Refresh and status writes target the exact credential ID bound at read time. The helper
   constructs a `CredentialPool` from the stored rows rather than calling `load_pool()`;
   the latter may normalize and persist priorities. It verifies the ID/priority order
   before and after a mutation and refuses malformed rows instead of normalizing them.
5. Only a recognized Codex usage-window 429 with a reset time updates the exact Hermes
   row. A generic/transient 429 is left alone. Hindsight's configured failover member
   order controls the next provider; the Hermes pool order is not changed.
6. Hindsight multi-LLM failover applies to interactive `call`/`call_with_tools` paths.
   Batch retain lifecycle is outside this patch's failover guarantee.

**cost:** event-driven, no timer or background polling. Each bridge operation starts one
local Hermes Python process: `read` when a provider manager is initialized, `reclaim` before
each Codex API call, plus `refresh` only when Hermes needs to rotate a token and
`mark_quota` only for a recognized usage-window 429. Each process has a 45-second timeout;
peak child-process concurrency is bounded by the Hindsight calls in flight (token-bearing
reclaim/refresh operations serialize per manager). The Hermes patch adds one persisted-row
read per refresh, but no extra subprocess or token-endpoint request. No retry loop or extra
upstream LLM request is added; refresh network traffic remains owned by Hermes.
Daily process count is determined by actual Hindsight call volume, not a fixed interval.

## Apply manually

Back up the relevant source files first. Check the Hermes source is exactly v0.23.0 and the
Hindsight distribution is exactly `hindsight-api-slim==1.0.0`. Do not apply either patch to
a different version.

1. From the Hermes v0.23.0 source root, dry-run and apply the refresh-safety patch:

   ```sh
   patch --dry-run -p1 < /path/to/hermes-ops/integrations/hindsight-codex-pool/patches/hermes-agent-v0.23.0-codex-pool-refresh.patch
   patch -p1 < /path/to/hermes-ops/integrations/hindsight-codex-pool/patches/hermes-agent-v0.23.0-codex-pool-refresh.patch
   ```

   Use the patched Hermes source in every runtime sharing the pool. The repository does
   not install it into an environment or restart services.

2. Copy `hermes_pool_codex_auth.py` into `hindsight_api/engine/providers/` in the target
   Hindsight environment. From that environment's `site-packages` directory, dry-run and apply:

   ```sh
   patch --dry-run -p1 < /path/to/hermes-ops/integrations/hindsight-codex-pool/patches/hindsight-api-slim-1.0.0-codex_llm.patch
   patch -p1 < /path/to/hermes-ops/integrations/hindsight-codex-pool/patches/hindsight-api-slim-1.0.0-codex_llm.patch
   ```

3. Set these environment variables for the Hindsight API process (not for a shell that
   will print secrets):

   | Variable | Value |
   |---|---|
   | `HINDSIGHT_HERMES_AGENT_ROOT` | Hermes Agent source checkout root |
   | `HINDSIGHT_HERMES_HOME` | Hermes profile home containing the intended credential pool |
   | `HINDSIGHT_HERMES_PYTHON` | executable for the Hermes Python environment |
   | `HINDSIGHT_HERMES_TMP` | optional scratch directory; defaults to `<HINDSIGHT_HERMES_HOME>/cache/scratch` |

4. For each Hindsight Codex member, set its `codex_home` to a configured pool label, e.g.
   `hermes-pool://primary` and `hermes-pool://backup`. Configure Hindsight's normal
   failover strategy and member order separately. Use the runtime-config field names for
   the installed Hindsight version; this adapter adds no Hindsight configuration parser.
5. Run the Hermes refresh regression suite and the isolated repository tests before arranging
   any service update. This repository does not install, restart, or roll back either service.

To roll back, restore the saved Hermes/Hindsight source files and remove the copied adapter
module. Do not restore or overwrite Hermes authentication data as part of rollback.

## Verification

The Hindsight patch applied and `py_compile` passed against a clean `hindsight-api-slim`
1.0.0 provider copy. The Hermes patch applied against clean Hermes Agent v0.23.0 sources;
the focused upstream refresh suite passed (100 tests, including the stale-manual-row and
borrowed-root-lock regression). The ten adapter tests use fakes and no real profile, token,
network, or service. A prior session reported a local backup-member smoke, but that private
runtime was not independently rechecked against this portable bundle and is not counted as
artifact verification. A fresh upstream 429 was not induced.

Run:

```sh
# From the patched Hermes v0.23.0 source root:
python -m pytest tests/agent/test_credential_pool.py tests/agent/test_credential_pool_codex_singleton_isolation.py tests/agent/test_credential_pool_oauth_writethrough.py tests/agent/test_credential_pool_profile_oauth_fork.py -q

# From the hermes-ops checkout:
python -m unittest discover -s tests -p 'test_hindsight_codex_pool_adapter.py' -v
```

## Files

- `hermes_pool_codex_auth.py` — subprocess bridge and exact-ID auth manager.
- `patches/hindsight-api-slim-1.0.0-codex_llm.patch` — opt-in provider integration.
- `patches/hermes-agent-v0.23.0-codex-pool-refresh.patch` — opt-in Hermes source fix for
  stale manual-row refresh and authoritative profile/root locking.
