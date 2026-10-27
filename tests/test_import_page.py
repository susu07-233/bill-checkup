"""导入页的测试：点「用示例账单试试」后，应该解析、清洗出和直接调用函数一样的结果。"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from core.clean import clean, totals
from core.demo import demo_files
from core.parse import parse_bill

PAGE = Path(__file__).parent.parent / "app_pages" / "import_bills.py"
DEMO = clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0]


def test_ai_toggle_disabled_without_key():
    at = AppTest.from_file(str(PAGE))
    at.secrets["DEEPSEEK_API_KEY"] = "在这里粘贴"
    at.run()
    assert at.toggle(key="use_ai").disabled
    assert "还没有设置 DeepSeek API Key" in at.toggle(key="use_ai").help   # 鼠标移到开关旁的问号上能看到


def test_ai_toggle_enabled_with_key():
    at = AppTest.from_file(str(PAGE))
    at.secrets["DEEPSEEK_API_KEY"] = "sk-test"
    at.run()
    assert not at.toggle(key="use_ai").disabled
    assert at.toggle(key="use_ai").value                  # 有 Key 时默认打开


def test_fill_with_ai_fills_what_rules_missed():
    from app_state import fill_with_ai
    from core.classify import classify, load_rules
    from tests.test_ai_classify import FakeAI

    # 示例数据规则能全分出来，这里只用「食堂」一条规则，让大部分交易留给 AI
    rules_only = classify(DEMO, [r for r in load_rules() if r.keyword == "食堂"])
    fake = FakeAI(answers={"": "其他"})                     # 假 AI：什么都答「其他」
    out, (level, message) = fill_with_ai(rules_only, {"api_key": "sk-x", "base_url": "", "model": "m"},
                                          client_factory=lambda *a: fake)
    spend = out[out["direction"] == "支出"]
    assert level == "success" and "AI 补全了" in message
    assert spend["category"].notna().all()                  # 全部分上了
    assert set(spend["category_source"]) == {"规则", "AI"}
    assert (spend.loc[spend["counterparty"].str.contains("食堂"), "category_source"] == "规则").all()


def test_fill_with_ai_keeps_rule_result_on_error():
    from app_state import fill_with_ai
    from core.classify import classify
    from tests.test_ai_classify import FakeAI

    rules_only = classify(DEMO, [])
    out, (level, message) = fill_with_ai(rules_only, {"api_key": "sk-x", "base_url": "", "model": "m"},
                                          client_factory=lambda *a: FakeAI(fail=True))
    assert level == "error" and "只用了规则分类" in message
    pd.testing.assert_frame_equal(out, rules_only)


def test_fill_with_ai_without_key():
    from app_state import fill_with_ai
    out, (level, _) = fill_with_ai(DEMO, None)
    assert level == "warning" and out is DEMO


def test_sample_button_loads_demo_data():
    kept, removed = clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))

    at = AppTest.from_file(str(PAGE)).run()
    sample_button = next(b for b in at.button if "示例账单" in b.label)
    sample_button.click().run()

    assert not at.exception
    assert len(at.session_state["transactions"]) == len(kept)
    assert len(at.session_state["removed"]) == len(removed)
    assert at.subheader[0].value == f"导入了 {len(kept)} 笔交易"
    assert f"自动排除的 {len(removed)} 笔" in at.expander[0].label
    report = " ".join(m.value for m in at.markdown)
    assert "跨月退款" in report and "部分退款" in report and "分类" in report
    assert "¥" not in report                                 # 不用 ¥，免得被看成日元
    assert not at.metric                                     # 金额统计在看板，这里不重复
