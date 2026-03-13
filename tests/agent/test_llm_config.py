import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/bseed/git/lucas/src/agent/main")

from llm import resolve_llm_config, validate_llm_config


class LLMConfigTests(unittest.TestCase):
    def test_claude_legacy_config_still_resolves(self):
        with patch.dict(
            os.environ,
            {
                "CLAUDE_MODEL": "sonnet",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.backend, "claude-code")
            self.assertEqual(config.provider, "anthropic")
            self.assertTrue(config.supports_resume)
            validate_llm_config(config)

    def test_groq_defaults_to_openai_compatible_endpoint(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "groq",
                "GROQ_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.backend, "openai-compatible")
            self.assertEqual(config.provider, "groq")
            self.assertEqual(config.base_url, "https://api.groq.com/openai/v1")
            self.assertEqual(config.model, "llama-3.3-70b-versatile")
            validate_llm_config(config)

    def test_kimi_defaults_to_official_endpoint_and_model(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "kimi",
                "KIMI_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.provider, "kimi")
            self.assertEqual(config.base_url, "https://api.moonshot.ai/v1")
            self.assertEqual(config.model, "kimi-k2.5")
            validate_llm_config(config)

    def test_gemini_defaults_to_official_openai_compatible_endpoint_and_model(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.provider, "gemini")
            self.assertEqual(config.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
            self.assertEqual(config.model, "gemini-2.5-flash")
            validate_llm_config(config)

    def test_gemini_shared_env_overrides_work(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "gemini",
                "LLM_API_KEY": "shared-key",
                "LLM_MODEL": "gemini-3-flash-preview",
                "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.api_key, "shared-key")
            self.assertEqual(config.model, "gemini-3-flash-preview")
            self.assertEqual(config.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
            validate_llm_config(config)

    def test_provider_specific_values_override_generic_values(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "gemini",
                "LLM_API_KEY": "generic-key",
                "LLM_MODEL": "llama-3.3-70b-versatile",
                "LLM_BASE_URL": "https://api.groq.com/openai/v1",
                "GEMINI_API_KEY": "gemini-key",
                "GEMINI_MODEL": "gemini-2.5-flash",
                "GEMINI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.provider, "gemini")
            self.assertEqual(config.api_key, "gemini-key")
            self.assertEqual(config.model, "gemini-2.5-flash")
            self.assertEqual(config.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
            validate_llm_config(config)


if __name__ == "__main__":
    unittest.main()
