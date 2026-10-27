"""看板页的测试。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.dashboard import kpis

PAGE = str(Path(__file__).parent.parent / "pages" / "3_看板.py")


def page_with_demo_data() -> AppTest:
    at = AppTest.from_file(PAGE, default_timeout=20)
    at.run()
    at.button[0].click().run()
    return at


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_empty_state_offers_demo():
    at = AppTest.from_file(PAGE).run()
    assert not at.exception
    assert "还没有导入数据" in at.info[0].value


def test_dashboard_renders_with_demo_data():
    at = page_with_demo_data()
    assert not at.exception
    k = kpis(at.session_state["transactions"])
    assert metric(at, "总支出") == f"{k['支出']:,.2f} 元"
    assert metric(at, "弹性支出占比") == f"{k['弹性占比']:.0%}"
    assert len(at.get("vega_lite_chart")) == 6                       # 必要/弹性、每月、每日、分类、商家、日历
    assert any("花得最多的一天" in m.value for m in at.markdown)


def test_daily_chart_share_mode():
    at = page_with_demo_data()
    at.segmented_control(key="daily_mode").set_value("占比").run()
    assert not at.exception


def test_pick_a_month_shows_change_vs_last_month():
    at = page_with_demo_data()
    at.selectbox[0].select("2026-09").run()
    assert not at.exception
    df = at.session_state["transactions"]
    month = lambda m: df[df["time"].dt.strftime("%Y-%m") == m]
    sept, aug = kpis(month("2026-09")), kpis(month("2026-08"))
    total = next(m for m in at.metric if m.label == "总支出")
    assert total.value == f"{sept['支出']:,.2f} 元"
    assert total.delta == f"{sept['支出'] - aug['支出']:+,.2f} 元"
