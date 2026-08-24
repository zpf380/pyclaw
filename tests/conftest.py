# -*- coding: utf-8 -*-
"""pytest 共享 fixtures.

所有 DB 相关测试使用临时文件数据库，避免污染项目根目录的 pyclaw.db。
"""
import sys

import pytest

# 控制台 UTF-8 输出，避免 Windows GBK 终端崩溃
for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "reconfigure", None):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


@pytest.fixture()
def db_manager(tmp_path):
    """临时 SQLite 数据库的 DatabaseManager 实例."""
    from pyclaw.database.database import DatabaseManager

    db_path = tmp_path / "test.db"
    manager = DatabaseManager(f"sqlite:///{db_path}")
    yield manager
    manager.engine.dispose()


@pytest.fixture()
def workspace(tmp_path):
    """临时 workspace 目录（含 skills 子目录）."""
    ws = tmp_path / "workspace"
    (ws / "skills").mkdir(parents=True, exist_ok=True)
    return ws
