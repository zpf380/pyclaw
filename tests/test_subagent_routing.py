# -*- coding: utf-8 -*-
"""子代理结果路由测试：Web UI（GatewayServer）来源的子代理结果必须回到发起请求的连接."""
import pytest

from pyclaw.agent.loop import AgentLoop
from pyclaw.bus.events import InboundMessage, WebsocketMessage, OutboundMessage
from pyclaw.bus.queue import MessageBus
from pyclaw.providers.base import LLMResponse


class FakeLLM:
    """返回纯文本、不触发工具调用的替身 provider."""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None, model=None, **kwargs):
        self.calls += 1
        return LLMResponse(content="已汇总子代理结果", finish_reason="stop")

    def get_default_model(self):
        return "fake-model"


@pytest.fixture()
def loop(tmp_path):
    return AgentLoop(
        bus=MessageBus(),
        provider=FakeLLM(),
        workspace=tmp_path,
        model="fake-model",
    )


@pytest.mark.asyncio
async def test_websocket_origin_returns_websocket_message(loop):
    """Web UI 来源的子代理 announce → WebsocketMessage，channel 为 client_id.

    修复前：返回 OutboundMessage，run() 走 publish_outbound 被网关丢弃，
    管理员在 Web UI 发起 spawn 后永远看不到结果。
    """
    msg = InboundMessage(
        channel="system",
        sender_id="client_abc",  # 子代理 announce 已携带 websocket client_id
        chat_id="GatewayServer:conv-123",
        content="[Subagent 'research' completed successfully]\nTask: 查资料\nResult: 找到答案\nSummarize.",
    )
    resp = await loop._process_message(msg)
    assert isinstance(resp, WebsocketMessage)
    assert resp.channel == "client_abc"  # 网关按连接 id 匹配推送
    assert resp.chat_id == "conv-123"
    assert "汇总" in resp.content


@pytest.mark.asyncio
async def test_im_origin_returns_outbound_message(loop):
    """非 Web UI 来源（如 Feishu）的子代理 announce → OutboundMessage."""
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="feishu:chat123",
        content="[Subagent 'x' completed successfully]\nTask: t\nResult: r\nSummarize.",
    )
    resp = await loop._process_message(msg)
    assert isinstance(resp, OutboundMessage)
    assert resp.channel == "feishu"
    assert resp.chat_id == "chat123"


@pytest.mark.asyncio
async def test_websocket_result_reaches_websocketbound_queue(loop):
    """WebSocketMessage 响应经 run() 路由到 websocketbound 队列（网关消费）."""
    msg = InboundMessage(
        channel="system",
        sender_id="client_xyz",
        chat_id="GatewayServer:conv-9",
        content="[Subagent 'x' completed successfully]\nTask: t\nResult: r\nSummarize.",
    )
    response = await loop._process_message(msg)
    assert isinstance(response, WebsocketMessage)

    # 模拟 run() 的路由逻辑：按响应类型 publish_websocket
    import asyncio
    await loop.bus.publish_websocket(response)
    got = await asyncio.wait_for(loop.bus.consume_websocket(), timeout=2)
    assert got.channel == "client_xyz"
