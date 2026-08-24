"""Skills loader for agent capabilities.
技能加载器 - 加载和管理Agent技能"""

import json
import os
import re
import shutil
from pathlib import Path

# Default builtin skills directory (relative to this file)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    Loader for agent skills.
    
    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """
    
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    
    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List all available skills.
        
        Args:
            filter_unavailable: If True, filter out skills with unmet requirements.
        
        Returns:
            List of skill info dicts with 'name', 'path', 'source'.
        """
        skills = []
        
        # Workspace skills (highest priority)
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "workspace"})
        
        # Built-in skills
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "builtin"})
        
        # Filter by requirements
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills
    
    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.
        
        Args:
            name: Skill name (directory name).
        
        Returns:
            Skill content or None if not found.
        """
        # Check workspace first
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")
        
        # Check built-in
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")
        
        return None
    
    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.
        
        Args:
            skill_names: List of skill names to load.
        
        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""
    
    def build_skills_summary(self, include_names: set[str] | None = None) -> str:
        """
        Build a summary of all skills (name, description, path, availability).

        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.

        Args:
            include_names: 可选过滤——只列这些技能名（None 列全部，保 CLI 兼容）。

        Returns:
            XML-formatted skills summary.
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if include_names is not None:
            all_skills = [s for s in all_skills if s["name"] in include_names]
        if not all_skills:
            return ""
        
        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)
            
            lines.append(f"  <skill available=\"{str(available).lower()}\">")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")
            
            # Show missing requirements for unavailable skills
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")
            
            lines.append(f"  </skill>")
        lines.append("</skills>")
        
        return "\n".join(lines)

    def get_skill_description(self, name: str) -> str:
        """获取技能描述：优先 frontmatter description，其次 '## Description' 首段，兜底目录名."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        content = self.load_skill(name)
        if content:
            m = re.search(r"^##\s+Description\s*\n(.+?)(?=\n##|\Z)", content, re.MULTILINE | re.DOTALL)
            if m:
                first = m.group(1).strip().split("\n\n")[0].strip()
                if first:
                    return first
            lines = content.strip().splitlines()
            if lines and lines[0].startswith("#"):
                return lines[0].lstrip("#").strip()
        return name

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)
    
    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # Fallback to skill name
    
    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content
    
    def _parse_pyclaw_metadata(self, raw: str) -> dict:
        """Parse pyclaw metadata JSON from frontmatter."""
        try:
            data = json.loads(raw)
            return data.get("pyclaw", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met (bins, env vars)."""
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True
    
    def _get_skill_meta(self, name: str) -> dict:
        """Get pyclaw metadata for a skill (cached in frontmatter)."""
        meta = self.get_skill_metadata(name) or {}
        return self._parse_pyclaw_metadata(meta.get("metadata", ""))
    
    def get_always_skills(self, include_names: list[str] | None = None) -> list[str]:
        """Get skills marked as always=true that meet requirements.

        Args:
            include_names: 可选过滤——只在这些技能名里筛（None 筛全部，保 CLI 兼容）。
        """
        names = set(include_names) if include_names is not None else None
        result = []
        for s in self.list_skills(filter_unavailable=True):
            if names is not None and s["name"] not in names:
                continue
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_pyclaw_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result
    
    def get_skill_metadata(self, name: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter.
        
        Args:
            name: Skill name.
        
        Returns:
            Metadata dict or None.
        """
        content = self.load_skill(name)
        if not content:
            return None
        
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # Simple YAML parsing
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata

        return None

    # ========================================================================
    # 文件落盘操作（SKILL.md 可视化编辑 / 双向同步用）
    # ========================================================================

    def _safe_skill_code(self, code: str) -> str:
        """校验技能编码可作为目录名（防路径穿越）."""
        code = (code or "").strip()
        if not code:
            raise ValueError("技能编码不能为空")
        if code in {".", ".."} or "/" in code or "\\" in code or "\x00" in code:
            raise ValueError("技能编码包含非法字符")
        return code

    def get_skill_file_path(self, code: str):
        """返回 workspace 下技能文件的路径（不检查存在性）."""
        safe = self._safe_skill_code(code)
        return self.workspace_skills / safe / "SKILL.md"

    def read_skill_full(self, code: str) -> dict:
        """读取技能文件内容.

        Returns:
            {"content": 全文(含frontmatter), "body": 正文(剥离frontmatter), "has_file": bool}
        """
        path = self.get_skill_file_path(code)
        if path.exists():
            content = path.read_text(encoding="utf-8")
            return {"content": content, "body": self._strip_frontmatter(content), "has_file": True}
        return {"content": "", "body": "", "has_file": False}

    def write_skill(self, code: str, name: str, description: str, content: str):
        """把技能正文写回 workspace 文件，合并保留既有 frontmatter 额外键.

        Args:
            code: 技能编码（= 目录名）
            name: 技能名称（写入 frontmatter name）
            description: 技能描述（写入 frontmatter description）
            content: SKILL.md 正文（不含 frontmatter）

        Returns:
            写入的文件路径
        """
        safe = self._safe_skill_code(code)
        # 保留既有 frontmatter 的额外键（metadata/always/requires 等）
        existing_meta = self.get_skill_metadata(safe) or {}

        def fmt(v):
            v = str(v)
            # 含冒号或特殊前缀时用引号包裹，避免破坏简单 YAML 解析
            if ":" in v or v.startswith("#") or v.startswith('"') or v.startswith("'"):
                return f'"{v}"'
            return v

        meta_lines = [
            f"name: {fmt(name or safe)}",
            f"description: {fmt(description or '')}",
        ]
        for key, value in existing_meta.items():
            if key in ("name", "description"):
                continue
            meta_lines.append(f"{key}: {fmt(value)}")

        frontmatter = "---\n" + "\n".join(meta_lines) + "\n---\n\n"
        body = (content or "").strip()
        path = self.workspace_skills / safe / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(frontmatter + body + "\n", encoding="utf-8")
        return path

    def delete_skill_file(self, code: str) -> bool:
        """删除 workspace 下的技能目录（内置技能目录不在此，天然不可删）."""
        safe = self._safe_skill_code(code)
        skill_dir = self.workspace_skills / safe
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            return True
        return False

    def export_skill(self, code: str, name: str, description: str):
        """导出 DB 技能为 workspace 文件（已存在则不覆盖，返回 None）."""
        path = self.get_skill_file_path(code)
        if path.exists():
            return None
        return self.write_skill(code, name, description, f"# {name or code}\n\n{description or ''}")
