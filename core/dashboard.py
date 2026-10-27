"""看板用到的计算：只处理数据，不涉及界面。

所有函数只看「支出」（不计收支、收入都不算）；跨月退款是负数，会自动抵扣。
"""

import pandas as pd

from core.filters import UNCATEGORIZED, to_group
from core.money import yuan
from core.schema import SPENDING_TYPES

NEED, FLEX, OTHER = "必要", "弹性", "其他"
TYPE_ORDER = [NEED, FLEX, OTHER]


def spending_type(category) -> str:
    """分类 → 必要 / 弹性 / 其他。"""
    return next((t for t, members in SPENDING_TYPES.items() if category in members), OTHER)


def spending(df: pd.DataFrame) -> pd.DataFrame:
    """只留支出，并加上 月份、日期、分类（没分类的填「未分类」）、大类、必要/弹性 这几列。"""
    s = df[df["direction"] == "支出"].copy()
    s["category"] = s["category"].fillna(UNCATEGORIZED).replace("", UNCATEGORIZED)
    s["month"] = s["time"].dt.strftime("%Y-%m")
    s["date"] = s["time"].dt.normalize()
    s["group"] = s["category"].map(to_group)
    s["type"] = s["category"].map(spending_type)
    return s


def months(df: pd.DataFrame) -> list[str]:
    return sorted(spending(df)["month"].unique())


def kpis(df: pd.DataFrame) -> dict:
    """总支出、日均、吃喝、必要 / 弹性 / 其他 各多少、弹性占比。"""
    s = spending(df)
    total = float(s["amount"].sum())
    days = (df["time"].max().normalize() - df["time"].min().normalize()).days + 1 if len(df) else 0
    by_type = s.groupby("type")["amount"].sum()
    result = {
        "支出": round(total, 2),
        "天数": days,
        "日均": round(total / days, 2) if days else 0.0,
        "吃喝": round(float(s.loc[s["group"] == "吃喝", "amount"].sum()), 2),
        **{t: round(float(by_type.get(t, 0.0)), 2) for t in TYPE_ORDER},
    }
    result["弹性占比"] = result[FLEX] / total if total > 0 else 0.0
    return result


def monthly_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """每月 必要 / 弹性 / 其他 各花了多少。列：month, type, amount。"""
    s = spending(df)
    out = s.groupby(["month", "type"], as_index=False)["amount"].sum()
    out["amount"] = out["amount"].round(2)
    return out


def by_category(df: pd.DataFrame) -> pd.DataFrame:
    """每个分类花了多少，按金额从多到少。列：category, type, amount, count。"""
    s = spending(df)
    out = (s.groupby(["category", "type"], as_index=False)
           .agg(amount=("amount", "sum"), count=("id", "size")))
    out["amount"] = out["amount"].round(2)
    return out.sort_values("amount", ascending=False).reset_index(drop=True)


def top_merchants(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """花钱最多的 n 个商家。列：counterparty, amount, count, type（这个商家的钱主要属于哪类）。"""
    s = spending(df)
    out = (s.groupby("counterparty", as_index=False)
           .agg(amount=("amount", "sum"), count=("id", "size"),
                type=("type", lambda t: t.value_counts().index[0])))
    out["amount"] = out["amount"].round(2)
    return out.sort_values("amount", ascending=False).head(n).reset_index(drop=True)


def daily(df: pd.DataFrame) -> pd.DataFrame:
    """每天花了多少，没花钱的日子补 0（消费日历用）。列：date, amount, weekday(0=周一), week。"""
    s = spending(df)
    if s.empty:
        return pd.DataFrame(columns=["date", "amount", "weekday", "week"])
    days = pd.date_range(df["time"].min().normalize(), df["time"].max().normalize(), freq="D")
    out = s.groupby("date")["amount"].sum().reindex(days, fill_value=0.0).rename_axis("date").reset_index()
    out["amount"] = out["amount"].round(2)
    out["weekday"] = out["date"].dt.day_of_week
    out["week"] = out["date"] - pd.to_timedelta(out["weekday"], unit="D")   # 这一周的周一
    return out


def insights(df: pd.DataFrame) -> list[str]:
    """用规则写几句「小结」（第 10 步会换成 AI 写的月报）。"""
    s = spending(df)
    if s.empty:
        return []
    k = kpis(df)
    lines = [f"这段时间一共支出 **{yuan(k['支出'])}**，平均每天 {yuan(k['日均'])}。"]

    cats = by_category(df)
    flex = cats[cats["type"] == FLEX]
    if k["支出"] > 0 and not flex.empty:
        top = flex.iloc[0]
        compare = "比必要支出还多" if k[FLEX] > k[NEED] else "少于必要支出"
        lines.append(f"弹性支出 {yuan(k[FLEX])}，占 **{k['弹性占比']:.0%}**，{compare}；"
                     f"其中最多的是「{top['category']}」{yuan(top['amount'])}。")
    if k["吃喝"] > 0:
        lines.append(f"吃喝一共 {yuan(k['吃喝'])}，占总支出的 {k['吃喝'] / k['支出']:.0%}。")

    d = daily(df)
    peak = d.loc[d["amount"].idxmax()]
    peak_day = s[s["date"] == peak["date"]]
    main_cat = peak_day.groupby("category")["amount"].sum().idxmax()
    lines.append(f"花得最多的一天是 {peak['date']:%m月%d日}（{yuan(peak['amount'])}），主要花在「{main_cat}」。")
    no_spend = int((d["amount"] <= 0).sum())
    if no_spend:
        lines.append(f"有 {no_spend} 天一分钱没花。")
    return lines
