"""流水页的测试。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.filters import summarize

PAGE = str(Path(__file__).parent.parent / "app_pages" / "transactions.py")


def page_with_demo_data() -> AppTest:
    at = AppTest.from_file(PAGE, default_timeout=20)
    at.run()                                     # 第一次运行：没有数据
    at.button[0].click().run()                   # 点「用示例账单试试」
    return at


def metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


def bulk_set(at: AppTest, keyword: str, category: str):
    """在「明细」里搜索 keyword，把结果批量设为 category。"""
    at.segmented_control(key="flow_mode").set_value("明细").run()
    at.text_input[0].input(keyword).run()
    at.selectbox(key="bulk_category").select(category).run()
    next(b for b in at.button if b.label.startswith("应用到")).click().run()


def test_empty_state_offers_demo():
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "还没有导入数据" in at.info[0].value
    assert any("示例账单" in b.label for b in at.button)


def test_shows_everything_by_default():
    at = page_with_demo_data()
    assert not at.exception
    assert at.metric[0].value == f"{len(at.session_state['transactions'])} 笔"


def test_default_view_is_spending_by_merchant():
    """苏宇晨的需求：筛选后要能看到每一项花了多少钱。"""
    at = page_with_demo_data()
    table = at.dataframe[0].value
    expected = summarize(at.session_state["transactions"], "counterparty")
    assert list(table.columns[:4]) == ["商家", "笔数", "支出", "收入"]
    assert table.iloc[0]["商家"] == expected.iloc[0]["counterparty"]     # 花得最多的商家排第一
    assert table.iloc[0]["支出"] == expected.iloc[0]["支出"]


def test_merchant_summary_follows_filters():
    at = page_with_demo_data()
    at.text_input[0].input("瑞幸").run()
    table = at.dataframe[0].value
    df = at.session_state["transactions"]
    luckin = df[df["counterparty"] == "瑞幸咖啡"]
    assert list(table["商家"]) == ["瑞幸咖啡"]
    assert table.iloc[0]["笔数"] == len(luckin)
    assert table.iloc[0]["支出"] == round(luckin["amount"].sum(), 2)


def test_pick_a_merchant_to_see_its_transactions():
    at = page_with_demo_data()
    at.selectbox(key="pick_counterparty").select("美团").run()
    assert not at.exception
    assert any(h.value.startswith("美团 的") for h in at.subheader)
    detail = at.dataframe[1].value
    df = at.session_state["transactions"]
    assert len(detail) == (df["counterparty"] == "美团").sum()
    assert set(detail["交易对方"]) == {"美团"}


def test_food_and_drink_total():
    """苏宇晨的需求（Q12）：一眼看到「吃喝」一共花了多少。"""
    at = page_with_demo_data()
    df = at.session_state["transactions"]
    spend = df[df["direction"] == "支出"]
    expected = spend.loc[spend["category"].isin(["餐饮", "零食饮品"]), "amount"].sum()
    assert metric(at, "其中吃喝") == f"{expected:,.2f} 元"


def test_category_summary_merges_into_groups_by_default():
    at = page_with_demo_data()
    at.segmented_control(key="flow_mode").set_value("按分类汇总").run()
    table = at.dataframe[0].value
    assert "吃喝" in set(table["大类"]) and "餐饮" not in set(table["大类"])
    at.selectbox(key="pick_group").select("吃喝").run()
    df = at.session_state["transactions"]
    expected = ((df["direction"] == "支出") & df["category"].isin(["餐饮", "零食饮品"])).sum()
    assert len(at.dataframe[1].value) == expected


def test_pick_a_category_including_income_group():
    at = page_with_demo_data()
    at.segmented_control(key="flow_mode").set_value("按分类汇总").run()
    at.toggle(key="merge_groups").set_value(False).run()          # 关掉大类，看细分
    df = at.session_state["transactions"]
    at.selectbox(key="pick_category").select("收入 / 不计收支").run()
    assert len(at.dataframe[1].value) == (df["direction"] != "支出").sum()
    at.selectbox(key="pick_category").select("交通").run()
    assert len(at.dataframe[1].value) == ((df["category"] == "交通") & (df["direction"] == "支出")).sum()


def test_clicking_a_platform_shows_only_that_platform():
    """苏宇晨测试发现的问题：以前点一个平台是「取消」它，全部取消后又变成显示全部。"""
    at = page_with_demo_data()
    at.segmented_control[0].set_value("微信").run()
    df = at.session_state["transactions"]
    assert at.metric[0].value == f"{(df['platform'] == '微信').sum()} 笔"


def test_clicking_a_direction_shows_only_that_direction():
    at = page_with_demo_data()
    at.segmented_control[1].set_value("支出").run()
    df = at.session_state["transactions"]
    assert at.metric[0].value == f"{(df['direction'] == '支出').sum()} 笔"
    assert metric(at, "收入") == "0.00 元"                        # 只看支出，收入为 0


def test_category_filter_disabled_when_nothing_is_categorized():
    """苏宇晨测试发现的问题：还没分类时选任何分类都是 0 笔，让人以为坏了。"""
    at = page_with_demo_data()
    at.session_state["transactions"] = at.session_state["transactions"].assign(category=None, category_source=None)
    at.run()
    assert at.multiselect[0].disabled


def test_imported_data_is_auto_categorized_and_filterable():
    at = page_with_demo_data()
    assert not at.multiselect[0].disabled
    at.multiselect[0].select("零食饮品").run()
    df = at.session_state["transactions"]
    assert at.metric[0].value == f"{(df['category'] == '零食饮品').sum()} 笔"
    assert set(at.dataframe[0].value["商家"]) >= {"瑞幸咖啡", "蜜雪冰城"}


def test_keyword_search():
    at = page_with_demo_data()
    at.text_input[0].input("瑞幸").run()
    df = at.session_state["transactions"]
    assert at.metric[0].value == f"{(df['counterparty'] == '瑞幸咖啡').sum()} 笔"


def test_bulk_change_is_saved_for_next_import():
    from core.overrides import load_overrides
    at = page_with_demo_data()
    bulk_set(at, "瑞幸", "其他")
    df = at.session_state["transactions"]
    luckin_ids = set(df.loc[df["counterparty"] == "瑞幸咖啡", "id"])
    saved = load_overrides()
    assert luckin_ids <= set(saved) and all(saved[i] == {"category": "其他"} for i in luckin_ids)


def test_bulk_set_category():
    at = page_with_demo_data()
    before = at.session_state["transactions"].copy()
    bulk_set(at, "食堂", "其他")

    assert not at.exception
    df = at.session_state["transactions"]
    is_canteen = df["counterparty"].str.contains("食堂")
    assert (df.loc[is_canteen, "category"] == "其他").all()
    assert (df.loc[is_canteen, "category_source"] == "手动").all()
    # 其他交易没被改
    others = before[~before["counterparty"].str.contains("食堂")]
    assert df.set_index("id").loc[others["id"], "category"].tolist() == others["category"].tolist()
