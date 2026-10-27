"""清洗：把解析好的交易表里「不该算钱」的记录挑出来，并修正部分退款的金额。

规则（按顺序）：
1. 重复记录（同一个 id）只保留一条
2. 交易关闭 / 失败的：钱没花出去 → 排除
3. 全额退款的：钱退回来了 → 排除
4. 部分退款的：金额扣掉退回的部分，比如 ¥80 退 ¥30 → 记为 ¥50
5. 「退款到账」的收入记录：原订单已经在第 3、4 条处理过，再算一次就重复了 → 排除

「不计收支」的记录（充值、理财、转入余额宝等）保留在表里，但统计支出和收入时不会算进去。
"""

import re

import pandas as pd

# 排除原因（会显示在页面上）
REASON_DUPLICATE = "重复记录"
REASON_CLOSED = "交易关闭或失败"
REASON_REFUNDED = "已全额退款"
REASON_REFUND_INCOME = "退款到账（已在原订单扣除）"

# 匹配部分退款状态，取出退回的金额。真实微信账单里两种写法都有：
#   「已退款(¥30.00)」和「已退款¥30.00」（没有括号）
_PARTIAL_REFUND = re.compile(r"已退款[(（]?[¥￥]?([\d,]+(?:\.\d+)?)")


def _removal_reason(row: pd.Series) -> str | None:
    """判断一条记录该不该排除；该排除就返回原因，否则返回 None。"""
    status = str(row["status"])
    raw_type = str(row["raw_type"])

    if "关闭" in status or "失败" in status:
        return REASON_CLOSED
    if "全额退款" in status and row["direction"] == "支出":
        return REASON_REFUNDED
    if row["direction"] == "收入" and ("退款" in status or "退款" in raw_type):
        return REASON_REFUND_INCOME
    return None


def _refunded_amount(status: str) -> float:
    """从「已退款(¥30.00)」里取出 30.0；不是部分退款就返回 0。"""
    match = _PARTIAL_REFUND.search(str(status))
    return float(match.group(1).replace(",", "")) if match else 0.0


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """清洗交易表。

    返回两张表：
      kept    —— 保留下来、参与统计的交易
      removed —— 被排除的交易，多一列 reason 写着排除原因
    """
    df = df.copy()

    # 1. 去重
    dup_mask = df.duplicated(subset="id", keep="first")
    duplicates = df[dup_mask].assign(reason=REASON_DUPLICATE)
    df = df[~dup_mask]

    # 2、3、5. 按规则判断是否排除
    reasons = df.apply(_removal_reason, axis=1)
    removed = pd.concat([duplicates, df[reasons.notna()].assign(reason=reasons[reasons.notna()])])
    kept = df[reasons.isna()].copy()

    # 4. 部分退款：扣掉退回的金额
    refunded = kept["status"].map(_refunded_amount)
    is_spend = kept["direction"] == "支出"
    kept.loc[is_spend, "amount"] = (kept.loc[is_spend, "amount"] - refunded[is_spend]).round(2)

    return kept.reset_index(drop=True), removed.reset_index(drop=True)


def totals(df: pd.DataFrame) -> dict[str, float]:
    """统计支出、收入合计（不计收支的不算）。"""
    return {
        "支出": round(float(df.loc[df["direction"] == "支出", "amount"].sum()), 2),
        "收入": round(float(df.loc[df["direction"] == "收入", "amount"].sum()), 2),
    }
