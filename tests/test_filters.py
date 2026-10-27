"""筛选、改分类的测试。用示例数据。"""

from datetime import date

import pandas as pd
import pytest

from core.clean import clean
from core.demo import demo_files
from core.clean import totals
from core.filters import (
    NOT_SPENDING,
    SOURCE_MANUAL,
    UNCATEGORIZED,
    filter_transactions,
    set_category,
    summarize,
)
from core.parse import parse_bill


@pytest.fixture(scope="module")
def df():
    kept, _ = clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))
    return kept


def test_no_filters_returns_everything(df):
    assert len(filter_transactions(df)) == len(df)


def test_date_range(df):
    out = filter_transactions(df, start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert len(out) > 0
    assert out["time"].dt.month.eq(9).all()


def test_platform_and_direction(df):
    out = filter_transactions(df, platforms=["支付宝"], directions=["支出"])
    assert set(out["platform"]) == {"支付宝"}
    assert set(out["direction"]) == {"支出"}


def test_keyword_searches_counterparty_and_item(df):
    assert set(filter_transactions(df, keyword="食堂")["counterparty"]) == {"第一食堂", "第二食堂"}
    assert (filter_transactions(df, keyword="外卖")["item"].str.contains("外卖")).all()
    assert len(filter_transactions(df, keyword="steam")) > 0          # 不区分大小写
    assert len(filter_transactions(df, keyword="第一 午餐")) > 0       # 多个词同时满足
    assert len(filter_transactions(df, keyword="不存在的商家xyz")) == 0


def test_category_filter_and_uncategorized(df):
    ids = df["id"].head(3)
    labelled = set_category(df, ids, "餐饮")
    assert len(filter_transactions(labelled, categories=["餐饮"])) == 3
    assert len(filter_transactions(labelled, categories=[UNCATEGORIZED])) == len(df) - 3


def test_set_category_marks_manual_and_keeps_original(df):
    before = df.copy()
    ids = df["id"].head(2)
    out = set_category(df, ids, "交通")
    changed = out[out["id"].isin(ids)]
    assert (changed["category"] == "交通").all()
    assert (changed["category_source"] == SOURCE_MANUAL).all()
    pd.testing.assert_frame_equal(df, before)                         # 原表没被改

    cleared = set_category(out, ids, None)
    assert cleared[cleared["id"].isin(ids)]["category"].isna().all()


def test_summarize_by_merchant(df):
    out = summarize(df, "counterparty")
    assert list(out.columns) == ["counterparty", "笔数", "支出", "收入", "支出占比"]
    assert out["笔数"].sum() == len(df)
    assert round(out["支出"].sum(), 2) == totals(df)["支出"]           # 各商家加起来 = 总支出
    assert round(out["收入"].sum(), 2) == totals(df)["收入"]
    assert out["支出"].is_monotonic_decreasing                           # 花得最多的排最前
    assert abs(out["支出占比"].clip(lower=0).sum() - 1) < 1e-9

    canteen = out[out["counterparty"] == "第一食堂"].iloc[0]
    expected = df[(df["counterparty"] == "第一食堂") & (df["direction"] == "支出")]["amount"].sum()
    assert canteen["支出"] == round(expected, 2)


def test_summarize_by_category_separates_income_from_uncategorized(df):
    labelled = set_category(df, df[df["counterparty"].str.contains("食堂")]["id"], "餐饮")
    out = summarize(labelled, "category").set_index("category")
    assert set(out.index) == {"餐饮", UNCATEGORIZED, NOT_SPENDING}
    assert out["笔数"].sum() == len(df)
    assert out.loc[NOT_SPENDING, "支出"] == 0                       # 这一组只有收入和不计收支
    assert out.loc[UNCATEGORIZED, "收入"] == 0                      # 未分类的都是支出


# ---------- 大类：吃喝 = 餐饮 + 零食饮品 ----------

def test_to_group():
    from core.filters import to_group
    assert to_group("餐饮") == "吃喝" and to_group("零食饮品") == "吃喝"
    assert to_group("交通") == "交通"


def test_summarize_by_group_merges_food_and_snacks():
    from core.classify import classify
    from core.filters import group_spending
    df = classify(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True).pipe(lambda d: clean(d)[0]))
    by_cat = summarize(df, "category").set_index("category")
    by_group = summarize(df, "group").set_index("group")

    assert "吃喝" in by_group.index and "餐饮" not in by_group.index and "零食饮品" not in by_group.index
    assert by_group.loc["吃喝", "支出"] == round(by_cat.loc["餐饮", "支出"] + by_cat.loc["零食饮品", "支出"], 2)
    assert by_group.loc["吃喝", "笔数"] == by_cat.loc["餐饮", "笔数"] + by_cat.loc["零食饮品", "笔数"]
    assert by_group.loc["交通", "支出"] == by_cat.loc["交通", "支出"]                 # 其他分类不变
    assert round(by_group["支出"].sum(), 2) == round(by_cat["支出"].sum(), 2)       # 总数不变

    food = group_spending(df, "吃喝")
    assert food["吃喝"] == by_group.loc["吃喝", "支出"]
    assert food["餐饮"] == by_cat.loc["餐饮", "支出"] and food["零食饮品"] == by_cat.loc["零食饮品", "支出"]


def test_filter_by_day_kind(df):
    from core.daytype import day_types
    out = filter_transactions(df, day_kinds=["节假日"])
    assert len(out) > 0 and (day_types(out["time"]) == "节假日").all()
    assert out["time"].dt.strftime("%m-%d").isin(["10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",
                                                   "09-25", "09-26", "09-27", "06-19", "06-20", "06-21",
                                                   "05-01", "05-02", "05-03", "05-04", "05-05"]).all()
