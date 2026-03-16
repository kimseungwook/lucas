import os
import sys
import importlib.util
from importlib.machinery import ModuleSpec
from pathlib import Path
import unittest
from types import ModuleType
from unittest.mock import patch

aiohttp_stub = ModuleType("aiohttp")
aiohttp_stub.__spec__ = ModuleSpec("aiohttp", loader=None)
setattr(aiohttp_stub, "ClientTimeout", object)
setattr(aiohttp_stub, "ClientSession", object)
sys.modules.setdefault("aiohttp", aiohttp_stub)

llm_spec = importlib.util.spec_from_file_location(
    "test_llm_module",
    "/Users/bseed/git/lucas/src/agent/main/llm.py",
)
assert llm_spec and llm_spec.loader
llm_module = importlib.util.module_from_spec(llm_spec)
sys.modules[llm_spec.name] = llm_module
llm_spec.loader.exec_module(llm_module)

resolve_llm_config = llm_module.resolve_llm_config
validate_llm_config = llm_module.validate_llm_config


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

    def test_openrouter_defaults_to_official_endpoint_and_model(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "openrouter",
                "OPENROUTER_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.backend, "openai-compatible")
            self.assertEqual(config.provider, "openrouter")
            self.assertEqual(config.api_key, "test-key")
            self.assertEqual(config.model, "stepfun/step-3.5-flash:free")
            self.assertEqual(config.base_url, "https://openrouter.ai/api/v1")
            validate_llm_config(config)

    def test_openrouter_provider_specific_values_override_generic_values(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "openrouter",
                "LLM_API_KEY": "generic-key",
                "LLM_MODEL": "generic-model",
                "LLM_BASE_URL": "https://generic.example/v1",
                "OPENROUTER_API_KEY": "openrouter-key",
                "OPENROUTER_MODEL": "openrouter/model",
                "OPENROUTER_BASE_URL": "https://openrouter.example/v1/",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.provider, "openrouter")
            self.assertEqual(config.api_key, "openrouter-key")
            self.assertEqual(config.model, "openrouter/model")
            self.assertEqual(config.base_url, "https://openrouter.example/v1")
            validate_llm_config(config)

    def test_openrouter_legacy_api_key_alias_is_honored(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "openai-compatible",
                "LLM_PROVIDER": "openrouter",
                "OPENROUTE_API_KEY": "legacy-key",
            },
            clear=True,
        ):
            config = resolve_llm_config()
            self.assertEqual(config.api_key, "legacy-key")
            self.assertEqual(config.model, "stepfun/step-3.5-flash:free")
            self.assertEqual(config.base_url, "https://openrouter.ai/api/v1")
            validate_llm_config(config)

    def test_openrouter_env_templates_include_canonical_reference_vars(self):
        for relative_path in ("k8s/dev.env.template", "k8s/prod.env.template"):
            text = Path(f"/Users/bseed/git/lucas/{relative_path}").read_text()
            self.assertIn("OPENROUTER_API_KEY", text, relative_path)
            self.assertIn("OPENROUTER_MODEL", text, relative_path)
            self.assertIn("OPENROUTER_BASE_URL", text, relative_path)

    def test_install_script_includes_openrouter_defaults_and_guardrail(self):
        text = Path("/Users/bseed/git/lucas/scripts/install.sh").read_text()
        self.assertIn("openrouter", text)
        self.assertIn("stepfun/step-3.5-flash:free", text)
        self.assertIn("https://openrouter.ai/api/v1", text)
        self.assertIn("openrouter requires openai-compatible backend", text)


if __name__ == "__main__":
    unittest.main()
