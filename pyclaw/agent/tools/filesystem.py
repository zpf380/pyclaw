"""File system tools: read, write, edit.
文件系统工具 - 文件读写操作"""

from pathlib import Path
from typing import Any

from pyclaw.agent.tools.base import Tool


def _checked_path(path: str, workspace: "Path | None") -> tuple[Path | None, str | None]:
    """解析路径并校验其位于工作区内（防越权读写任意路径）.

    Args:
        path: 用户提供的路径
        workspace: 工作区根目录（None 表示不限制，保持向后兼容）

    Returns:
        (resolved_path, error)。error 非空表示路径被拦截，此时 resolved_path 为 None。
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception as e:
        return None, f"Error: 无法解析路径 '{path}': {e}"
    if workspace is not None:
        ws = Path(workspace).resolve()
        try:
            inside = resolved == ws or resolved.is_relative_to(ws)
        except ValueError:
            # 不同盘符等场景 is_relative_to 抛 ValueError
            inside = False
        if not inside:
            return None, f"Error: 越权访问——路径不在工作区内: {path}"
    return resolved, None


class ReadFileTool(Tool):
    """Tool to read file contents."""

    def __init__(self, workspace: "Path | None" = None):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        file_path, err = _checked_path(path, self.workspace)
        if err:
            return err
        try:
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            return content
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """Tool to write content to a file."""

    def __init__(self, workspace: "Path | None" = None):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        file_path, err = _checked_path(path, self.workspace)
        if err:
            return err
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content.encode('utf-8'))} bytes to {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""

    def __init__(self, workspace: "Path | None" = None):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        file_path, err = _checked_path(path, self.workspace)
        if err:
            return err
        try:
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."
            
            # Count occurrences
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
            
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            
            return f"Successfully edited {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """Tool to list directory contents."""

    def __init__(self, workspace: "Path | None" = None):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List the contents of a directory."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        dir_path, err = _checked_path(path, self.workspace)
        if err:
            return err
        try:
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"
            
            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")
            
            if not items:
                return f"Directory {path} is empty"
            
            return "\n".join(items)
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
