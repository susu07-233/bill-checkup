"""清洗规则的测试。"""

from pathlib import Path

import pandas as pd

from core.clean import (
    REASON_CLOSED,
    REASON_DUPLICATE,
    REASON_REFUND_INCOME,
    REASON_REFUNDED,
    clean,
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
    assert len(ALL) == 13
    assert len(kept) == 10
    assert len(removed) == 3


def test_closed_trade_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "ali_2026092022001100004")["reason"] == REASON_CLOSED


def test_full_refund_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "wx_4200002026092200003")["reason"] == REASON_REFUNDED


def test_refund_income_removed():
    _, removed = clean(ALL)
    assert by_id(removed, "wx_4200002026091400007")["reason"] == REASON_REFUND_INCOME


def test_partial_refund_reduces_amount():
    kept, _ = clean(ALL)
    assert by_id(kept, "wx_4200002026091200006")["amount"] == 50.0   # 80 - 30


def test_neutral_kept_but_not_counted():
    kept, _ = clean(ALL)
    assert "wx_1000050026090500005" in set(kept["id"])                # 零钱充值还在表里
    # 支付宝 25.5 + 39.9 + 179.9，微信 9.9 + 50 + 50（部分退款后）；零钱充值的 500 不算
    assert totals(kept) == {"支出": 355.2, "收入": 152.0}


def test_duplicates_removed():
    kept, removed = clean(pd.concat([ALL, ALIPAY], ignore_index=True))  # 支付宝导入了两次
    assert len(kept) == 10
    assert (removed["reason"] == REASON_DUPLICATE).sum() == 6


def test_original_table_not_modified():
    before = ALL.copy()
    clean(ALL)
    pd.testing.assert_frame_equal(ALL, before)
