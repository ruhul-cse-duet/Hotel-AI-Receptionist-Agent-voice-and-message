"""
LLM Provider Abstraction Layer
Seamlessly switch between OpenAI, Gemini, and LM Studio (local)
All providers implement the same interface for drop-in replacement.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, AsyncIterator, Optional, Any
from config import settings, LLMProvider

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Base Provider Interface
# ─────────────────────────────────────────────

class BaseLLMProvider(ABC):

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> Dict:
        """Returns: { content: str, tool_calls: [...] | None, usage: {...} }"""
        pass

    @abstractmethod
    async def stream_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        """Yields text chunks for streaming TTS"""
        pass


# ─────────────────────────────────────────────
# OpenAI Provider
# ─────────────────────────────────────────────

class OpenAIProvider(BaseLLMProvider):

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        logger.info(f"🤖 LLM: OpenAI ({self.model})")

    async def chat_completion(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> Dict:
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    "type": "function",
                }
                for tc in msg.tool_calls
            ]

        return {
            "content": msg.content or "",
            "tool_calls": tool_calls,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }

    async def stream_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.5,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


# ─────────────────────────────────────────────
# Gemini Provider
# ─────────────────────────────────────────────

class GeminiProvider(BaseLLMProvider):

    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.genai = genai
        self.model_name = settings.GEMINI_MODEL
        logger.info(f"🤖 LLM: Google Gemini ({self.model_name})")

    def _convert_messages_to_gemini(self, messages: List[Dict]):
        """Convert OpenAI-style messages to Gemini format"""
        system_prompt = ""
        history = []
        last_user_msg = ""

        for msg in messages:
            role = msg["role"]
            content = msg["content"] or ""

            if role == "system":
                system_prompt = content
            elif role == "user":
                last_user_msg = content
                if history:
                    history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})

        return system_prompt, history, last_user_msg

    async def chat_completion(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> Dict:
        import asyncio

        system_prompt, history, last_msg = self._convert_messages_to_gemini(messages)

        model_kwargs = {
            "model_name": self.model_name,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        }
        if system_prompt:
            model_kwargs["system_instruction"] = system_prompt

        # Gemini function calling (tools)
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_tools_to_gemini(tools)
            model_kwargs["tools"] = gemini_tools

        model = self.genai.GenerativeModel(**model_kwargs)
        chat = model.start_chat(history=history)

        response = await asyncio.to_thread(chat.send_message, last_msg)

        # Extract tool calls if any
        tool_calls = None
        content = ""

        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                import json
                tool_calls = [{
                    "id": f"gemini_{fc.name}",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args)),
                    },
                    "type": "function",
                }]
            elif hasattr(part, "text"):
                content += part.text

        return {"content": content, "tool_calls": tool_calls, "usage": {}}

    def _convert_tools_to_gemini(self, tools: List[Dict]) -> List:
        """Convert OpenAI tool format to Gemini format"""
        from google.generativeai.types import FunctionDeclaration, Tool

        declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                declarations.append(
                    FunctionDeclaration(
                        name=fn["name"],
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}),
                    )
                )
        return [Tool(function_declarations=declarations)]

    async def stream_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        import asyncio

        system_prompt, history, last_msg = self._convert_messages_to_gemini(messages)
        model = self.genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
            system_instruction=system_prompt if system_prompt else None,
        )
        chat = model.start_chat(history=history)

        response = await asyncio.to_thread(
            chat.send_message, last_msg, stream=True
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text


# ─────────────────────────────────────────────
# LM Studio Provider (Local Development)
# OpenAI-compatible API — works offline
# ─────────────────────────────────────────────

class LMStudioProvider(BaseLLMProvider):

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            base_url=settings.LM_STUDIO_BASE_URL,
            api_key=settings.LM_STUDIO_API_KEY,
        )
        self.model = settings.LM_STUDIO_MODEL
        logger.info(f"🤖 LLM: LM Studio local ({settings.LM_STUDIO_BASE_URL})")

    async def chat_completion(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> Dict:
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # LM Studio supports tool calling with compatible models (Llama 3.1+, Mistral)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        try:
            response = await self.client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            tool_calls = None
            if msg.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        "type": "function",
                    }
                    for tc in msg.tool_calls
                ]

            return {
                "content": msg.content or "",
                "tool_calls": tool_calls,
                "usage": {},
            }
        except Exception as e:
            logger.error(f"LM Studio error: {e}")
            raise

    async def stream_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ─────────────────────────────────────────────
# Provider Factory
# ─────────────────────────────────────────────

_provider_instance: Optional[BaseLLMProvider] = None


def get_llm_provider() -> BaseLLMProvider:
    global _provider_instance
    if _provider_instance is None:
        provider_map = {
            LLMProvider.OPENAI: OpenAIProvider,
            LLMProvider.GEMINI: GeminiProvider,
            LLMProvider.LM_STUDIO: LMStudioProvider,
        }
        cls = provider_map.get(settings.LLM_PROVIDER)
        if not cls:
            raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
        _provider_instance = cls()
    return _provider_instance
