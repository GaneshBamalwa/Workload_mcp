"""LLM provider abstraction layer."""
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog
from anthropic import Anthropic
from openai import OpenAI

from app.core.config import settings

logger = structlog.get_logger(__name__)


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Get text completion."""
        pass

    @abstractmethod
    async def structured_output(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get structured output matching schema."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        """Initialize OpenAI provider."""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.debug("OpenAI provider initialized", model=model)

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Get completion from OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("OpenAI completion failed", error=str(e))
            raise

    async def structured_output(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get structured output from OpenAI using JSON mode."""
        try:
            # Add JSON schema instruction
            system_message = messages[0] if messages else {}
            schema_instruction = f"\nReturn only valid JSON matching this schema: {schema}"

            messages_with_schema = messages.copy()
            if messages:
                messages_with_schema[0] = {
                    **messages[0],
                    "content": messages[0].get("content", "") + schema_instruction,
                }

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages_with_schema,
                response_format={"type": "json_object"},
                temperature=kwargs.get("temperature", 0.5),
                max_tokens=kwargs.get("max_tokens", 2000),
            )

            import json

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            logger.error("OpenAI structured output failed", error=str(e))
            raise


class OpenAICompatibleProvider(OpenAIProvider):
    """Provider for OpenAI-compatible APIs (Groq, Mistral, OpenRouter)."""

    def __init__(self, api_key: str, model: str, base_url: str):
        """Initialize OpenAI-compatible provider."""
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        logger.debug("OpenAI-compatible provider initialized", model=model, base_url=base_url)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        """Initialize Anthropic provider."""
        self.client = Anthropic(api_key=api_key)
        self.model = model
        logger.debug("Anthropic provider initialized", model=model)

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Get completion from Claude."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 1000),
                system=messages[0].get("content") if messages else "",
                messages=[m for m in messages[1:]] if len(messages) > 1 else [],
            )
            return response.content[0].text
        except Exception as e:
            logger.error("Anthropic completion failed", error=str(e))
            raise

    async def structured_output(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get structured output from Claude."""
        try:
            import json

            schema_instruction = f"\nReturn only valid JSON matching this schema: {json.dumps(schema)}"

            response = self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 2000),
                system=messages[0].get("content", "") + schema_instruction if messages else schema_instruction,
                messages=[m for m in messages[1:]] if len(messages) > 1 else [],
            )

            result = json.loads(response.content[0].text)
            return result

        except Exception as e:
            logger.error("Anthropic structured output failed", error=str(e))
            raise


class LLMFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create_provider(provider: str = "openai") -> LLMProvider:
        """Create LLM provider based on config."""
        if provider == "openai":
            return OpenAIProvider(
                settings.OPENAI_API_KEY,
                settings.OPENAI_MODEL,
            )
        elif provider == "anthropic":
            return AnthropicProvider(
                settings.ANTHROPIC_API_KEY,
                settings.ANTHROPIC_MODEL,
            )
        elif provider == "groq":
            return OpenAICompatibleProvider(
                settings.GROQ_API_KEY,
                settings.GROQ_MODEL,
                "https://api.groq.com/openai/v1",
            )
        elif provider == "mistral":
            return OpenAICompatibleProvider(
                settings.MISTRAL_API_KEY,
                settings.MISTRAL_MODEL,
                "https://api.mistral.ai/v1",
            )
        elif provider == "openrouter":
            return OpenAICompatibleProvider(
                settings.OPENROUTER_API_KEY,
                settings.OPENROUTER_MODEL,
                "https://openrouter.ai/api/v1",
            )
        elif provider == "local":
            logger.warning("Local provider requested, using OpenAI-compatible fallback with OPENROUTER settings")
            return OpenAICompatibleProvider(
                settings.OPENROUTER_API_KEY,
                settings.OPENROUTER_MODEL,
                "https://openrouter.ai/api/v1",
            )
        else:
            logger.warning("Unknown LLM provider, defaulting to OpenAI", provider=provider)
            return OpenAIProvider(
                settings.OPENAI_API_KEY,
                settings.OPENAI_MODEL,
            )


# Global LLM provider instance
_llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Get global LLM provider."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMFactory.create_provider(settings.LLM_PROVIDER)
    return _llm_provider


async def call_llm(prompt: str, system: str = "", **kwargs) -> str:
    """Convenience function to call LLM."""
    provider = get_llm_provider()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return await provider.complete(messages, **kwargs)


async def call_llm_structured(
    prompt: str,
    schema: dict[str, Any],
    system: str = "",
    **kwargs,
) -> dict[str, Any]:
    """Convenience function to call LLM with structured output."""
    provider = get_llm_provider()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return await provider.structured_output(messages, schema, **kwargs)
