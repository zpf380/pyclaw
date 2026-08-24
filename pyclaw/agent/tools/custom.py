"""自定义工具运行时代理 - 由 tool_registry 元数据驱动的通用工具

tool_registry 中 category=custom（或任意非内置）的工具只有元数据，没有对应
工具类实现。ScriptTool 把 DB 里的 name/description/config 包装成一个 Tool，
执行时在 workspace 内通过 ExecTool 代理运行，从而让「自定义工具」真正参与
AgentLoop 的工具调用循环。

config 支持两种运行模式（二选一）：
  - command:    命令模板，支持 {arg} 占位符，LLM 传入的实参按名替换后执行
  - script:     Python 脚本内容，写入 workspace 临时目录后由本解释器执行
  - parameters: 参数 JSON Schema（可选，缺省空 schema，参数全部可选）
"""

import os
import sys
from pathlib import Path
from typing import Any

from pyclaw.agent.tools.base import Tool
from pyclaw.agent.tools.shell import ExecTool


class ScriptTool(Tool):
    """自定义工具的通用代理.

    Args:
        name: 工具名称（来自 tool_registry.name）
        description: 工具描述（来自 tool_registry.description）
        config: 工具配置 dict（command/script/parameters）
        workspace: 工作区路径（命令限制在此目录内执行）
        exec_config: ExecToolConfig（timeout / restrict_to_workspace）
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        config: dict | None = None,
        workspace: str | Path | None = None,
        exec_config: Any = None,
    ):
        self._name = name
        self._description = description or f"自定义工具 {name}"
        self._config = config or {}
        # workspace 缺失时退回当前目录，交由 ExecTool 的 working_dir 兜底
        work_dir = str(workspace) if workspace else None
        timeout = getattr(exec_config, "timeout", 60)
        restrict = getattr(exec_config, "restrict_to_workspace", False)
        self._exec = ExecTool(
            working_dir=work_dir,
            timeout=timeout,
            restrict_to_workspace=restrict,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        """参数 JSON Schema（优先使用 config.parameters，缺省空 schema）. """
        params = self._config.get("parameters")
        if isinstance(params, dict):
            return params
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        """执行自定义工具.

        优先 command 模式（{arg} 占位替换）；未配置时退回 script 模式
        （写入临时 .py 文件后由本解释器执行）。
        """
        command = self._config.get("command")
        script = self._config.get("script")

        if command:
            rendered = self._render(command, kwargs)
            return await self._exec.execute(command=rendered)

        if script:
            return await self._run_script(script)

        return "Error: 自定义工具未配置 command 或 script"

    def _render(self, template: str, kwargs: dict[str, Any]) -> str:
        """把命令模板中的 {arg} 占位符替换为实际参数值."""
        rendered = template
        for key, value in kwargs.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered

    async def _run_script(self, script: str) -> str:
        """把 Python 脚本写入 workspace/.pyclaw_tmp/ 后执行，返回输出."""
        # 统一解析为绝对路径：working_dir 可能为相对路径，直接拼接再交给
        # ExecTool（以 working_dir 为 cwd）执行时会二次解析导致路径翻倍。
        base = Path(self._exec.working_dir or os.getcwd()).resolve()
        tmp_dir = base / ".pyclaw_tmp"
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
            script_path = (tmp_dir / f"{self._name}.py").resolve()
            script_path.write_text(script, encoding="utf-8")
            command = f'"{sys.executable}" "{script_path}"'
            return await self._exec.execute(command=command)
        except Exception as e:
            return f"Error executing script tool '{self._name}': {str(e)}"
