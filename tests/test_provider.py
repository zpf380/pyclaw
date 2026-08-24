# -*- coding: utf-8 -*-
"""LiteLLM Provider 测试：文本 tool_call 解析、模型名前缀处理、错误兜底."""
import json
from types import SimpleNamespace

import pytest

from pyclaw.providers.litellm_provider import (
    LiteLLMProvider,
    _extract_balanced_object,
)


class TestExtractBalancedObject:
    def test_flat_object(self):
        assert _extract_balanced_object('{"a": 1}') == '{"a": 1}'

    def test_nested_object(self):
        text = '{"name": "x", "arguments": {"content": {"k": "v"}}}'
        assert _extract_balanced_object(text) == text

    def test_string_with_braces_inside(self):
        text = '{"name": "say", "arguments": {"text": "} not close"}}'
        assert _extract_balanced_object(text) == text

    def test_leading_text_before_object(self):
        assert _extract_balanced_object('prefix {"a": 1}') == '{"a": 1}'

    def test_no_object(self):
        assert _extract_balanced_object('no braces here') is None


def _fake_response(content, finish_reason="stop", tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


class TestModelPrefixing:
    @pytest.mark.asyncio
    async def test_openrouter_gemini_no_double_prefix(self, monkeypatch):
        """OpenRouter 渠道配 gemini 模型时不应叠加成 gemini/openrouter/..."""
        captured = {}
        async def fake_acompletion(**kwargs):
            captured["model"] = kwargs["model"]
            return _fake_response("hi")
        monkeypatch.setattr("pyclaw.providers.litellm_provider.acompletion", fake_acompletion)

        provider = LiteLLMProvider(api_key="sk-or-123", api_base="https://openrouter.ai/api/v1")
        await provider.chat(messages=[], model="gemini/gemini-2.0-flash")
        assert captured["model"] == "openrouter/gemini/gemini-2.0-flash"

    @pytest.mark.asyncio
    async def test_direct_gemini_prefix(self, monkeypatch):
        captured = {}
        async def fake_acompletion(**kwargs):
            captured["model"] = kwargs["model"]
            return _fake_response("hi")
        monkeypatch.setattr("pyclaw.providers.litellm_provider.acompletion", fake_acompletion)

        provider = LiteLLMProvider(api_key="AIza-something")
        await provider.chat(messages=[], model="gemini-2.0-flash")
        assert captured["model"] == "gemini/gemini-2.0-flash"

    @pytest.mark.asyncio
    async def test_openrouter_zhipu_no_double_prefix(self, monkeypatch):
        captured = {}
        async def fake_acompletion(**kwargs):
            captured["model"] = kwargs["model"]
            return _fake_response("hi")
        monkeypatch.setattr("pyclaw.providers.litellm_provider.acompletion", fake_acompletion)

        provider = LiteLLMProvider(api_key="sk-or-123", api_base="https://openrouter.ai/api/v1")
        await provider.chat(messages=[], model="glm-4.7-flash")
        assert captured["model"] == "openrouter/glm-4.7-flash"


class TestTextToolCallFallback:
    @pytest.mark.asyncio
    async def test_nested_arguments_parsed(self, monkeypatch):
        """arguments 内层是对象时也能完整解析（修复正则首个 } 截断）."""
        tool_call = '<tool_call>{"name": "write_file", "arguments": {"path": "a/b.txt", "content": {"nested": "{}"}}}</tool_call>'
        provider = LiteLLMProvider()
        content, calls = provider._extract_text_tool_calls(tool_call)
        assert len(calls) == 1
        assert calls[0].name == "write_file"
        assert calls[0].arguments["content"] == {"nested": "{}"}

    @pytest.mark.asyncio
    async def test_error_finish_reason(self, monkeypatch):
        """LLM 调用异常 → finish_reason=error，content 为错误串."""
        provider = LiteLLMProvider()
        resp = provider.chat  # noqa
        # 直接构造：provider.chat 内部已捕获异常
        # 通过 monkeypatch 让 acompletion 抛异常验证
        async def boom(**kwargs):
            raise RuntimeError("boom")
        monkeypatch.setattr("pyclaw.providers.litellm_provider.acompletion", boom)
        result = await provider.chat(messages=[], model="x")
        assert result.finish_reason == "error"
        assert "boom" in (result.content or "")


class TestProviderErrorHandling:
    @pytest.mark.asyncio
    async def test_no_tools_ok(self, monkeypatch):
        async def fake_acompletion(**kwargs):
            return _fake_response("hello")
        monkeypatch.setattr("pyclaw.providers.litellm_provider.acompletion", fake_acompletion)
        provider = LiteLLMProvider()
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "hello"
        assert result.finish_reason == "stop"
