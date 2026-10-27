"""筛选、改分类的测试。用示例数据。"""

from datetime import date

import pandas as pd
import pytest

from core.clean import clean
from core.demo import demo_files
from core.clean import totals
from core.filters import SOURCE_MANUAL, UNCATEGORIZED, filter_transactions, set_category, summarize
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


def test_summarize_by_category_counts_uncategorized(df):
    labelled = set_category(df, df[df["counterparty"].str.contains("食堂")]["id"], "餐饮")
    out = summarize(labelled, "category").set_index("category")
    assert set(out.index) == {"餐饮", UNCATEGORIZED}
    assert out["笔数"].sum() == len(df)
