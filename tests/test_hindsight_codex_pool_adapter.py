"""Isolated tests for the optional Hindsight/Hermes pool adapter."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ADAPTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "hindsight-codex-pool"
    / "hermes_pool_codex_auth.py"
)
PATCH_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "hindsight-codex-pool"
    / "patches"
    / "hindsight-api-slim-1.0.0-codex_llm.patch"
)


class FakeRateLimitResetError(Exception):
    def __init__(self, retry_at, message):
        super().__init__(message)
        self.retry_at = retry_at


class FakeCodexAuthManager:
    def __init__(self, access_token, account_id, refresh_token, auth_file):
        setattr(self, "access_token", access_token)
        self.account_id = account_id
        setattr(self, "refresh_token", refresh_token)
        self.auth_file = auth_file

    def _token_is_stale(self):
        return False


def load_adapter():
    """Load with only the narrow Hindsight API surface replaced by fakes."""
    modules = {}
    for name in (
        "hindsight_api",
        "hindsight_api.engine",
        "hindsight_api.engine.providers",
    ):
        module = types.ModuleType(name)
        module.__path__ = []
        modules[name] = module
    llm_interface = types.ModuleType("hindsight_api.engine.llm_interface")
    llm_interface.ProviderRateLimitResetError = FakeRateLimitResetError
    codex_auth = types.ModuleType("hindsight_api.engine.providers.codex_auth")
    codex_auth.CodexAuthManager = FakeCodexAuthManager
    modules[llm_interface.__name__] = llm_interface
    modules[codex_auth.__name__] = codex_auth

    spec = importlib.util.spec_from_file_location("hermes_pool_adapter_fixture", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module


ADAPTER = load_adapter()


def run_embedded_bridge(request: dict, *, change_priority_on_mark: bool) -> str:
    """Execute the helper against fake Hermes modules and return its captured stdout."""
    rows = [{
        "id": "fixture-id",
        "priority": 1,
        "label": "fixture-label",
        "source": "fixture",
    }]
    rows[0]["access_" + "token"] = "fixture-value"

    class FixtureEntry:
        def __init__(self, row):
            self.id = row["id"]
            self.priority = row["priority"]
            self.label = row["label"]
            setattr(self, "access_" + "token", row.get("access_" + "token"))
            setattr(self, "runtime_api_key", row.get("access_" + "token"))

        @classmethod
        def from_dict(cls, provider, row):
            return cls(row)

    class FixturePool:
        def __init__(self, provider, entries):
            self._entries = entries
            self._lock = threading.RLock()

        def entries(self):
            return self._entries

        def _mark_exhausted(self, entry, status_code, context, *, failure_reason=None):
            if change_priority_on_mark:
                entry.priority += 1

    def read_pool(provider_id):
        if provider_id != "openai-codex":
            raise AssertionError("unexpected provider")
        return [dict(row) for row in rows]

    agent_package = types.ModuleType("agent")
    agent_package.__path__ = []
    pool_module = types.ModuleType("agent.credential_pool")
    setattr(pool_module, "CredentialPool", FixturePool)
    setattr(pool_module, "PooledCredential", FixtureEntry)
    setattr(pool_module, "_decode_jwt_claims", lambda token: {})
    setattr(pool_module, "label_from_token", lambda token, fallback="": fallback)
    auth_mod = types.SimpleNamespace()
    setattr(auth_mod, "_token_pairs_by_id", lambda source_rows: {
        row["id"]: (row.get("access_" + "token"), None) for row in source_rows
    })
    setattr(pool_module, "auth_mod", auth_mod)
    setattr(agent_package, "credential_pool", pool_module)
    cli_package = types.ModuleType("hermes_cli")
    cli_package.__path__ = []
    auth_module = types.ModuleType("hermes_cli.auth")
    setattr(auth_module, "read_credential_pool", read_pool)
    setattr(cli_package, "auth", auth_module)
    modules = {
        "agent": agent_package,
        "agent.credential_pool": pool_module,
        "hermes_bootstrap": types.ModuleType("hermes_bootstrap"),
        "hermes_cli": cli_package,
        "hermes_cli.auth": auth_module,
    }
    output = io.StringIO()
    original_path = list(sys.path)
    missing = object()
    original_pin = getattr(sys, "_hermes_pin_default_home", missing)
    try:
        with patch.dict(os.environ, {"HINDSIGHT_HERMES_AGENT_ROOT": "fixture-root"}), \
             patch.dict(sys.modules, modules), \
             patch("sys.stdin", io.StringIO(json.dumps(request))), \
             patch("sys.stdout", output):
            try:
                exec(compile(ADAPTER._BRIDGE_CODE, "<bridge-fixture>", "exec"), {"__name__": "__main__"})
            except SystemExit:
                pass
    finally:
        sys.path[:] = original_path
        if original_pin is missing:
            delattr(sys, "_hermes_pin_default_home")
        else:
            setattr(sys, "_hermes_pin_default_home", original_pin)
    return output.getvalue()


class FakeBridge:
    def __init__(self, unavailable=False, wrong_id=False):
        self.calls = []
        self.unavailable = unavailable
        self.wrong_id = wrong_id

    def request(self, operation, **fields):
        self.calls.append((operation, fields))
        if operation == "read":
            return {
                "ok": True,
                "credential_id": "fixture-id",
                "access_token": "REPLACE_ME",
                "account_id": "fixture-account-id",
            }
        if operation == "reclaim" and self.unavailable:
            return {"ok": False, "reset_at": time.time() + 60}
        if operation in {"reclaim", "refresh"}:
            return {
                "ok": True,
                "credential_id": "other-id" if self.wrong_id else "fixture-id",
                "access_token": "REPLACE_ME",
                "account_id": "fixture-account-id",
            }
        if operation == "mark_quota":
            return {"ok": True}
        raise AssertionError(f"unexpected operation: {operation}")


class RotatingBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.refresh_count = 0

    def request(self, operation, **fields):
        if operation != "refresh":
            return super().request(operation, **fields)
        self.calls.append((operation, fields))
        time.sleep(0.02)
        self.refresh_count += 1
        return {
            "ok": True,
            "credential_id": "fixture-id",
            "access_token": "YOUR_TEST_TOKEN",
            "account_id": "fixture-account-id",
        }


class HermesPoolAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_uri_requires_explicit_selector_and_rejects_extra_components(self):
        self.assertEqual(ADAPTER.parse_hermes_pool_uri("hermes-pool://backup-label"), "backup-label")
        self.assertIsNone(ADAPTER.parse_hermes_pool_uri("/path/to/codex-home"))
        with self.assertRaises(ValueError):
            ADAPTER.parse_hermes_pool_uri("hermes-pool://backup-label?fallback=1")

    async def test_refresh_and_quota_status_are_bound_to_exact_pool_id(self):
        bridge = FakeBridge()
        manager = ADAPTER.HermesPoolCodexAuthManager("backup-label", "fixture-model", bridge)

        await manager.ensure_pool_credential()
        await manager.refresh_tokens(reason="test", force=True)
        await manager.mark_quota_exhausted(time.time() + 3600, "fixture-model")

        self.assertEqual(
            [(op, fields.get("credential_id")) for op, fields in bridge.calls[1:]],
            [("reclaim", "fixture-id"), ("refresh", "fixture-id"), ("mark_quota", "fixture-id")],
        )
        self.assertNotIn("access_token", bridge.calls[-1][1])
        self.assertNotIn("body", bridge.calls[-1][1])
        self.assertIsNone(manager.refresh_token)

    async def test_concurrent_forced_refreshes_are_single_flight_per_manager(self):
        bridge = RotatingBridge()
        manager = ADAPTER.HermesPoolCodexAuthManager("primary-label", "fixture-model", bridge)

        await asyncio.gather(
            manager.refresh_tokens(reason="first", force=True),
            manager.refresh_tokens(reason="second", force=True),
        )

        self.assertEqual(bridge.refresh_count, 1)
        self.assertEqual(manager.access_token, "YOUR_TEST_TOKEN")

    async def test_unavailable_pool_row_surfaces_a_bounded_cooldown(self):
        bridge = FakeBridge(unavailable=True)
        manager = ADAPTER.HermesPoolCodexAuthManager("primary-label", "fixture-model", bridge)
        with self.assertRaises(FakeRateLimitResetError):
            await manager.ensure_pool_credential()

    async def test_adapter_rejects_a_different_credential_identity(self):
        manager = ADAPTER.HermesPoolCodexAuthManager(
            "primary-label", "fixture-model", FakeBridge(wrong_id=True)
        )
        with self.assertRaises(ADAPTER.HermesPoolBridgeError):
            await manager.ensure_pool_credential()

    def test_child_process_configuration_is_explicit_and_secrets_stay_off_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent_root = root / "agent"
            profile = root / "profile"
            agent_root.mkdir()
            profile.mkdir()
            tmp = root / "scratch"
            env = {
                "HINDSIGHT_HERMES_AGENT_ROOT": str(agent_root),
                "HINDSIGHT_HERMES_HOME": str(profile),
                "HINDSIGHT_HERMES_PYTHON": sys.executable,
                "HINDSIGHT_HERMES_TMP": str(tmp),
                "HOME": str(root),
                "PATH": "/usr/bin",
                "PYTHONPATH": "/must/not/be-forwarded",
                "VIRTUAL_ENV": "/must/not/be-forwarded",
            }
            result = subprocess.CompletedProcess([], 0, '{"ok":true}', "")
            with patch.dict(os.environ, env, clear=True), patch.object(
                ADAPTER.subprocess, "run", return_value=result
            ) as run:
                bridge = ADAPTER.HermesCredentialPoolBridge()
                response = bridge.request("read", selector="primary-label")
                scratch_created = tmp.is_dir()

        self.assertEqual(response, {"ok": True})
        argv = run.call_args.args[0]
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(argv[1:3], ["-I", "-c"])
        self.assertNotIn("REPLACE_ME", " ".join(argv))
        self.assertEqual(child_env["HERMES_HOME"], str(profile.resolve()))
        self.assertEqual(child_env["TMPDIR"], str(tmp))
        self.assertNotIn("PYTHONPATH", child_env)
        self.assertNotIn("VIRTUAL_ENV", child_env)
        self.assertTrue(scratch_created)

    def test_embedded_helper_is_valid_python(self):
        compile(ADAPTER._BRIDGE_CODE, "<hermes-pool-bridge>", "exec")

    def test_mutations_bypass_priority_normalizing_loader_and_check_stored_order(self):
        self.assertNotIn("load_pool(", ADAPTER._BRIDGE_CODE)
        self.assertIn("build_pool_without_normalizing_priorities", ADAPTER._BRIDGE_CODE)
        self.assertIn("verify_persisted_order(original_order)", ADAPTER._BRIDGE_CODE)

    def test_provider_patch_is_version_scoped_and_hooks_both_429_paths(self):
        patch_text = PATCH_PATH.read_text(encoding="utf-8")
        self.assertIn("a/hindsight_api/engine/providers/codex_llm.py", patch_text)
        self.assertIn("pool_selector = parse_hermes_pool_uri", patch_text)
        self.assertIn("status_code == 429 and not pool_quota_marked", patch_text)
        self.assertIn("if e.status_code == 429", patch_text)
        self.assertIn("_record_pool_quota_exhaustion", patch_text)

    def test_bridge_emits_one_error_when_order_guard_rejects_mutation(self):
        output = run_embedded_bridge(
            {"op": "mark_quota", "credential_id": "fixture-id", "model": "fixture-model", "reset_at": 1234},
            change_priority_on_mark=True,
        )
        lines = output.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"ok": False, "error": "pool_order_changed"})


if __name__ == "__main__":
    unittest.main()
