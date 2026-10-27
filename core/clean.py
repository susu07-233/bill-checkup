"""清洗：把解析好的交易表里「不该算钱」的记录挑出来，并修正退款相关的金额。

规则（按顺序）：
1. 重复记录（同一个 id）只保留一条
2. 交易关闭 / 失败的：钱没花出去 → 排除
3. 全额退款的支出：钱退回来了 → 排除
4. 部分退款的支出：金额扣掉退回的部分，比如 ¥80 退 ¥30 → 记为 ¥50
5. 「退款到账」的收入记录，分两种：
   a. 原订单在这份账单里：退款已经在第 3、4 条扣过了 → 排除
   b. 原订单不在这份账单里（跨月退款，比如上个月买的火车票这个月退了）：
      → 记为一笔「负的支出」，抵扣本月支出（产品决定 Q1，见 docs/改进清单.md）

怎么判断原订单在不在：退款记录的状态里写着原订单一共退了多少（如「已退款¥131.50」，
全额退款时就是它自己的金额）。账单里有一笔支出正好退了这么多、并且时间更早，就算找到了。

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


def _refunded_amount(status: str) -> float:
    """从「已退款(¥30.00)」里取出 30.0；不是部分退款就返回 0。"""
    match = _PARTIAL_REFUND.search(str(status))
    return float(match.group(1).replace(",", "")) if match else 0.0


def _is_refund_income(row: pd.Series) -> bool:
    """是不是一条「退款到账」的收入记录。"""
    return row["direction"] == "收入" and ("退款" in str(row["status"]) or "退款" in str(row["raw_type"]))


def _refund_total(row: pd.Series) -> float:
    """一条记录对应的「原订单一共退了多少」。

    - 原订单（支出）：全额退款 → 它自己的金额；部分退款 → 状态里的金额
    - 退款到账（收入）：状态里写了金额就用它；没写（全额退款）→ 它自己的金额
    """
    from_status = _refunded_amount(row["status"])
    return round(from_status if from_status else float(row["amount"]), 2)


def _removal_reason(row: pd.Series) -> str | None:
    """判断一条记录该不该排除（退款到账的收入记录另外处理）。"""
    status = str(row["status"])
    if "关闭" in status or "失败" in status:
        return REASON_CLOSED
    if "全额退款" in status and row["direction"] == "支出":
        return REASON_REFUNDED
    return None


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """清洗交易表。

    返回两张表：
      kept    —— 保留下来、参与统计的交易（跨月退款是 amount 为负数的「支出」）
      removed —— 被排除的交易，多一列 reason 写着排除原因
    """
    df = df.copy()

    # 1. 去重
    dup_mask = df.duplicated(subset="id", keep="first")
    duplicates = df[dup_mask].assign(reason=REASON_DUPLICATE)
    df = df[~dup_mask]

    # 先找出账单里所有「有退款的原订单」：(一共退了多少, 下单时间)
    originals = df[(df["direction"] == "支出") & df["status"].astype(str).str.contains("退款")]
    original_refunds = [(_refund_total(r), r["time"]) for _, r in originals.iterrows()]

    def has_original(refund_row: pd.Series) -> bool:
        total = _refund_total(refund_row)
        return any(abs(t - total) < 0.005 and when <= refund_row["time"] for t, when in original_refunds)

    # 2、3、5a. 判断哪些要排除
    reasons = df.apply(_removal_reason, axis=1)
    refund_income = df.apply(_is_refund_income, axis=1)
    matched = refund_income & df.apply(has_original, axis=1)
    reasons[matched] = REASON_REFUND_INCOME

    removed = pd.concat([duplicates, df[reasons.notna()].assign(reason=reasons[reasons.notna()])])
    kept = df[reasons.isna()].copy()

    # 4. 部分退款的支出：扣掉退回的金额
    is_spend = kept["direction"] == "支出"
    refunded = kept["status"].map(_refunded_amount)
    kept.loc[is_spend, "amount"] = (kept.loc[is_spend, "amount"] - refunded[is_spend]).round(2)

    # 5b. 跨月退款：变成负的支出，抵扣本月支出
    cross_month = refund_income[reasons.isna()].reindex(kept.index, fill_value=False)
    kept.loc[cross_month, "direction"] = "支出"
    kept.loc[cross_month, "amount"] = -kept.loc[cross_month, "amount"]

    return kept.reset_index(drop=True), removed.reset_index(drop=True)


def cross_month_refunds(kept: pd.DataFrame) -> pd.DataFrame:
    """清洗后表里的跨月退款（金额为负的支出）。"""
    return kept[(kept["direction"] == "支出") & (kept["amount"] < 0)]


def totals(df: pd.DataFrame) -> dict[str, float]:
    """统计支出、收入合计（不计收支的不算；跨月退款是负数，会自动抵扣支出）。"""
    return {
        "支出": round(float(df.loc[df["direction"] == "支出", "amount"].sum()), 2),
        "收入": round(float(df.loc[df["direction"] == "收入", "amount"].sum()), 2),
    }
