from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

if importlib.util.find_spec("aiohttp") is not None:
    aiohttp = importlib.import_module("aiohttp")
else:
    aiohttp = None

logger = logging.getLogger(__name__)

load_dotenv(".env.providers.local", override=False)
load_dotenv("k8s/dev.env.local", override=False)
load_dotenv(override=False)

LEGACY_MODEL_MAP = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

CLAUDE_COST_PER_MILLION = {
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
}

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_KIMI_MODEL = "kimi-k2.5"
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_OPENROUTER_MODEL = "stepfun/step-3.5-flash:free"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class LLMConfig:
    backend: str
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    auth_mode: str
    supports_resume: bool


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    costs = CLAUDE_COST_PER_MILLION.get(
        model,
        CLAUDE_COST_PER_MILLION[LEGACY_MODEL_MAP["sonnet"]],
    )
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    return input_cost + output_cost


def resolve_llm_config() -> LLMConfig:
    backend = os.environ.get("LLM_BACKEND", "").strip().lower()
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    model = os.environ.get("LLM_MODEL", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    auth_mode = os.environ.get("AUTH_MODE", "api-key").strip().lower()

    if not backend:
        if provider and provider != "anthropic":
            backend = "openai-compatible"
        else:
            backend = "claude-code"

    if backend == "claude-code":
        model = model or LEGACY_MODEL_MAP.get(
            os.environ.get("CLAUDE_MODEL", "sonnet").lower(),
            LEGACY_MODEL_MAP["sonnet"],
        )
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        return LLMConfig(
            backend="claude-code",
            provider="anthropic",
            model=model,
            api_key=api_key,
            base_url=None,
            auth_mode=auth_mode,
            supports_resume=True,
        )

    provider = provider or os.environ.get("DEFAULT_LLM_PROVIDER", "groq").strip().lower() or "groq"

    provider_api_key = None
    provider_model = model
    provider_base_url = base_url

    if provider == "groq":
        provider_api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY")
        provider_model = os.environ.get("GROQ_MODEL") or provider_model or DEFAULT_GROQ_MODEL
        provider_base_url = os.environ.get("GROQ_BASE_URL") or provider_base_url or DEFAULT_GROQ_BASE_URL
    elif provider == "kimi":
        provider_api_key = os.environ.get("KIMI_API_KEY") or os.environ.get("LLM_API_KEY")
        provider_model = os.environ.get("KIMI_MODEL") or provider_model or DEFAULT_KIMI_MODEL
        provider_base_url = os.environ.get("KIMI_BASE_URL") or provider_base_url or DEFAULT_KIMI_BASE_URL
    elif provider == "gemini":
        provider_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        provider_model = os.environ.get("GEMINI_MODEL") or provider_model or DEFAULT_GEMINI_MODEL
        provider_base_url = os.environ.get("GEMINI_BASE_URL") or provider_base_url or DEFAULT_GEMINI_BASE_URL
    elif provider == "openrouter":
        provider_api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENROUTE_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        provider_model = os.environ.get("OPENROUTER_MODEL") or provider_model or DEFAULT_OPENROUTER_MODEL
        provider_base_url = os.environ.get("OPENROUTER_BASE_URL") or provider_base_url or DEFAULT_OPENROUTER_BASE_URL
    else:
        provider_api_key = os.environ.get("LLM_API_KEY")

    return LLMConfig(
        backend="openai-compatible",
        provider=provider,
        model=provider_model,
        api_key=provider_api_key,
        base_url=provider_base_url.rstrip("/") if provider_base_url else None,
        auth_mode=auth_mode,
        supports_resume=False,
    )


def validate_llm_config(config: LLMConfig) -> None:
    if config.backend == "claude-code":
        if config.auth_mode == "credentials":
            if os.path.exists(os.path.expanduser("~/.claude/.credentials.json")) or os.path.exists("/secrets/credentials.json"):
                return
            raise ValueError("Claude credentials mode requires credentials.json")
        if not config.api_key:
            raise ValueError("Claude backend requires ANTHROPIC_API_KEY or LLM_API_KEY")
        return

    if not config.api_key:
        raise ValueError(f"{config.provider} backend requires LLM_API_KEY or provider-specific API key")
    if not config.model:
        raise ValueError(f"{config.provider} backend requires LLM_MODEL or provider-specific model env")
    if not config.base_url:
        raise ValueError(f"{config.provider} backend requires LLM_BASE_URL or provider-specific base URL env")


class AgentBackend:
    async def run(
        self,
        prompt: str,
        system_prompt: str,
        session_id: str | None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class ClaudeCodeBackend(AgentBackend):
    def __init__(self, config: LLMConfig):
        self.config = config

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        session_id: str | None,
        context: dict[str, Any] | None = None,
        _retry: bool = False,
    ) -> dict[str, Any]:
        cmd = [
            "claude",
            "--model",
            self.config.model,
            "--dangerously-skip-permissions",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--append-system-prompt",
            system_prompt,
            "--allowedTools",
            "Bash(kubectl:*),Bash(sqlite3:*),Read,Grep,Glob,Edit,WebFetch",
        ]

        if session_id:
            cmd.extend(["--resume", session_id])

        env = os.environ.copy()
        env["SLACK_THREAD_TS"] = (context or {}).get("thread_ts", "") or ""
        env["SLACK_CHANNEL"] = (context or {}).get("channel", "") or ""

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await process.communicate()

        stderr_text = stderr.decode() if stderr else ""
        if stderr_text:
            logger.warning("Claude stderr: %s", stderr_text)

        if session_id and "No conversation found with session ID" in stderr_text and not _retry:
            logger.info("Session %s is stale, retrying without session", session_id)
            return await self.run(
                prompt=prompt,
                system_prompt=system_prompt,
                session_id=None,
                context=context,
                _retry=True,
            )

        output = stdout.decode().strip()
        lines = output.split("\n")
        result_text = ""
        new_session_id = session_id
        token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "model": self.config.model,
            "cost": 0.0,
        }

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                result_text = line
                continue

            if data.get("type") == "result":
                result_text = data.get("result", "")
                if "total_cost_usd" in data:
                    token_usage["cost"] = data.get("total_cost_usd", 0.0)
                if data.get("usage"):
                    usage = data["usage"]
                    token_usage["input_tokens"] = (
                        usage.get("input_tokens", 0)
                        + usage.get("cache_creation_input_tokens", 0)
                        + usage.get("cache_read_input_tokens", 0)
                    )
                    token_usage["output_tokens"] = usage.get("output_tokens", 0)
                if data.get("modelUsage"):
                    for model_id, model_usage in data["modelUsage"].items():
                        token_usage["model"] = model_id
                        if not token_usage["input_tokens"]:
                            token_usage["input_tokens"] = (
                                model_usage.get("inputTokens", 0)
                                + model_usage.get("cacheReadInputTokens", 0)
                                + model_usage.get("cacheCreationInputTokens", 0)
                            )
                        if not token_usage["output_tokens"]:
                            token_usage["output_tokens"] = model_usage.get("outputTokens", 0)
            if data.get("session_id"):
                new_session_id = data["session_id"]

        if not result_text:
            result_text = output or "No response from agent"

        return {
            "text": result_text,
            "session_id": new_session_id,
            "input_tokens": token_usage["input_tokens"],
            "output_tokens": token_usage["output_tokens"],
            "model": token_usage["model"],
            "cost": token_usage["cost"],
            "supports_resume": True,
        }


class OpenAICompatibleBackend(AgentBackend):
    def __init__(self, config: LLMConfig):
        self.config = config

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        session_id: str | None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del session_id
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for openai-compatible backends")
        context = context or {}
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(context.get("history") or [])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
        }

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.base_url}/chat/completions"

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"{self.config.provider} API error {response.status}: {body[:500]}")
                data = json.loads(body)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )

        usage = data.get("usage") or {}
        return {
            "text": content or body,
            "session_id": None,
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "model": data.get("model", self.config.model),
            "cost": 0.0,
            "supports_resume": False,
        }


def create_backend(config: LLMConfig) -> AgentBackend:
    if config.backend == "claude-code":
        return ClaudeCodeBackend(config)
    return OpenAICompatibleBackend(config)
