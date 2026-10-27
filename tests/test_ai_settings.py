"""AI 设置：本地读 secrets.toml，线上（魔搭创空间）读环境变量。"""

import app_state


def test_reads_key_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-only")
    s = app_state.ai_settings()
    assert s["api_key"] == "sk-test-only"
    assert s["base_url"].startswith("https://") and s["model"]


def test_bad_key_means_no_ai(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-a-key")
    assert app_state.ai_settings() is None
