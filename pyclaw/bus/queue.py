"""Async message queue for decoupled channel-agent communication.
消息队列 - 消息队列实现"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from pyclaw.bus.events import InboundMessage, OutboundMessage, WebsocketMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.
    
    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """
    
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self.websocketbound: asyncio.Queue[WebsocketMessage] = asyncio.Queue()
        self._running = False
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)
    
    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)
     
    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()
   
    async def consume_websocket(self) -> WebsocketMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.websocketbound.get()
    
    async def publish_websocket(self, msg: WebsocketMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.websocketbound.put(msg)
    
    def stop(self) -> None:
        """Stop the dispatcher loop."""
        self._running = False
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    @property
    def websocketoutbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.websocketbound.qsize()
