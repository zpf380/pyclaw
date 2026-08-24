import asyncio
import websockets
import json
import requests
import uuid
import zlib
import time
import base64

from datetime import datetime

def get_admin_token() -> str:
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
    token = resp.json()["data"][
        "token"]
    print("imAdmin 的 token：", token)
    return token

def get_user_token(user_id):
    url = "https://web.yunzainfo.com/api/auth/get_user_token"
    data = {
        "platformID": 5,  # 默认密钥
        "userID": user_id
    }
    headers = {
        'Content-Type': 'application/json',
        'operationID': '123456',
        'token': get_admin_token()
    }
    resp = requests.post(url, json=data, headers=headers)
    token = resp.json()["data"][
        "token"]
    print("你的 token：", token)
    return token
# --------------------------
# 解压 GZIP 数据（内置）
# --------------------------
def decompress_gzip(data):
    try:
        return zlib.decompress(data, 16 + zlib.MAX_WBITS).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")
        

# --------------------------
# 配置（改成你自己的）
# --------------------------
USER_ID = "1698163922"       # 必须真实存在
RECV_ID = "1830170283"       # 接收方
PLATFORM_ID = 5         # 固定
token = get_user_token(USER_ID)

from sdkws import sdkws_pb2

# 稳定发送消息（无断开报错）
async def send_msg_stable():
    full_ws_url = f"wss://web.yunzainfo.com/msg_gateway?isBackground=false&sdkType=js&compression=None&platformID=5&sendID={USER_ID}&token={token}"
    # full_ws_url = f"wss://web.yunzainfo.com/msg_gateway?platformID=5&sendID={USER_ID}&token={token}"
    
    try:
        async with websockets.connect(
            full_ws_url,
            ping_interval=20,   # 心跳（关键）
            ping_timeout=40,
            close_timeout=10
        ) as ws:
            print("✅ WebSocket 已连接")

            # --------------------------
            # 核心修复：必须一直接收！
            # --------------------------
            async def receive_loop():
                while True:
                    try:
                        raw_msg = await ws.recv()
                        # 自动判断是否二进制并解压
                        if isinstance(raw_msg, bytes):
                            msg_text = decompress_gzip(raw_msg)
                            print("------------------------------------------------------------")
                        else:
                            msg_text = raw_msg

                        print("\n📩 收到消息：")
                        wrapper = json.loads(msg_text)
                        # 提取消息头字段
                        req_id = wrapper.get('reqIdentifier')
                        op_id = wrapper.get('operationID')
                        err_code = wrapper.get('errCode', 0)
                        data_b64 = wrapper.get('data', '')
                        print(f"[{op_id}] ReqIdentifier={req_id}, ErrCode={err_code}")
                        print("------------------------------------------------------------")
                        if data_b64:
                            push_msg = sdkws_pb2.PushMessages()
                            protobuf_bytes = base64.b64decode(data_b64)
                            push_msg.ParseFromString(protobuf_bytes)
                            print(f"收到 {push_msg.msgs} 条消息")
                            
                        await send()
                    except websockets.exceptions.ConnectionClosed:
                        print("🔌 连接已关闭")
                        break
                    except Exception as e:
                        print("接收异常:", e)
                        break

            # --------------------------
            # 发送消息
            # --------------------------
            async def send():
                # await asyncio.sleep(1)
                msg = {
                    "reqMsgId": str(uuid.uuid4()),
                    "sendID": USER_ID,
                    "cmd": 1003,  # 发送消息命令码（固定）
                    "data": {
                        "recvID": RECV_ID,
                        "msgFrom": 1,

                        "msgType": 101,  # 101=文本消息
                        "content": "dddddd",
                        "sessionType": 1
                    }
                }
                # await ws.send(json.dumps(msg))
                print("✅ 消息发送成功")

            # 并行运行：收 + 发
            await asyncio.gather(
                receive_loop()
            )

    except websockets.exceptions.ConnectionClosedError:
        print("\n❌ 连接被服务器断开 → 99% 是 Token 错误 或 userID 不存在")
    except Exception as e:
        print("\n❌ 错误：", e)


if __name__ == "__main__":
    asyncio.run(send_msg_stable())