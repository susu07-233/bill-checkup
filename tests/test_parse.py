"""账单解析的测试。用 tests/fixtures/ 里的模拟账单。"""

from pathlib import Path

import pytest

from core.parse import parse_alipay, parse_bill, parse_wechat
from core.schema import COLUMNS

FIXTURES = Path(__file__).parent / "fixtures"
ALIPAY = (FIXTURES / "alipay_sample.csv").read_bytes()
WECHAT = (FIXTURES / "wechat_sample.xlsx").read_bytes()


# ---------- 支付宝 ----------

def test_alipay_reads_all_rows():
    df = parse_alipay(ALIPAY)
    assert list(df.columns) == COLUMNS
    assert len(df) == 6


def test_alipay_first_row():
    row = parse_alipay(ALIPAY).iloc[0]
    assert row["id"] == "ali_2026093022001100001"   # 单号后面的 \t 已经去掉
    assert row["amount"] == 25.5
    assert row["direction"] == "支出"
    assert row["counterparty"] == "美团"
    assert row["platform"] == "支付宝"
    assert str(row["time"]) == "2026-09-30 12:31:05"


def test_alipay_directions():
    df = parse_alipay(ALIPAY)
    assert set(df["direction"]) == {"支出", "收入", "不计收支"}


# ---------- 微信 ----------

def test_wechat_reads_all_rows():
    df = parse_wechat(WECHAT)
    assert list(df.columns) == COLUMNS
    assert len(df) == 7


def test_wechat_first_row():
    row = parse_wechat(WECHAT).iloc[0]
    assert row["id"] == "wx_4200002026093000001"
    assert row["amount"] == 9.9                     # "¥9.90" 已经变成数字
    assert row["direction"] == "支出"
    assert row["counterparty"] == "瑞幸咖啡"
    assert row["platform"] == "微信"


def test_wechat_neutral_direction():
    df = parse_wechat(WECHAT)
    recharge = df[df["raw_type"] == "零钱充值"].iloc[0]
    assert recharge["direction"] == "不计收支"       # 原来是 "/"


# ---------- 自动识别 ----------

def test_parse_bill_detects_platform():
    assert parse_bill("支付宝账单.csv", ALIPAY)["platform"].iloc[0] == "支付宝"
    assert parse_bill("微信账单.XLSX", WECHAT)["platform"].iloc[0] == "微信"


def test_parse_bill_rejects_unknown_file():
    with pytest.raises(ValueError):
        parse_bill("照片.jpg", b"")
