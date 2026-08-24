# -*- coding: utf-8 -*-
"""SkillsLoader 测试（读取、写入、删除、frontmatter 处理）. """
import pytest

from pyclaw.agent.skills import SkillsLoader


@pytest.fixture()
def loader(workspace):
    return SkillsLoader(workspace)


def test_write_and_read(loader, workspace):
    path = loader.write_skill("my-skill", "我的技能", "一段描述", "# 正文内容\n\n步骤一")
    assert path.exists()
    full = loader.read_skill_full("my-skill")
    assert full["has_file"]
    assert "步骤一" in full["body"]
    meta = loader.get_skill_metadata("my-skill")
    assert meta["name"] == "我的技能"
    assert meta["description"] == "一段描述"


def test_write_preserves_extra_frontmatter_keys(loader):
    loader.write_skill("s1", "S1", "d", "body")
    # 手动补充 always 键再写一次
    p = loader.get_skill_file_path("s1")
    content = p.read_text(encoding="utf-8")
    content = content.replace("name: S1", "name: S1\nalways: true")
    p.write_text(content, encoding="utf-8")

    loader.write_skill("s1", "S1-new", "d2", "new body")
    meta = loader.get_skill_metadata("s1")
    assert meta["always"] == "true"  # 额外键被保留
    assert meta["name"] == "S1-new"


def test_list_skills(loader, workspace):
    loader.write_skill("a-skill", "A", "d", "body")
    loader.write_skill("b-skill", "B", "d", "body")
    names = [s["name"] for s in loader.list_skills()]
    assert "a-skill" in names and "b-skill" in names


def test_delete(loader, workspace):
    loader.write_skill("del-skill", "D", "d", "body")
    assert loader.delete_skill_file("del-skill")
    assert not loader.delete_skill_file("del-skill")
    assert not (workspace / "skills" / "del-skill").exists()


def test_unsafe_code_rejected(loader):
    with pytest.raises(ValueError):
        loader.write_skill("../evil", "E", "d", "body")
    with pytest.raises(ValueError):
        loader.write_skill("a/b", "E", "d", "body")
    with pytest.raises(ValueError):
        loader.write_skill("", "E", "d", "body")


def test_always_skills(loader):
    loader.write_skill("always-1", "A1", "d", "body")
    p = loader.get_skill_file_path("always-1")
    p.write_text("---\nname: always-1\ndescription: d\nalways: true\n---\n\nbody\n", encoding="utf-8")
    loader.write_skill("normal-1", "N1", "d", "body")
    always = loader.get_always_skills()
    assert "always-1" in always
    assert "normal-1" not in always
    # 过滤后不包含 normal-1
    filtered = loader.get_always_skills(include_names=["normal-1"])
    assert "always-1" not in filtered
