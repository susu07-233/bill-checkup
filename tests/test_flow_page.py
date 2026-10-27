"""流水页的测试。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app_state import load_files
from core.demo import demo_files

PAGE = str(Path(__file__).parent.parent / "pages" / "2_流水.py")


def page_with_demo_data() -> AppTest:
    at = AppTest.from_file(PAGE)
    at.run()                                     # 第一次运行：没有数据
    at.button[0].click().run()                   # 点「用示例账单试试」
    return at


def test_empty_state_offers_demo():
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "还没有导入数据" in at.info[0].value
    assert any("示例账单" in b.label for b in at.button)


def test_shows_all_income_and_spending_by_default():
    at = page_with_demo_data()
    assert not at.exception
    df = at.session_state["transactions"]
    expected = (df["direction"] != "不计收支").sum()     # 默认只看支出和收入
    assert at.metric[0].value == f"{expected} 笔"


def test_keyword_search():
    at = page_with_demo_data()
    at.text_input[0].input("瑞幸").run()
    df = at.session_state["transactions"]
    expected = (df["counterparty"] == "瑞幸咖啡").sum()
    assert at.metric[0].value == f"{expected} 笔"


def test_bulk_set_category():
    at = page_with_demo_data()
    at.text_input[0].input("食堂").run()
    at.selectbox(key="bulk_category").select("餐饮").run()
    next(b for b in at.button if b.label.startswith("应用到")).click().run()

    assert not at.exception
    df = at.session_state["transactions"]
    canteen = df[df["counterparty"].str.contains("食堂")]
    assert (canteen["category"] == "餐饮").all()
    assert (canteen["category_source"] == "手动").all()
    assert df.loc[~df["counterparty"].str.contains("食堂"), "category"].isna().all()   # 其他交易没被改
