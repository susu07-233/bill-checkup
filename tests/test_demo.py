"""示例数据的测试：格式能被正常解析，内容像一个真实大学生的账单。"""

import pandas as pd
import pytest

from core.clean import REASON_CLOSED, REASON_REFUND_INCOME, REASON_REFUNDED, clean, cross_month_refunds
from core.demo import demo_files
from core.parse import parse_bill


@pytest.fixture(scope="module")
def files():
    return demo_files()


@pytest.fixture(scope="module")
def cleaned(files):
    raw = pd.concat([parse_bill(name, data) for name, data in files], ignore_index=True)
    return raw, *clean(raw)


def test_two_files_one_per_platform(files):
    names = [name for name, _ in files]
    assert names[0].endswith(".csv") and names[1].endswith(".xlsx")


def test_same_result_every_time(files):
    """固定随机种子，每次生成的内容一样，方便测试和演示。
    （比较解析后的内容，不比较 xlsx 原始字节：xlsx 里记着保存时间，每秒都不一样。）"""
    again = demo_files()
    assert [name for name, _ in again] == [name for name, _ in files]
    assert again[0][1] == files[0][1]                                   # 支付宝 CSV：逐字节相同
    pd.testing.assert_frame_equal(parse_bill(*again[1]), parse_bill(*files[1]))   # 微信 xlsx：内容相同


def test_parsed_cleanly(cleaned):
    raw, kept, _ = cleaned
    assert len(raw) > 400
    assert set(raw["platform"]) == {"微信", "支付宝"}
    assert raw["time"].notna().all() and raw["amount"].notna().all()
    assert raw["id"].is_unique


def test_covers_six_months(cleaned):
    _, kept, _ = cleaned
    assert kept["time"].dt.strftime("%Y-%m").nunique() == 6


def test_monthly_spending_is_realistic(cleaned):
    _, kept, _ = cleaned
    spend = kept[kept["direction"] == "支出"]
    monthly = spend.groupby(spend["time"].dt.strftime("%Y-%m"))["amount"].sum()
    assert monthly.between(1000, 4500).all(), monthly.to_dict()
    assert monthly.idxmax() == "2026-09"      # 开学季花得最多
    assert monthly.idxmin() == "2026-07"      # 暑假在家花得最少


def test_has_every_special_case(cleaned):
    _, kept, removed = cleaned
    reasons = set(removed["reason"])
    assert {REASON_CLOSED, REASON_REFUNDED, REASON_REFUND_INCOME} <= reasons
    assert len(cross_month_refunds(kept)) == 1
    assert (kept["direction"] == "不计收支").any()
    assert kept["status"].str.contains("已退款").any()   # 部分退款
