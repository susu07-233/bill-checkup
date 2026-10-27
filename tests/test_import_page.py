"""导入页的测试：点「用示例账单试试」后，应该解析出 11 笔交易。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).parent.parent / "pages" / "1_导入.py"


def test_sample_button_loads_transactions():
    at = AppTest.from_file(str(PAGE)).run()
    sample_button = next(b for b in at.button if "示例账单" in b.label)
    sample_button.click().run()

    assert not at.exception
    assert len(at.session_state["transactions"]) == 11   # 支付宝 6 笔 + 微信 5 笔
    assert at.metric[0].value == "11 笔"
