"""导入页的测试：点「用示例账单试试」后，应该解析、清洗出正确的结果。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).parent.parent / "pages" / "1_导入.py"


def test_sample_button_loads_transactions():
    at = AppTest.from_file(str(PAGE)).run()
    sample_button = next(b for b in at.button if "示例账单" in b.label)
    sample_button.click().run()

    assert not at.exception
    # 模拟账单共 13 笔：保留 10 笔，排除 3 笔（关闭 1、全额退款 1、退款到账 1）
    assert len(at.session_state["transactions"]) == 10
    assert len(at.session_state["removed"]) == 3
    assert at.metric[0].value == "10 笔"
    assert at.metric[1].value == "¥355.20"
    assert "已自动排除 3 笔" in at.expander[0].label
