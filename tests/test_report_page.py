"""报告页的测试：用假的 AI（不联网）。"""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import app_state
from tests.test_ai_report_qa import FakeLLM

PAGE = str(Path(__file__).parent.parent / "pages" / "4_报告.py")
REPORT = "**一句话总结**：测试月报。"
QUERY = json.dumps({"metric": "count", "categories": ["交通"], "understanding": "交通一共几笔"})


class RoutingLLM(FakeLLM):
    """月报请求返回一段文字；问一问请求（要求返回 JSON 的那种）返回查询条件。"""

    def create(self, **kwargs):
        self.content = QUERY if "response_format" in kwargs else REPORT
        return super().create(**kwargs)


def page(monkeypatch, with_key=True):
    fake = RoutingLLM()
    monkeypatch.setattr(app_state, "ai_client", lambda: (fake, "m") if with_key else None)
    at = AppTest.from_file(PAGE, default_timeout=20)
    at.run()
    at.button[0].click().run()          # 用示例账单
    return at, fake


def test_without_key_shows_rule_summary(monkeypatch):
    at, fake = page(monkeypatch, with_key=False)
    assert not at.exception
    assert "还没有设置 DeepSeek API Key" in at.info[0].value
    assert any("花得最多的一天" in m.value for m in at.markdown)
    assert fake.sent == []                                            # 没 Key 就完全不联网


def test_generate_report(monkeypatch):
    at, fake = page(monkeypatch)
    next(b for b in at.button if b.label == "生成月报").click().run()
    assert not at.exception
    assert any("测试月报" in m.value for m in at.markdown)
    assert any(b.label == "重新生成" for b in at.button)               # 生成过就缓存，不会每次刷新都花钱
    assert len(fake.sent) == 1


def test_ask_a_question(monkeypatch):
    at, fake = page(monkeypatch)
    at.chat_input[0].set_value("交通一共几笔？").run()
    assert not at.exception
    df = at.session_state["transactions"]
    expected = ((df["direction"] == "支出") & (df["category"] == "交通")).sum()
    assert any(f"一共 **{expected} 笔**" in m.value for m in at.markdown)
    assert fake.sent[-1][1]["content"] == "交通一共几笔？"           # 只发了问题本身
