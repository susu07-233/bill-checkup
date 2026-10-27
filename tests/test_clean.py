"""清洗规则的测试。"""

from pathlib import Path

import pandas as pd
import pytest

from core.clean import (
    REASON_CLOSED,
    REASON_DUPLICATE,
    REASON_REFUND_INCOME,
    REASON_REFUNDED,
    _refunded_amount,
    clean,
    cross_month_refunds,
    totals,
)
from core.parse import parse_alipay, parse_wechat

FIXTURES = Path(__file__).parent / "fixtures"
ALIPAY = parse_alipay((FIXTURES / "alipay_sample.csv").read_bytes())
WECHAT = parse_wechat((FIXTURES / "wechat_sample.xlsx").read_bytes())
ALL = pd.concat([ALIPAY, WECHAT], ignore_index=True)


def by_id(df, id_):
    return df[df["id"] == id_].iloc[0]


def test_counts():
    kept, removed = clean(ALL)
    assert len(ALL) == 14
    assert len(kept) == 11
    assert len(removed) == 3


def test_closed_trade_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "ali_2026092022001100004")["reason"] == REASON_CLOSED


def test_full_refund_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "wx_4200002026092200003")["reason"] == REASON_REFUNDED


def test_refund_income_with_original_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "wx_4200002026091400007")["reason"] == REASON_REFUND_INCOME


def test_partial_refund_reduces_amount():
    kept, _ = clean(ALL)
    assert by_id(kept, "wx_4200002026091200006")["amount"] == 50.0   # 80 - 30


def test_cross_month_refund_becomes_negative_spend():
    kept, _ = clean(ALL)
    row = by_id(kept, "wx_4200002026090800008")      # 火车票退款，原订单不在账单里
    assert row["direction"] == "支出"
    assert row["amount"] == -45.0
    assert list(cross_month_refunds(kept)["id"]) == ["wx_4200002026090800008"]


def test_split_refund_matches_original_total():
    """真实账单里的情况：一笔订单分两次退款（10.5 + 121），状态都写着原订单总共退了 131.5。"""
    base = {"counterparty": "x", "item": "", "platform": "微信", "pay_method": "零钱",
            "category": None, "category_source": None}
    rows = [
        {**base, "id": "a", "time": pd.Timestamp("2026-09-01"), "amount": 200.0, "direction": "支出",
         "status": "已退款(¥131.50)", "raw_type": "商户消费"},
        {**base, "id": "b", "time": pd.Timestamp("2026-09-02"), "amount": 10.5, "direction": "收入",
         "status": "已退款¥131.50", "raw_type": "x-退款"},
        {**base, "id": "c", "time": pd.Timestamp("2026-09-02"), "amount": 121.0, "direction": "收入",
         "status": "已退款¥131.50", "raw_type": "x-退款"},
    ]
    with_original = pd.DataFrame(rows)
    kept, removed = clean(with_original)
    assert set(removed["id"]) == {"b", "c"}              # 原订单在：两笔退款都排除
    assert totals(kept)["支出"] == 68.5                    # 200 - 131.5

    kept, removed = clean(with_original[with_original["id"] != "a"])
    assert removed.empty                                 # 原订单不在：跨月退款
    assert totals(kept)["支出"] == -131.5


@pytest.mark.parametrize("status, refunded", [
    ("已退款(¥30.00)", 30.0),
    ("已退款（￥30.00）", 30.0),
    ("已退款¥131.50", 131.5),      # 真实微信账单里的写法：没有括号
    ("已退款¥1,200.00", 1200.0),
    ("已全额退款", 0.0),
    ("已退款", 0.0),
    ("支付成功", 0.0),
])
def test_refunded_amount_formats(status, refunded):
    assert _refunded_amount(status) == refunded


def test_totals():
    kept, _ = clean(ALL)
    assert "wx_1000050026090500005" in set(kept["id"])                # 零钱充值还在表里，但不算
    # 支付宝 25.5 + 39.9 + 179.9；微信 9.9 + 50 + 50（部分退款后）- 45（跨月退款）
    assert totals(kept) == {"支出": 310.2, "收入": 152.0}


def test_duplicates_removed():
    kept, removed = clean(pd.concat([ALL, ALIPAY], ignore_index=True))  # 支付宝导入了两次
    assert len(kept) == 11
    assert (removed["reason"] == REASON_DUPLICATE).sum() == 6


def test_original_table_not_modified():
    before = ALL.copy()
    clean(ALL)
    pd.testing.assert_frame_equal(ALL, before)
