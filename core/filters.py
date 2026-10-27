"""流水页用到的数据操作：筛选、改分类。只处理数据，不涉及界面。"""

from datetime import date

import pandas as pd

UNCATEGORIZED = "未分类"
SOURCE_MANUAL = "手动"


def filter_transactions(
    df: pd.DataFrame,
    start: date | None = None,
    end: date | None = None,
    platforms: list[str] | None = None,
    directions: list[str] | None = None,
    categories: list[str] | None = None,
    keyword: str = "",
) -> pd.DataFrame:
    """按条件筛选交易。参数为空（None 或空列表）表示这一项不筛选。

    categories 里可以包含「未分类」，表示还没有分类的交易。
    keyword 在交易对方和商品说明里搜索，不区分大小写。
    """
    mask = pd.Series(True, index=df.index)
    day = df["time"].dt.date

    if start:
        mask &= day >= start
    if end:
        mask &= day <= end
    if platforms:
        mask &= df["platform"].isin(platforms)
    if directions:
        mask &= df["direction"].isin(directions)
    if categories:
        category = df["category"].fillna(UNCATEGORIZED).replace("", UNCATEGORIZED)
        mask &= category.isin(categories)
    if keyword.strip():
        text = (df["counterparty"].astype(str) + " " + df["item"].astype(str)).str.lower()
        for word in keyword.lower().split():   # 多个词用空格隔开，要同时包含
            mask &= text.str.contains(word, regex=False)

    return df[mask]


def summarize(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """按某一列（比如 counterparty 商家、category 分类）汇总：每一项花了多少、收了多少。

    返回列：by、笔数、支出、收入、支出占比（0–1），按支出从多到少排序。
    「不计收支」的记录只算笔数，不算钱。跨月退款是负数，会抵扣对应项的支出。
    """
    key = df[by].fillna(UNCATEGORIZED).replace("", UNCATEGORIZED) if by == "category" else df[by]
    spend = df["amount"].where(df["direction"] == "支出", 0.0)
    income = df["amount"].where(df["direction"] == "收入", 0.0)
    out = (
        pd.DataFrame({by: key, "笔数": 1, "支出": spend, "收入": income})
        .groupby(by, as_index=False)
        .sum()
    )
    out[["支出", "收入"]] = out[["支出", "收入"]].round(2)
    total_spend = out["支出"].clip(lower=0).sum()
    out["支出占比"] = (out["支出"].clip(lower=0) / total_spend) if total_spend else 0.0
    return out.sort_values(["支出", "收入"], ascending=False).reset_index(drop=True)


def set_category(df: pd.DataFrame, ids, category: str | None) -> pd.DataFrame:
    """把指定 id 的交易改成某个分类，并标记为「手动」分类。返回新表，不改原表。

    category 为空表示清除分类。
    """
    df = df.copy()
    rows = df["id"].isin(list(ids))
    df.loc[rows, "category"] = category or None
    df.loc[rows, "category_source"] = SOURCE_MANUAL if category else None
    return df
