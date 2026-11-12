"""Regression tests for narrow secret-scanner false positives."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

CHECKER_PATH = Path(__file__).resolve().parents[1] / ".devframework" / "secrets_check.py"
SPEC = importlib.util.spec_from_file_location("secrets_check_fixture", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class SecretCheckTests(unittest.TestCase):
    def test_unquoted_self_reference_is_not_a_literal_secret(self):
        name = "access_token"
        self.assertEqual(CHECKER.findings(f"{name}={name}\n"), [])

    def test_other_unquoted_value_remains_a_candidate(self):
        name = "access_token"
        self.assertEqual(len(CHECKER.findings(f"{name}=fixture_value\n")), 1)

    def test_exact_public_xai_marker_is_not_a_secret(self):
        name = "X-XAI-Token-Auth"
        value = "xai-grok-cli"
        self.assertEqual(CHECKER.findings(f'"{name}": "{value}"\n'), [])

    def test_other_xai_marker_value_remains_a_candidate(self):
        name = "X-XAI-Token-Auth"
        value = "not-the-public-marker"
        self.assertEqual(len(CHECKER.findings(f'"{name}": "{value}"\n')), 1)


if __name__ == "__main__":
    unittest.main()
