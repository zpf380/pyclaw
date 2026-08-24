import asyncio
import websockets
import json

async def client():
    uri = "ws://localhost:18790"
    async with websockets.connect(uri) as ws:
        # 发送请求
        request = {
            "id": "123",
            "jsonrpc": "2.0",
            "method": "agent.listTools",
            "params": {
                "agent": "AgentLoop",
                "message": "Hello!"
            }
        }
        await ws.send(json.dumps(request))

        # 接收响应
        response = await ws.recv()
        data = json.loads(response)

        if "error" in data:
            print(f"Error: {data['error']}")
        else:
            print(f"Result: {data['result']}")

asyncio.run(client())