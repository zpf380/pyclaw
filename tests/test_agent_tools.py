# -*- coding: utf-8 -*-
"""Agent 工具（自定义工具 ScriptTool、ExecTool 安全守卫、工具注册表）测试."""
import asyncio
import sys

import pytest

from pyclaw.agent.tools.custom import ScriptTool
from pyclaw.agent.tools.registry import ToolRegistry
from pyclaw.agent.tools.shell import ExecTool
from pyclaw.agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
from pyclaw.config.schema import ExecToolConfig


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestToolRegistry:
    def test_register_unregister(self):
        reg = ToolRegistry()
        tool = ReadFileTool()
        reg.register(tool)
        assert reg.has("read_file")
        defs = reg.get_definitions()
        assert defs[0]["function"]["name"] == "read_file"
        reg.unregister("read_file")
        assert not reg.has("read_file")

    def test_duplicate_register(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(ReadFileTool())  # 不抛错
        assert len(reg.tool_names) == 1

    def test_execute(self, tmp_path):
        reg = ToolRegistry()
        reg.register(WriteFileTool())
        target = tmp_path / "a.txt"
        result = run(reg.execute("write_file", {"path": str(target), "content": "hi"}))
        assert target.exists()
        assert "successfully wrote" in result.lower() or "已写入" in result


class TestExecToolGuard:
    def make_exec(self, ws, restrict=True):
        return ExecTool(
            working_dir=str(ws),
            timeout=10,
            restrict_to_workspace=restrict,
        )

    def test_deny_pattern_rm_rf(self, tmp_path):
        tool = self.make_exec(tmp_path)
        result = run(tool.execute("rm -rf /"))
        assert result.startswith("Error")

    def test_block_outside_path(self, tmp_path):
        tool = self.make_exec(tmp_path)
        # 引用 workspace 外绝对路径应被拦截
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("x")
        result = run(tool.execute(f"type \"{outside}\""))
        assert result.startswith("Error")
        assert "outside" in result

    def test_allow_inside_path(self, tmp_path):
        tool = self.make_exec(tmp_path)
        inner = tmp_path / "inner.txt"
        inner.write_text("hello")
        # Windows: type 输出文件内容；POSIX 兼容回退用 python 打印
        if sys.platform == "win32":
            result = run(tool.execute(f"type \"{inner}\""))
        else:
            result = run(tool.execute(f"cat \"{inner}\""))
        assert "hello" in result

    def test_allow_current_interpreter(self, tmp_path):
        # 运行解释器本身（脚本工具依赖）不应被拦
        tool = self.make_exec(tmp_path)
        result = run(tool.execute(f"\"{sys.executable}\" -c \"print('ok')\""))
        assert "ok" in result


class TestFileSystemWorkspaceBoundary:
    """文件系统工具必须限制在工作区内（越权防护）."""

    def test_read_blocked_outside(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        tool = ReadFileTool(workspace=ws)
        result = run(tool.execute(str(outside)))
        assert result.startswith("Error")
        assert "工作区" in result

    def test_read_allowed_inside(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        inner = ws / "a.txt"
        inner.write_text("hello")
        tool = ReadFileTool(workspace=ws)
        result = run(tool.execute(str(inner)))
        assert "hello" in result

    def test_write_blocked_outside(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        target = tmp_path / "evil.txt"
        tool = WriteFileTool(workspace=ws)
        result = run(tool.execute(str(target), "pwned"))
        assert result.startswith("Error")
        assert not target.exists()

    def test_no_workspace_backward_compat(self, tmp_path):
        # workspace=None 不限制（保持既有调用方兼容）
        target = tmp_path / "anywhere.txt"
        tool = WriteFileTool()
        result = run(tool.execute(str(target), "ok"))
        assert "Successfully wrote" in result
        assert target.exists()

    def test_write_reports_utf8_bytes(self, tmp_path):
        target = tmp_path / "b.txt"
        tool = WriteFileTool()
        # 2 个汉字（6 字节）+ 3 个 ASCII = 9 字节；len() 是 5 字符（字符数≠字节数）
        content = "中文abc"
        assert len(content) == 5
        assert "9 bytes" in run(tool.execute(str(target), content))

    def test_bool_rejected_as_integer(self):
        from pyclaw.agent.tools.base import Tool
        import pytest

        class IntTool(Tool):
            name = "int_tool"
            description = ""
            @property
            def parameters(self):
                return {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
            async def execute(self, **kwargs):
                return ""

        tool = IntTool()
        errors = tool.validate_params({"n": True})
        assert any("should be integer" in e for e in errors)
        # 真实整数通过
        assert tool.validate_params({"n": 3}) == []


class TestScriptTool:
    def test_script_mode(self, workspace):
        tool = ScriptTool(
            name="hello",
            description="say hi",
            config={"script": "print('hello from tool')", "command": ""},
            workspace=workspace,
            exec_config=ExecToolConfig(timeout=10, restrict_to_workspace=True),
        )
        result = run(tool.execute())
        assert "hello from tool" in result

    def test_command_mode_with_args(self, workspace):
        tool = ScriptTool(
            name="echo",
            description="echo arg",
            config={"command": "python -c \"print('got:{arg}')\"", "parameters": None},
            workspace=workspace,
            exec_config=ExecToolConfig(timeout=10, restrict_to_workspace=True),
        )
        result = run(tool.execute(arg="42"))
        assert "got:42" in result

    def test_no_config(self, workspace):
        tool = ScriptTool(name="empty", description="", config={}, workspace=workspace)
        result = run(tool.execute())
        assert "未配置" in result

    def test_script_has_parameter_schema(self, workspace):
        config = {
            "script": "print('x')",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
        tool = ScriptTool(name="p", description="", config=config, workspace=workspace)
        params = tool.parameters
        assert params["required"] == ["name"]
        assert "name" in params["properties"]
