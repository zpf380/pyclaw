"""OpenIM channel implementation using openim_sdk_python SDK with WebSocket long connection.
OpenIM集成 - OpenIM消息支持"""
from pyclaw.bus.events import OutboundMessage
from pyclaw.bus.queue import MessageBus
from pyclaw.channels.base import BaseChannel
from pyclaw.config.schema import OpenIMConfig

from pyclaw.channels.sdkws import sdkws_pb2
import asyncio
import websockets
import json
import requests
import uuid
import zlib
import time
import base64
import threading
from collections import OrderedDict
from typing import Any
from loguru import logger
import websocket
import struct
import re

class OpenIMChannel(BaseChannel):
    name = "openim"

    def __init__(self, config: OpenIMConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: OpenIMConfig = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
        
        self.PLATFORM_ID = 5         # 固定
        self.token = self.get_user_token(self.config.user_id)
        self.recv_id = '1830170283'
        self.send_id = '1698163922'

    
    async def start(self) -> None:
        """Start the OpenIM bot with WebSocket long connection."""
        logger.info("OpenIM bot started with WebSocket long connection")
        logger.info("No public IP required - using WebSocket to receive events")
        await self.handler_message()
        logger.error("OpenIM channel terminal!")

    async def stop(self) -> None:
        """Stop the OpenIM bot."""
    
    async def send(self, msg: OutboundMessage) -> None:
        def clean_bytes(data: bytes) -> bytes:
            """
            清理二进制 bytes 数据
            保留：中文 + 大小写字母 + 数字 + 常用符号（。，！？@#$%^&*()_+-=等）
            剔除：所有不可见控制符、乱码、特殊坏字符
            """
            result = []
            
            for b in data:
                # 保留规则：
                # 1. 可见 ASCII 字符 (空格 ~ ~)
                # 2. 中文等多字节字符 (>= 0x80)
                if (0x20 <= b <= 0x7E) or (b >= 0x80):
                    result.append(b)
            
            return bytes(result)
        if msg == None:
            print("msg is None")
        else:
            msg_text = msg.content.replace('"',"'");
            content = str("{\"content\":\""+msg_text+"\"}").encode('utf-8')
            result = clean_bytes(content)
            sdkws_msg = sdkws_pb2.MsgData()
            sdkws_msg.sendID = self.send_id
            sdkws_msg.recvID = self.recv_id
            sdkws_msg.groupID = ""
            sdkws_msg.clientMsgID = f"{self.send_id}_{int(time.time() * 1000)}"
            sdkws_msg.serverMsgID = f"{self.send_id}_{int(time.time() * 1000)}"
            sdkws_msg.senderPlatformID = 5
            sdkws_msg.senderNickname = "muzileester"
            sdkws_msg.sessionType = 1
            sdkws_msg.contentType = 101  # 文本消息
            sdkws_msg.content = result
            sdkws_msg.sendTime = int(time.time() * 1000)
            sdkws_msg.createTime = int(time.time() * 1000)
            sdkws_msg.status = 2
            

            msg_bytes = sdkws_msg.SerializeToString()
            data_b64 = base64.b64encode(msg_bytes).decode('ascii')
            request = {
                "reqIdentifier": 1003,
                "sendID": self.send_id,
                "operationID": f"op_{uuid.uuid4().hex[:12]}",
                "msgIncr": str(int(time.time() * 1000)),
                "data": data_b64
            }
            await self._ws_client.send(json.dumps(request).encode('utf-8'))

    def get_admin_token(self) -> str:
        url = "https://web.yunzainfo.com/api/auth/get_admin_token"
        data = {
            "secret": "openIM123",  # 默认密钥
            "userID": "imAdmin"
        }
        headers = {
            'Content-Type': 'application/json',
            'operationID': '123456'
        }
        resp = requests.post(url, json=data, headers=headers)
        token = resp.json()["data"]["token"]
        # print("imAdmin 的 token：", token)
        return token

    def get_user_token(self, user_id):
        url = "https://web.yunzainfo.com/api/auth/get_user_token"
        data = {
            "platformID": self.PLATFORM_ID,  # 默认密钥
            "userID": user_id
        }
        headers = {
            'Content-Type': 'application/json',
            'operationID': '123456',
            'token': self.get_admin_token()
        }
        resp = requests.post(url, json=data, headers=headers)
        token = resp.json()["data"]["token"]
        # print("你的 token：", token)
        return token

    # --------------------------
    # 解压 GZIP 数据
    # --------------------------
    def decompress_gzip(self, data):
        try:
            return zlib.decompress(data, 16 + zlib.MAX_WBITS).decode("utf-8")
        except Exception:
            return data.decode("utf-8", errors="replace")
    

    # 接收发送消息
    async def handler_message(self):
        full_ws_url = f"wss://web.yunzainfo.com/msg_gateway?isBackground=false&sdkType=js&compression=None&platformID={self.PLATFORM_ID}&sendID={self.config.user_id}&token={self.token}"
        try:
            async with websockets.connect(
                full_ws_url,
                ping_interval=20,   # 心跳
                ping_timeout=40,
                close_timeout=10
            ) as ws:
                print("✅ WebSocket 已连接")
                self._ws_client = ws
                # --------------------------
                # 核心：必须一直接收！
                # --------------------------
                async def receive_loop():
                    while True:
                        try:
                            raw_msg = await ws.recv()
                            # 自动判断是否二进制并解压
                            if isinstance(raw_msg, bytes):
                                msg_text = self.decompress_gzip(raw_msg)
                            else:
                                # msg_text = raw_msg
                                continue

                            # print("\n📩 收到消息：")
                            wrapper = json.loads(msg_text)
                            # 提取消息头字段
                            req_id = wrapper.get('reqIdentifier')
                            op_id = wrapper.get('operationID')
                            err_code = wrapper.get('errCode', 0)
                            data_b64 = wrapper.get('data', '')
                            if req_id == 2001:                               
                                if data_b64:
                                    push_msg = sdkws_pb2.PushMessages()
                                    protobuf_bytes = base64.b64decode(data_b64)
                                    push_msg.ParseFromString(protobuf_bytes)
                                    # print(f"收到 {push_msg} 条消息")
                                    msg = None
                                    for key, value in push_msg.msgs.items():
                                        pull_msgs = sdkws_pb2.PullMsgs()
                                        pull_msgs.ParseFromString(value.SerializeToString())
                                        for i, msg in enumerate(pull_msgs.Msgs):
                                            pass
                                        
                                    # Forward to message bus
                                    if msg != None and msg.sendID != self.send_id and msg.content != "" and msg.contentType == 101:
                                        # print(f"收到 {push_msg} 消息")
                                        str_data = msg.content.decode("utf-8")  # utf-8 是最通用编码
                                        json_obj = json.loads(str_data)
                                        print(self.send_id,"开始向",self.recv_id,"发送回复消息！")
                                        # reply_to = chat_id if chat_type == "group" else sender_id
                                        await self._handle_message(
                                            sender_id=self.send_id,
                                            chat_id=self.send_id,
                                            content=json_obj['content'],
                                            metadata={
                                                "message_id": "123",
                                                "chat_type": "cli",
                                                "msg_type": "text",
                                            }
                                        )
                        except websockets.exceptions.ConnectionClosed:
                            print("🔌 连接已关闭")
                            break
                        except Exception as e:
                            print("接收异常:", e)
                            break

                # 并行运行：收 + 发
                await asyncio.gather(
                    receive_loop()
                )

        except websockets.exceptions.ConnectionClosedError:
            print("\n❌ 连接被服务器断开 → 99% 是 Token 错误 或 userID 不存在")
        except Exception as e:
            print("\n❌ 错误：", e)
 