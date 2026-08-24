# -*- coding: utf-8 -*-
"""DatabaseManager 各域 CRUD 测试."""
import json


class TestUsers:
    def test_create_and_get_user(self, db_manager):
        r = db_manager.create_user("alice", "hash", "salt", role="member", display_name="Alice")
        assert r["success"]
        user = db_manager.get_user_by_username("alice")
        assert user["username"] == "alice"
        assert user["role"] == "member"
        # 不泄露密码哈希
        assert "password_hash" not in user and "salt" not in user

    def test_duplicate_username(self, db_manager):
        db_manager.create_user("bob", "h", "s")
        r = db_manager.create_user("bob", "h2", "s2")
        assert not r["success"]

    def test_update_role(self, db_manager):
        r = db_manager.create_user("carol", "h", "s", role="member")
        uid = r["user"]["id"]
        r = db_manager.update_user_role(uid, "admin")
        assert r["success"]
        assert db_manager.get_user_by_id(uid)["role"] == "admin"

    def test_token_lifecycle(self, db_manager):
        db_manager.create_user("dave", "h", "s")
        uid = db_manager.get_user_by_username("dave")["id"]
        from datetime import datetime, timedelta

        expires = datetime.utcnow() + timedelta(hours=1)
        r = db_manager.issue_token(uid, "tok_hash_1", expires)
        assert r["success"]
        rec = db_manager.get_token_record_by_hash("tok_hash_1")
        assert rec is not None and rec["user_id"] == uid
        # 吊销后不可用
        db_manager.revoke_token("tok_hash_1")
        assert db_manager.get_token_record_by_hash("tok_hash_1") is None


class TestSkills:
    def test_add_get_update_delete(self, db_manager):
        r = db_manager.add_skill("测试技能", "test-skill", "描述")
        assert r["success"]
        sid = r["skill"]["id"]

        s = db_manager.get_skill_by_code("test-skill")
        assert s["name"] == "测试技能"

        r = db_manager.update_skill(sid, status="inactive")
        assert r["success"]
        assert db_manager.get_skill_by_id(sid)["status"] == "inactive"

        r = db_manager.delete_skill(sid)
        assert r["success"]
        assert db_manager.get_skill_by_code("test-skill") is None

    def test_duplicate_code(self, db_manager):
        db_manager.add_skill("a", "code1", "")
        r = db_manager.add_skill("b", "code1", "")
        assert not r["success"]

    def test_upsert_preserves_status(self, db_manager):
        db_manager.add_skill("a", "code2", "")
        sid = db_manager.get_skill_by_code("code2")["id"]
        db_manager.update_skill(sid, status="inactive")
        # upsert 不应重置 status
        r = db_manager.upsert_skill("a2", "code2", "新描述")
        assert r["success"] and not r["created"]
        assert db_manager.get_skill_by_id(sid)["status"] == "inactive"


class TestTools:
    def test_crud(self, db_manager):
        r = db_manager.add_tool("my-tool", "工具描述", config={"command": "echo hi"})
        assert r["success"]
        tid = r["tool"]["id"]
        assert r["tool"]["builtin"] is False

        t = db_manager.get_tool_by_name("my-tool")
        assert t["config"]["command"] == "echo hi"

        r = db_manager.update_tool(tid, config={"script": "print(1)"})
        assert r["success"]
        assert db_manager.get_tool_by_id(tid)["config"]["script"] == "print(1)"

        r = db_manager.delete_tool(tid)
        assert r["success"]
        assert db_manager.get_tool_by_id(tid) is None

    def test_seed_builtin_tools(self, db_manager):
        defs = [
            {"name": "read_file", "description": "读文件", "config": {"parameters": {}}, "category": "filesystem", "version": "1.0.0", "author": "pyclaw"},
            {"name": "exec", "description": "执行命令", "config": {}, "category": "system"},
        ]
        n = db_manager.seed_builtin_tools(defs)
        assert n == 2
        # 二次 seed 不重复创建，保留 builtin=True
        n2 = db_manager.seed_builtin_tools(defs)
        assert n2 == 0
        t = db_manager.get_tool_by_name("read_file")
        assert t["builtin"] is True

    def test_inactive_tool_names(self, db_manager):
        db_manager.add_tool("t1", "")
        db_manager.add_tool("t2", "")
        # 手动把 t1 置为 inactive
        t1 = db_manager.get_tool_by_name("t1")
        db_manager.update_tool(t1["id"], status="inactive")
        names = db_manager.get_inactive_tool_names()
        assert "t1" in names and "t2" not in names


class TestMessages:
    def test_add_list_clear(self, db_manager):
        r = db_manager.add_message("s1", "hello", "user", "u1", "bot")
        assert r["success"]
        msgs = db_manager.get_messages_by_session("s1", limit=10)
        assert len(msgs) == 1 and msgs[0]["content"] == "hello"

        r = db_manager.clear_session_messages("s1")
        assert r["success"]
        assert db_manager.get_messages_by_session("s1") == []


class TestSensitiveRules:
    def test_crud(self, db_manager):
        r = db_manager.add_sensitive_word_rule("foo", action="block")
        assert r["success"]
        rid = r["rule"]["id"]

        rules = db_manager.get_all_sensitive_rules()
        assert any(x["id"] == rid for x in rules)

        r = db_manager.update_sensitive_rule(rid, action="replace", replacement="***")
        assert r["success"]
        assert db_manager.get_all_sensitive_rules()[0]["action"] == "replace"

        r = db_manager.delete_sensitive_rule(rid)
        assert r["success"]
        assert not any(x["id"] == rid for x in db_manager.get_all_sensitive_rules())

    def test_filter_block(self, db_manager):
        db_manager.add_sensitive_word_rule("禁词", action="block")
        res = db_manager.filter_message("这是一段包含 禁词 的文本")
        assert res["passed"] is False
        assert "拦截" in res["filtered_content"]
        assert res["matched_rules"][0]["keyword"] == "禁词"

    def test_filter_replace(self, db_manager):
        db_manager.add_sensitive_word_rule("禁词", action="replace", replacement="***")
        res = db_manager.filter_message("包含 禁词 的文本")
        assert res["passed"] is True
        assert "***" in res["filtered_content"] and "禁词" not in res["filtered_content"]
        assert res["action_taken"] == "replace"

    def test_filter_mask_without_replacement(self, db_manager):
        # mask 且未提供 replacement 时应默认 ***
        db_manager.add_sensitive_word_rule("禁词", action="mask")
        res = db_manager.filter_message("包含 禁词 的文本")
        assert res["passed"] is True
        assert "***" in res["filtered_content"] and "禁词" not in res["filtered_content"]

    def test_filter_review(self, db_manager):
        db_manager.add_sensitive_word_rule("审核词", action="review")
        res = db_manager.filter_message("包含 审核词 的内容")
        assert res["passed"] is False
        assert res["filtered_content"].startswith("[待审核")

    def test_inactive_rule_ignored(self, db_manager):
        r = db_manager.add_sensitive_word_rule("禁用词", action="block")
        db_manager.update_sensitive_rule(r["rule"]["id"], status="inactive")
        res = db_manager.filter_message("包含 禁用词 的文本")
        assert res["passed"] is True

    def test_clean_text_passes(self, db_manager):
        db_manager.add_sensitive_word_rule("禁词", action="block")
        res = db_manager.filter_message("完全正常的文本")
        assert res["passed"] is True and res["matched_rules"] == []
