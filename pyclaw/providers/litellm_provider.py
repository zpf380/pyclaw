"""LiteLLM provider implementation for multi-provider support.
LiteLLM集成 - 支持多种AI模型(GPT/Claude等)，生成对话响应"""

import json
import os
import re
from typing import Any

import litellm
from litellm import acompletion

from pyclaw.providers.base import LLMProvider, LLMResponse, ToolCallRequest


def _extract_balanced_object(text: str) -> str | None:
    """在文本中定位最外层平衡的 JSON 对象 {...} 并返回其原文.

    逐字符扫描并维护大括号深度，同时正确跳过字符串内的括号，
    因此支持 arguments 内层是对象/数组（嵌套 JSON）的情况。
    找不到平衡对象返回 None。
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.
    
    Supports OpenRouter, Anthropic, OpenAI, Gemini, and many other providers through
    a unified interface.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        enable_text_tool_call_fallback: bool = True,
        timeout: int = 120,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.enable_text_tool_call_fallback = enable_text_tool_call_fallback
        self.timeout = timeout

        # Detect OpenRouter by api_key prefix or explicit api_base
        self.is_openrouter = (
            (api_key and api_key.startswith("sk-or-")) or
            (api_base and "openrouter" in api_base)
        )

        # Track if using custom endpoint (vLLM, etc.)
        # 仅当 api_base 显式指向 vLLM 时才按 vLLM 路由；
        # 不能仅凭「有 api_base」判定——DeepSeek/Gemini 等官方 API 也带 api_base
        self.is_vllm = bool(api_base) and "vllm" in api_base.lower()
        
        # Configure LiteLLM based on provider
        if api_key:
            if self.is_openrouter:
                # OpenRouter mode - set key
                os.environ["OPENROUTER_API_KEY"] = api_key
            elif self.is_vllm:
                # vLLM/custom endpoint - uses OpenAI-compatible API
                os.environ["OPENAI_API_KEY"] = api_key
            elif "deepseek" in default_model:
                os.environ.setdefault("DEEPSEEK_API_KEY", api_key)
            elif "anthropic" in default_model:
                os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
            elif "openai" in default_model or "gpt" in default_model:
                os.environ.setdefault("OPENAI_API_KEY", api_key)
            elif "gemini" in default_model.lower():
                os.environ.setdefault("GEMINI_API_KEY", api_key)
            elif "zhipu" in default_model or "glm" in default_model or "zai" in default_model:
                os.environ.setdefault("ZHIPUAI_API_KEY", api_key)
            elif "groq" in default_model:
                os.environ.setdefault("GROQ_API_KEY", api_key)
        
        if api_base:
            litellm.api_base = api_base
        
        # Disable LiteLLM logging noise
        litellm.suppress_debug_info = True
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        model = model or self.default_model
        
        # For OpenRouter, prefix model name if not already prefixed
        if self.is_openrouter and not model.startswith("openrouter/"):
            model = f"openrouter/{model}"
        
        # For Zhipu/Z.ai, ensure prefix is present
        # Handle cases like "glm-4.7-flash" -> "zai/glm-4.7-flash"
        if ("glm" in model.lower() or "zhipu" in model.lower()) and not (
            model.startswith("zhipu/") or 
            model.startswith("zai/") or 
            model.startswith("openrouter/")
        ):
            model = f"zai/{model}"
        
        # For vLLM, use hosted_vllm/ prefix per LiteLLM docs
        # Convert openai/ prefix to hosted_vllm/ if user specified it
        if self.is_vllm:
            model = f"hosted_vllm/{model}"
        
        # For Gemini, ensure gemini/ prefix if not already present
        # 排除 openrouter/hosted_vllm 前缀，避免 OpenRouter 配 gemini 渠道时
        # 二次叠加成 gemini/openrouter/gemini-... 的非法模型名
        if "gemini" in model.lower() and not (
            model.startswith("gemini/") or
            model.startswith("openrouter/") or
            model.startswith("hosted_vllm/")
        ):
            model = f"gemini/{model}"
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # 网络/读超时兜底，避免 LLM API 挂起时 AgentLoop 永久等待
            "timeout": self.timeout,
        }
        
        # Pass api_base directly for custom endpoints (vLLM, etc.)
        if self.api_base:
            kwargs["api_base"] = self.api_base
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            # Return error as content for graceful handling
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        choice = response.choices[0]
        message = choice.message
        content = message.content
        
        tool_calls: list[ToolCallRequest] = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=self._coerce_tool_arguments(tc.function.arguments),
                ))

        if self.enable_text_tool_call_fallback and not tool_calls:
            content, tool_calls = self._extract_text_tool_calls(content)
        
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    def _coerce_tool_arguments(self, arguments: Any) -> dict[str, Any]:
        """Normalize tool-call arguments to a dict payload."""
        if isinstance(arguments, dict):
            return arguments

        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return {"raw": arguments}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}

        return {"value": arguments}

    def _extract_text_tool_calls(
        self,
        content: Any,
    ) -> tuple[str | None, list[ToolCallRequest]]:
        """
        Parse tool calls from text outputs like:
        <tool_call>{"name": "...", "arguments": {...}}</tool_call>
        """
        if not isinstance(content, str) or "<tool_call>" not in content:
            return content, []

        # 用非贪婪块匹配取每个 tool_call 的完整原文，再做括号配对扫描
        # 提取最外层 {...}：arguments 内层是对象（嵌套 JSON）时旧的正则会在
        # 第一个 '}' 处截断，导致 json.loads 失败、工具调用被静默丢弃
        pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
        parsed_calls: list[ToolCallRequest] = []

        for index, match in enumerate(pattern.finditer(content), start=1):
            payload_text = _extract_balanced_object(match.group(1))
            if payload_text is None:
                continue
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue

            if not isinstance(payload, dict):
                continue

            name = payload.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            call_id = payload.get("id")
            if not isinstance(call_id, str) or not call_id.strip():
                call_id = f"text_tool_call_{index}"

            parsed_calls.append(
                ToolCallRequest(
                    id=call_id,
                    name=name.strip(),
                    arguments=self._coerce_tool_arguments(payload.get("arguments", {})),
                )
            )

        if not parsed_calls:
            return content, []

        cleaned = pattern.sub("", content).strip()
        return (cleaned or None), parsed_calls
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
