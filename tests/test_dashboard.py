"""看板计算的测试。用示例数据（小林半年的账单）。"""

import pandas as pd
import pytest

from core.classify import classify
from core.clean import clean, totals
from core.dashboard import (
    FLEX,
    NEED,
    OTHER,
    by_category,
    daily,
    insights,
    kpis,
    monthly_by_type,
    months,
    spending_type,
    top_merchants,
)
from core.demo import demo_files
from core.filters import group_spending
from core.parse import parse_bill
from core.schema import CATEGORIES, SPENDING_TYPES


@pytest.fixture(scope="module")
def df():
    return classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])


def test_every_category_has_a_type():
    assert set(SPENDING_TYPES[NEED]).isdisjoint(SPENDING_TYPES[FLEX])
    assert {spending_type(c) for c in CATEGORIES} == {NEED, FLEX, OTHER}
    assert spending_type("其他") == OTHER and spending_type("未分类") == OTHER
    assert spending_type("餐饮") == NEED and spending_type("零食饮品") == FLEX


def test_kpis_add_up(df):
    k = kpis(df)
    assert k["支出"] == totals(df)["支出"]
    assert round(k[NEED] + k[FLEX] + k[OTHER], 2) == k["支出"]
    assert k["吃喝"] == group_spending(df, "吃喝")["吃喝"]
    assert k["天数"] == 179                                         # 2026-05-01 到 10-26
    assert abs(k["日均"] - k["支出"] / 179) < 0.01
    assert 0 < k["弹性占比"] < 1


def test_monthly_by_type_adds_up(df):
    m = monthly_by_type(df)
    assert months(df) == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert round(m["amount"].sum(), 2) == kpis(df)["支出"]
    sept = m[m["month"] == "2026-09"].set_index("type")["amount"]
    assert sept[FLEX] > 0 and sept[NEED] > 0


def test_by_category_sorted_and_typed(df):
    c = by_category(df)
    assert c["amount"].is_monotonic_decreasing
    assert round(c["amount"].sum(), 2) == kpis(df)["支出"]
    assert (c.set_index("category").loc["零食饮品", "type"]) == FLEX


def test_top_merchants(df):
    t = top_merchants(df, 5)
    assert len(t) == 5 and t["amount"].is_monotonic_decreasing


def test_daily_fills_days_without_spending(df):
    d = daily(df)
    assert len(d) == 179
    assert round(d["amount"].sum(), 2) == kpis(df)["支出"]
    assert set(d["weekday"]) == set(range(7))
    assert (d["week"].dt.day_of_week == 0).all()                         # 每周从周一开始


def test_insights_add_what_the_cards_dont_show(df):
    text = " ".join(insights(df))
    k = kpis(df)
    assert f"{k['支出']:,.2f} 元" not in text                         # 总支出已经在数字卡片里，不重复
    assert f"{k['弹性占比']:.0%}" in text
    assert "主要在" in text                                           # 弹性最多的分类花在哪几个商家
    assert "花得最多的一天" in text


def test_weekly_by_type_adds_up(df):
    from core.dashboard import weekly_by_type
    w = weekly_by_type(df)
    assert round(w["amount"].sum(), 2) == kpis(df)["支出"]
    assert (w["week"].dt.day_of_week == 0).all()                      # 每周从周一开始
    assert w["week"].nunique() == 27                                  # 5/1（周五）到 10/26（周一）跨 27 周
    assert w.loc[w["week"] == "2026-09-28", "label"].iloc[0] == "09/28–10/04"
    shares = w.groupby("week")["share"].sum()
    spent = w.groupby("week")["amount"].apply(lambda a: a.clip(lower=0).sum()) > 0
    assert ((shares[spent] - 1).abs() < 1e-9).all()                   # 有花钱的周，各部分占比加起来是 100%
    assert (shares[~spent] == 0).all()                                # 退款比花的还多的周（5/1 那周）不算占比


def test_previous_month(df):
    from core.dashboard import previous_month
    assert previous_month(df, "2026-09") == "2026-08"
    assert previous_month(df, "2026-05") is None


def test_no_comparison_with_a_partial_month(df):
    """真实账单从 9 月 27 日开始：拿 9 月的 4 天和 10 月整月比，会误以为 10 月花钱暴涨。"""
    from core.dashboard import previous_month
    late_start = df[df["time"] >= "2026-08-25"]                       # 8 月只有 7 天
    assert previous_month(late_start, "2026-09") is None


def test_excluded_and_income_not_counted(df):
    income_only = df[df["direction"] != "支出"]
    assert kpis(income_only)["支出"] == 0
    assert insights(income_only) == []


def test_monthly_trend(df):
    from core.dashboard import monthly_trend
    t = monthly_trend(df)
    assert list(t["month"]) == months(df)
    assert round(t["支出"].sum(), 2) == kpis(df)["支出"]
    sept = t.set_index("month").loc["2026-09"]
    assert sept["吃喝"] == kpis(df[df["time"].dt.month == 9])["吃喝"]
