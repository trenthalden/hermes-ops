"""Hindsight 1.0.0 adapter for one explicitly selected Hermes Codex pool row.

Install beside ``hindsight_api.engine.providers.codex_llm``. Pool credentials
cross only a private child-process pipe; this module never creates an auth file.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from hindsight_api.engine.llm_interface import ProviderRateLimitResetError
from hindsight_api.engine.providers.codex_auth import CodexAuthManager


class HermesPoolBridgeError(RuntimeError):
    """A safe, non-secret error from the Hermes credential-pool bridge."""


def parse_hermes_pool_uri(value: str | None) -> str | None:
    """Return the selected Hermes pool label from ``hermes-pool://<label>``.

    An email-shaped value remains accepted for compatibility, but stable,
    non-personal pool labels are recommended in Hindsight configuration.
    """
    if not isinstance(value, str) or not value.startswith("hermes-pool://"):
        return None
    parsed = urlsplit(value)
    selector = parsed.netloc
    if parsed.scheme != "hermes-pool" or not selector or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Invalid Hermes Codex pool URI; expected hermes-pool://<pool-label>.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}", selector):
        raise ValueError("Invalid Hermes Codex pool selector.")
    return selector.casefold()


# This code runs in Hermes' own Python runtime so its APIs and dependencies match
# the installed agent. Never pass a token as an argument or write it to a file.
_BRIDGE_CODE = r'''
import json, os, sys
root = os.environ.get("HINDSIGHT_HERMES_AGENT_ROOT", "")
if not root:
    raise SystemExit(2)
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)
os.environ.pop("VIRTUAL_ENV", None)
sys.path.insert(0, root)
sys._hermes_pin_default_home = True
import hermes_bootstrap
import agent.credential_pool as credential_pool_module
from agent.credential_pool import (
    CredentialPool, PooledCredential, _decode_jwt_claims, label_from_token,
)
from hermes_cli.auth import read_credential_pool

request = json.loads(sys.stdin.read())
op = request.get("op")
selector = str(request.get("selector") or "").casefold()
credential_id = str(request.get("credential_id") or "")
model = str(request.get("model") or "")

def fail(code):
    print(json.dumps({"ok": False, "error": code}, separators=(",", ":")))
    raise SystemExit(0)

def account_id(token):
    claims = _decode_jwt_claims(token)
    nested = claims.get("https://api.openai.com/auth") if isinstance(claims, dict) else None
    value = nested.get("chatgpt_account_id") if isinstance(nested, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else ""

def matching_entry(rows):
    matches = []
    for row in rows:
        token = row.get("access_token")
        if not isinstance(token, str) or not token:
            continue
        label = label_from_token(token, str(row.get("label") or ""))
        row_label = str(row.get("label") or "")
        if selector in {label.casefold(), row_label.casefold()}:
            matches.append(row)
    if len(matches) != 1:
        fail("credential_missing" if not matches else "credential_ambiguous")
    return matches[0]

def build_pool_without_normalizing_priorities():
    rows = read_credential_pool("openai-codex")
    if not rows:
        fail("credential_missing")
    entries = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row.get("id") or not isinstance(row.get("priority"), int)
                or isinstance(row.get("priority"), bool)):
            fail("pool_row_invalid")
        entries.append(PooledCredential.from_dict("openai-codex", row))
    pool = CredentialPool("openai-codex", entries)
    pool._persisted_token_pairs = credential_pool_module.auth_mod._token_pairs_by_id(rows)
    order = [(entry.id, entry.priority) for entry in pool.entries()]
    persisted_order = sorted(
        ((str(row["id"]), row["priority"]) for row in rows), key=lambda item: item[1]
    )
    if order != persisted_order:
        fail("pool_order_changed")
    return pool, order

def verify_persisted_order(expected):
    rows = read_credential_pool("openai-codex")
    if any(not isinstance(row, dict) or not isinstance(row.get("priority"), int)
            or isinstance(row.get("priority"), bool) for row in rows):
        fail("pool_row_invalid")
    actual = sorted(
        ((str(row.get("id") or ""), row["priority"]) for row in rows),
        key=lambda item: item[1],
    )
    if actual != expected:
        fail("pool_order_changed")

def output_entry(entry):
    token = str(getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "") or "")
    identity = account_id(token)
    if not entry.id or not token or not identity:
        fail("credential_incomplete")
    response = {"ok": True, "credential_id": entry.id, "account_id": identity}
    response["access_token"] = token
    return response

if op == "read":
    row = matching_entry(read_credential_pool("openai-codex"))
    identity = account_id(str(row.get("access_token") or ""))
    if not identity:
        fail("credential_incomplete")
    response = {"ok": True, "credential_id": str(row.get("id") or ""),
        "access_token": str(row.get("access_token") or ""), "account_id": identity}
elif op in {"reclaim", "refresh", "mark_quota"}:
    pool, original_order = build_pool_without_normalizing_priorities()
    if op == "reclaim":
        entry = pool.reclaim(credential_id, model=model)
        if entry is None:
            response = {"ok": False, "error": "credential_unavailable",
                "reset_at": pool.next_available_at(model=model)}
        else:
            response = output_entry(entry)
    elif op == "refresh":
        entry = pool.try_refresh_matching(credential_id=credential_id)
        if entry is None:
            fail("refresh_unavailable")
        response = output_entry(entry)
    else:
        entry = next((item for item in pool.entries() if item.id == credential_id), None)
        if entry is None:
            fail("credential_missing")
        context = {"reason": "usage_limit_reached",
            "message": "Codex usage window exhausted; Hindsight failover.",
            "reset_at": request.get("reset_at")}
        with pool._lock:
            pool._mark_exhausted(entry, 429, context, failure_reason="usage_limit_reached")
        response = {"ok": True}
    if original_order != [(entry.id, entry.priority) for entry in pool.entries()]:
        fail("pool_order_changed")
    verify_persisted_order(original_order)
else:
    fail("unsupported_operation")
print(json.dumps(response, separators=(",", ":")))
'''


class HermesCredentialPoolBridge:
    """Run narrow pool operations in the configured Hermes environment."""

    def __init__(self) -> None:
        self.agent_root = self._required_path("HINDSIGHT_HERMES_AGENT_ROOT", directory=True)
        self.hermes_home = self._required_path("HINDSIGHT_HERMES_HOME", directory=True)
        self.python = self._required_path("HINDSIGHT_HERMES_PYTHON", directory=False)
        scratch_value = os.environ.get("HINDSIGHT_HERMES_TMP")
        self.scratch = Path(scratch_value).expanduser() if scratch_value else self.hermes_home / "cache" / "scratch"
        self.scratch.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _required_path(name: str, *, directory: bool) -> Path:
        value = os.environ.get(name)
        if not value:
            raise HermesPoolBridgeError(f"Required Hermes integration setting is missing: {name}.")
        path = Path(value).expanduser().resolve()
        valid = path.is_dir() if directory else path.is_file()
        if not valid:
            raise HermesPoolBridgeError(f"Configured Hermes integration path is unavailable: {name}.")
        return path

    def request(self, operation: str, **fields: Any) -> dict[str, Any]:
        payload = {"op": operation, **fields}
        env = {
            "HOME": os.environ.get("HOME", str(Path.home())),
            "HERMES_HOME": str(self.hermes_home),
            "HINDSIGHT_HERMES_AGENT_ROOT": str(self.agent_root),
            "PATH": os.environ.get("PATH", ""),
            "TMPDIR": str(self.scratch),
            "PYTHONIOENCODING": "utf-8",
        }
        try:
            result = subprocess.run(
                [str(self.python), "-I", "-c", _BRIDGE_CODE],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=45,
                cwd=str(self.agent_root),
                env=env,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HermesPoolBridgeError(f"Hermes pool operation failed: {type(exc).__name__}.") from None
        if result.returncode != 0:
            raise HermesPoolBridgeError(f"Hermes pool helper exited with code {result.returncode}.")
        try:
            response = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            raise HermesPoolBridgeError("Hermes pool helper returned an invalid response.") from None
        if not isinstance(response, dict) or not response.get("ok"):
            code = response.get("error", "unknown") if isinstance(response, dict) else "unknown"
            if code == "credential_unavailable":
                return response
            raise HermesPoolBridgeError(f"Hermes pool operation rejected: {code}.")
        return response


class HermesPoolCodexAuthManager(CodexAuthManager):
    """Codex auth manager bound to one explicitly selected Hermes pool entry."""

    def __init__(self, selector: str, model: str, bridge: HermesCredentialPoolBridge | None = None) -> None:
        self.selector = selector.casefold()
        self.model = model
        self.bridge = bridge or HermesCredentialPoolBridge()
        initial = self.bridge.request("read", selector=self.selector, model=self.model)
        self.credential_id = str(initial["credential_id"])
        # The refresh token remains exclusively in Hermes' credential pool.
        super().__init__(
            access_token=str(initial["access_token"]),
            account_id=str(initial["account_id"]),
            refresh_token=None,
            auth_file=Path(os.devnull),
        )
        # Serialize token-bearing reclaim/refresh operations across event loops.
        self._pool_operation_lock = threading.Lock()

    async def ensure_pool_credential(self) -> None:
        await asyncio.to_thread(self._ensure_pool_credential_sync)

    def _ensure_pool_credential_sync(self) -> None:
        with self._pool_operation_lock:
            response = self.bridge.request(
                "reclaim",
                credential_id=self.credential_id,
                model=self.model,
            )
            if not response.get("ok"):
                reset_at = response.get("reset_at")
                if isinstance(reset_at, (int, float)) and not isinstance(reset_at, bool):
                    retry_at = datetime.fromtimestamp(float(reset_at), timezone.utc)
                    if retry_at > datetime.now(timezone.utc):
                        raise ProviderRateLimitResetError(
                            retry_at=retry_at,
                            message=f"Hermes Codex pool entry is cooling down; retry at {retry_at.isoformat()}",
                        )
                raise HermesPoolBridgeError("The configured Hermes Codex pool entry is unavailable.")
            self._adopt(response)

    def _adopt(self, response: dict[str, Any]) -> None:
        if str(response.get("credential_id")) != self.credential_id:
            raise HermesPoolBridgeError("Hermes pool returned a different credential identity.")
        self.access_token = str(response["access_token"])
        self.account_id = str(response["account_id"])

    async def refresh_tokens(self, reason: str = "", *, force: bool = False) -> None:
        token_before_lock = self.access_token
        await asyncio.to_thread(self._refresh_tokens_sync, token_before_lock, force)

    def _refresh_tokens_sync(self, token_before_lock: str, force: bool) -> None:
        with self._pool_operation_lock:
            if force:
                if self.access_token != token_before_lock:
                    return
            elif not self._token_is_stale():
                return
            response = self.bridge.request(
                "refresh",
                credential_id=self.credential_id,
                model=self.model,
            )
            self._adopt(response)

    async def mark_quota_exhausted(self, reset_at: float, model: str) -> None:
        await asyncio.to_thread(
            self.bridge.request,
            "mark_quota",
            credential_id=self.credential_id,
            model=model,
            reset_at=float(reset_at),
        )
