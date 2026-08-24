"""内置工具 seed 元数据 - 供 tool_registry 启动时同步

工具类的 name/description/parameters 均为不依赖 __init__ 的 property，
这里用 object.__new__ 绕过构造函数读取，避免为仅读元数据而传入占位依赖。
"""

from pyclaw.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from pyclaw.agent.tools.shell import ExecTool
from pyclaw.agent.tools.web import WebSearchTool, WebFetchTool
from pyclaw.agent.tools.message import MessageTool
from pyclaw.agent.tools.spawn import SpawnTool
from pyclaw.agent.tools.cron import CronTool

# (工具类, 分组, 默认版本, 默认作者)
BUILTIN_TOOLS = [
    (ReadFileTool, "system", "1.0.0", "pyclaw"),
    (WriteFileTool, "system", "1.0.0", "pyclaw"),
    (EditFileTool, "system", "1.0.0", "pyclaw"),
    (ListDirTool, "system", "1.0.0", "pyclaw"),
    (ExecTool, "system", "1.0.0", "pyclaw"),
    (WebSearchTool, "web", "1.0.0", "pyclaw"),
    (WebFetchTool, "web", "1.0.0", "pyclaw"),
    (MessageTool, "message", "1.0.0", "pyclaw"),
    (SpawnTool, "system", "1.0.0", "pyclaw"),
    (CronTool, "system", "1.0.0", "pyclaw"),
]


def builtin_tool_metadata() -> list[dict]:
    """返回 [{name, description, config(参数 JSON Schema), category, version, author}, ...]"""
    result = []
    for tool_cls, category, version, author in BUILTIN_TOOLS:
        try:
            # 绕过 __init__ 构造，仅读取元数据 property
            tool = object.__new__(tool_cls)
            result.append({
                "name": tool.name,
                "description": tool.description,
                "config": tool.parameters,
                "category": category,
                "version": version,
                "author": author,
            })
        except Exception:
            continue
    return result
