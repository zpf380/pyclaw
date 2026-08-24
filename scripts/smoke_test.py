# -*- coding: utf-8 -*-
"""Gateway RPC 冒烟测试脚本.

覆盖：登录鉴权、系统状态、技能 CRUD、工具 CRUD、敏感词 CRUD、消息 CRUD、
敏感词过滤、agent.run 全链路（LLM 调用）。
用法: python scripts/smoke_test.py
"""
import asyncio
import json
import sys
import time

import websockets

# 控制台统一 UTF-8 输出，避免 GBK 终端打印非 GBK 字符崩溃
for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "reconfigure", None):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

URI = "ws://localhost:18790"
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    tag = "PASS" if cond else "FAIL"
    (PASS if cond else FAIL).append(name)
    print(f"  [{tag}] {name}" + (f"  -> {detail}" if detail and not cond else ""))


async def main():
    async with websockets.connect(URI) as ws:
        rid = [0]

        async def rpc(method, params, expect_error=None, timeout=30):
            rid[0] += 1
            req_id = f"t{rid[0]}"
            await ws.send(json.dumps({
                "id": req_id, "jsonrpc": "2.0", "method": method, "params": params,
            }))
            while True:
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                if resp.get("id") == req_id:
                    if expect_error:
                        assert resp.get("error"), f"期望错误但成功: {resp}"
                        assert resp["error"]["code"] == expect_error, resp
                    else:
                        assert resp.get("error") is None, f"RPC 错误: {resp['error']}"
                    return resp

        # ============ 1. 鉴权 ============
        print("== 1. 登录与鉴权 ==")
        r = await rpc("system.login", {"username": "admin", "password": "admin123"})
        token = r["result"]["token"]
        check("登录成功并返回 token", bool(token))
        user = r["result"]["user"]
        check("登录返回 admin 角色", user["role"] == "admin", f"role={user.get('role')}")

        AUTH = {"token": token}

        # 无 token 应被拒绝
        r = await rpc("system.status", {}, expect_error=-32005)
        check("无 token 访问被拒绝 (AUTH_REQUIRED)", True)

        # 无效 token 应被拒绝
        r = await rpc("system.status", {"token": "bad-token"}, expect_error=-32006)
        check("无效 token 被拒绝 (AUTH_INVALID)", True)

        # 登录失败
        r = await rpc("system.login", {"username": "admin", "password": "wrong"}, expect_error=-32006)
        check("错误密码被拒绝", True)

        # ============ 2. 系统状态 ============
        print("== 2. 系统状态 ==")
        r = await rpc("system.status", AUTH)
        st = r["result"]
        check("system.status 返回 server 信息", "server" in st and st["server"]["running"] is True)
        check("system.status 返回 python 版本", "system" in st and bool(st["system"]["python_version"]))

        r = await rpc("system.listAgents", AUTH)
        agents = r["result"]
        check("system.listAgents 返回 AgentLoop", any(a.get("name") == "AgentLoop" for a in agents), str(agents))

        # ============ 3. 技能 ============
        print("== 3. 技能管理 ==")
        r = await rpc("system.listSkills", AUTH)
        skills = r["result"]
        check("system.listSkills 返回技能列表", isinstance(skills, list))
        print(f"   共 {len(skills)} 个技能: {[s.get('code') for s in skills][:10]}")

        skill_code = f"test_skill_{int(time.time())}"
        r = await rpc("system.addSkill", {**AUTH, "name": "测试技能", "code": skill_code, "description": "冒烟测试技能", "content": "# 测试\n\n这是用于测试的技能内容。"})
        sres = r["result"]
        check("system.addSkill 成功", sres.get("success"), str(sres))
        if sres.get("success"):
            skill_id = sres["skill"]["id"]
            # 获取内容
            r = await rpc("system.getSkillContent", {**AUTH, "code": skill_code})
            sc = r["result"]
            check("system.getSkillContent 返回正文", sc.get("success") and "测试" in sc["skill"]["content"], str(sc))
            # 更新（禁用）
            r = await rpc("system.updateSkill", {**AUTH, "id": skill_id, "status": "inactive"})
            check("system.updateSkill 禁用成功", r["result"].get("success"), str(r["result"]))
            r = await rpc("system.listSkills", AUTH)
            disabled = [s for s in r["result"] if s["id"] == skill_id]
            check("禁用状态已生效", disabled and disabled[0]["status"] == "inactive", str(disabled))
            # 删除
            r = await rpc("system.deleteSkill", {**AUTH, "id": skill_id})
            check("system.deleteSkill 成功", r["result"].get("success"), str(r["result"]))

        # ============ 4. 工具 ============
        print("== 4. 工具管理 ==")
        r = await rpc("agent.listTools", {**AUTH, "agent": "AgentLoop"})
        tools = r["result"]
        check("agent.listTools 返回工具列表", isinstance(tools, list) and len(tools) >= 10, f"{len(tools)} 个")
        builtin_names = {t["name"] for t in tools if t["builtin"]}
        check("内置工具标记正确", {"read_file", "write_file", "exec", "web_search"} <= builtin_names, str(builtin_names))

        tool_name = f"test_tool_{int(time.time())}"
        r = await rpc("agent.addTool", {**AUTH, "name": tool_name, "description": "冒烟测试工具", "category": "custom", "config": {"command": "", "script": "print('hello from tool')", "parameters": None}})
        tres = r["result"]
        check("agent.addTool 成功", tres.get("success"), str(tres))
        if tres.get("success"):
            tool_id = tres["tool"]["id"]
            r = await rpc("agent.testTool", {**AUTH, "id": tool_id, "args": {}})
            tt = r["result"]
            check("agent.testTool 可执行自定义工具", tt.get("success") and "hello from tool" in tt.get("output", ""), str(tt))
            r = await rpc("agent.deleteTool", {**AUTH, "id": tool_id})
            check("agent.deleteTool 成功", r["result"].get("success"), str(r["result"]))

        # ============ 5. 敏感词 ============
        print("== 5. 敏感词管理 ==")
        r = await rpc("system.listSensitiveRules", AUTH)
        rules = r["result"]
        check("system.listSensitiveRules 返回列表", isinstance(rules, list))
        kw = f"测试敏感{int(time.time())}"

        # --- block 动作 ---
        r = await rpc("system.addSensitiveRule", {**AUTH, "keyword": kw, "action": "block", "category": "test", "severity": "high"})
        rres = r["result"]
        check("system.addSensitiveRule 成功 (block)", rres.get("success"), str(rres))
        if rres.get("success"):
            rule_id = rres["rule"]["id"]
            r = await rpc("system.filterMessageContent", {**AUTH, "content": f"这是一段包含 {kw} 的文本"})
            fr = r["result"]
            check("block 动作拦截命中", fr["passed"] is False and "拦截" in fr["filtered_content"], str(fr))
            r = await rpc("system.updateSensitiveRule", {**AUTH, "id": rule_id, "action": "replace", "replacement": "***"})
            check("system.updateSensitiveRule 成功 (block->replace)", r["result"].get("success"), str(r["result"]))
            r = await rpc("system.filterMessageContent", {**AUTH, "content": f"这是一段包含 {kw} 的文本"})
            fr = r["result"]
            check("replace 动作脱敏放行", fr["passed"] is True and kw not in fr["filtered_content"] and "***" in fr["filtered_content"], str(fr))
            r = await rpc("system.deleteSensitiveRule", {**AUTH, "id": rule_id})
            check("system.deleteSensitiveRule 成功", r["result"].get("success"), str(r["result"]))

        # --- mask 动作（缺省 replacement 兜底 ***） ---
        r = await rpc("system.addSensitiveRule", {**AUTH, "keyword": kw, "action": "mask", "category": "test", "severity": "high"})
        rres = r["result"]
        check("system.addSensitiveRule 成功 (mask)", rres.get("success"), str(rres))
        if rres.get("success"):
            rule_id = rres["rule"]["id"]
            r = await rpc("system.filterMessageContent", {**AUTH, "content": f"这是一段包含 {kw} 的文本"})
            fr = r["result"]
            check("mask 动作脱敏放行", fr["passed"] is True and kw not in fr["filtered_content"] and "***" in fr["filtered_content"], str(fr))
            r = await rpc("system.deleteSensitiveRule", {**AUTH, "id": rule_id})
            check("mask 规则删除成功", r["result"].get("success"), str(r["result"]))

        # --- 正常文本放行 ---
        r = await rpc("system.filterMessageContent", {**AUTH, "content": "正常文本没有敏感内容"})
        fr2 = r["result"]
        check("正常文本放行", fr2["passed"] is True, str(fr2))

        # ============ 6. 消息 ============
        print("== 6. 消息管理 ==")
        r = await rpc("system.addMessage", {**AUTH, "session_id": "default", "content": "冒烟测试消息", "message_type": "user", "sender": "user", "receiver": "system"})
        check("system.addMessage 成功", r["result"].get("success"), str(r["result"]))
        r = await rpc("system.listMessages", {**AUTH, "session_id": "default", "limit": 20})
        msgs = r["result"]
        check("system.listMessages 返回消息", any("冒烟测试消息" in m.get("content", "") for m in msgs), str(msgs)[:200])
        r = await rpc("system.clearMessages", {**AUTH, "session_id": "default"})
        check("system.clearMessages 成功", r["result"].get("success"), str(r["result"]))

        # ============ 7. agent.run 全链路 ============
        print("== 7. agent.run 全链路（调用 LLM） ==")
        rid[0] += 1
        req_id = f"t{rid[0]}"
        await ws.send(json.dumps({
            "id": req_id, "jsonrpc": "2.0", "method": "agent.run",
            "params": {**AUTH, "agent": "AgentLoop", "id": "user-smoke", "message": "请只回复：冒烟测试通过"},
        }))
        # agent.run 是 fire-and-forget，结果经 websocket 推送 id=1001
        reply = None
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=deadline - time.time()))
            except asyncio.TimeoutError:
                break
            if resp.get("id") == "1001":
                reply = resp.get("result") or ""
                break
        check("agent.run 返回 LLM 回复", bool(reply), f"reply={str(reply)[:100]}")
        if reply:
            check("LLM 回复含期望字样", "冒烟测试" in reply, str(reply)[:100])

    print()
    print(f"===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====")
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
