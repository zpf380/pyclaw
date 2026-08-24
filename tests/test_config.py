# -*- coding: utf-8 -*-
"""配置加载/保存/键名转换测试."""
import json
from pathlib import Path

from pyclaw.config.loader import (
    load_config,
    save_config,
    convert_keys,
    convert_to_camel,
    camel_to_snake,
    snake_to_camel,
)
from pyclaw.config.schema import Config


def test_key_conversion():
    assert camel_to_snake("maxTokens") == "max_tokens"
    assert snake_to_camel("max_tokens") == "maxTokens"
    assert convert_keys({"maxTokens": 1, "nested": {"apiKey": "k"}}) == {
        "max_tokens": 1, "nested": {"api_key": "k"}}
    assert convert_to_camel({"max_tokens": 1, "nested": {"api_key": "k"}}) == {
        "maxTokens": 1, "nested": {"apiKey": "k"}}


def test_default_config():
    cfg = Config()
    assert cfg.agents.defaults.model
    assert cfg.get_api_key() is None


def test_load_roundtrip(tmp_path):
    path = tmp_path / "pyclaw.json"
    cfg = Config()
    save_config(cfg, path)
    assert path.exists()
    loaded = load_config(path)
    assert loaded.agents.defaults.model == cfg.agents.defaults.model
    # 文件中键应为 camelCase
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "maxTokens" in raw["agents"]["defaults"]


def test_load_missing_file_returns_default():
    cfg = load_config(Path("/nonexistent/path/pyclaw.json"))
    assert isinstance(cfg, Config)


def test_workspace_path_property():
    cfg = Config()
    assert str(cfg.workspace_path).endswith("workspace")
