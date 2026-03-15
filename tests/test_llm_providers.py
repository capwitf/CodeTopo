from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from llm_providers import get_provider_catalog, resolve_llm_config


class LLMProvidersTests(unittest.TestCase):
    def test_resolves_deepseek_defaults(self) -> None:
        config = resolve_llm_config()

        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.model, "deepseek-chat")

    def test_requires_base_url_for_openai_compatible(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a base URL"):
            resolve_llm_config(provider="openai_compatible", model="custom-model")

    def test_resolves_anthropic_defaults(self) -> None:
        config = resolve_llm_config(provider="anthropic")

        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.base_url, "https://api.anthropic.com/v1/")
        self.assertEqual(config.model, "claude-sonnet-4-20250514")

    def test_provider_catalog_contains_frontend_metadata(self) -> None:
        providers = get_provider_catalog()
        keys = {item["key"] for item in providers}

        self.assertTrue({"deepseek", "openai", "kimi", "anthropic", "glm", "minimax", "openai_compatible"} <= keys)


if __name__ == "__main__":
    unittest.main()
