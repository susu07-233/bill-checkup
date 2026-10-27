"""「好奇心问题」：首页上可以直接点的三个问题，答案由程序算（不用 AI，瞬间出结果、不花钱）。

来自 Codex 的改版建议：先用用户最想知道的问题吸引人（「奶茶花了多少？」），而不是先讲功能。

每个函数返回一个 dict，页面拿它画「小票式」的答案卡片：
  title     一句好奇的标题，比如「原来，奶茶是这样攒起来的」
  amount    大数字（元）
  note      一句说明，比如「12 笔，每笔平均 13 元」
  items     列表：[(名字, 说明), ...]，最多 3 条
  items_label  明细的小标题，比如「支出前三家」，说清楚只列了前几个
  rest      没列出来的部分（名字, 说明），比如（「其他 2 家店」, 「3 笔 · 25.00 元」）；全列出来了就是 None
            items + rest 加起来等于 amount，方便核对（favorite_shop 例外：大金额是最常去那家，明细是其他店）
金额统一保留两位小数（苏宇晨 U17：小票显示 173 元、明细合计 172.70 元，对不上）。
  rows      用到的交易（「看看这几笔」时显示）
"""

import pandas as pd

from core.dashboard import in_month, months, spending

# 奶茶店：常见品牌 + 「茶」字（本地小店常叫「XX 茶」，比如「爷爷不泡茶」）；排除茶叶这类不是饮品的
MILK_TEA_WORDS = ["奶茶", "蜜雪", "喜茶", "古茗", "茶百道", "霸王茶姬", "一点点", "CoCo", "书亦", "沪上阿姨",
                  "奈雪", "茶姬", "柠檬水", "茶"]
NOT_DRINKS = ["茶叶", "茶几", "茶具", "茶杯"]
DRINK_CATEGORIES = {"零食饮品", "餐饮"}
PRIVATE_CATEGORIES = {"社交"}            # 转账、红包：「商家」其实是人，不当成「常去的店」


DELIVERY_PLATFORMS = {"饿了么", "美团", "淘宝闪购", "美团外卖"}


def _shop_name(row) -> str:
    """外卖订单的「商家」是平台（饿了么），真正的店名写在商品里（「爷爷不泡茶XX店外卖订单」）。"""
    item = str(row["item"] or "")
    if row["counterparty"] in DELIVERY_PLATFORMS and item and item != "/":
        name = item.split("外卖订单")[0].split("订单")[0].replace(f"{row['counterparty']}", "").strip("-（( ")
        return (name[:10] + "…" if len(name) > 10 else name) or row["counterparty"]
    return row["counterparty"]


def latest_month(df: pd.DataFrame) -> str:
    return months(df)[-1]


def _spend(df: pd.DataFrame, month: str) -> pd.DataFrame:
    return spending(in_month(df, month))


def _text(rows: pd.DataFrame) -> pd.Series:
    return (rows["counterparty"].astype(str) + " " + rows["item"].astype(str)).str.lower()


def milk_tea(df: pd.DataFrame, month: str) -> dict:
    """这个月奶茶花了多少。"""
    s = _spend(df, month)
    s = s[s["category"].isin(DRINK_CATEGORIES)]
    text = _text(s)
    hit = pd.Series(False, index=s.index)
    for word in MILK_TEA_WORDS:
        hit |= text.str.contains(word.lower(), regex=False)
    for word in NOT_DRINKS:
        hit &= ~text.str.contains(word, regex=False)
    rows = s[hit]
    total, count = float(rows["amount"].sum()), len(rows)
    shops = (rows.assign(shop=rows.apply(_shop_name, axis=1)).groupby("shop")["amount"]
             .agg(["count", "sum"]).sort_values("sum", ascending=False))
    return {
        "title": "原来，奶茶是这样攒起来的" if count else "这个月没喝奶茶，真能忍",
        "amount": round(total, 2),
        "note": f"{count} 笔，每笔平均 {total / count:.2f} 元。" if count else "也许是在别的地方解了馋？",
        "items": [(shop, f"{int(r['count'])} 笔 · {r['sum']:.2f} 元") for shop, r in shops.head(3).iterrows()],
        "items_label": "支出前三家" if len(shops) > 3 else "每家店",
        "rest": _rest(shops.iloc[3:], "家店"),
        "rows": rows,
    }


def favorite_shop(df: pd.DataFrame, month: str) -> dict:
    """这个月去得最多的店（按次数，不含转账红包）。"""
    s = _spend(df, month)
    s = s[~s["category"].isin(PRIVATE_CATEGORIES)]
    if s.empty:
        return {"title": "这个月还没有消费记录", "amount": 0.0, "note": "", "items": [], "items_label": "",
                "rest": None, "rows": s}
    visits = s.groupby("counterparty")["amount"].agg(["count", "sum"]).sort_values(["count", "sum"], ascending=False)
    top, r = visits.index[0], visits.iloc[0]
    rows = s[s["counterparty"] == top]
    others = visits.iloc[1:4]
    return {
        "title": f"你最常去的是「{top}」",
        "amount": round(float(r["sum"]), 2),
        "note": f"去了 {int(r['count'])} 次，平均每次 {r['sum'] / r['count']:.2f} 元。熟悉的小店，也是生活的固定坐标。",
        "items": [(shop, f"{int(v['count'])} 次 · {v['sum']:.2f} 元") for shop, v in others.iterrows()],
        "items_label": "接下来常去的（按次数）" if len(others) else "",
        "rest": None,                   # 大金额只算最常去的那家，下面列的是别的店，不用凑合计
        "rows": rows,
    }


def _rest(shops: pd.DataFrame, unit: str) -> tuple[str, str] | None:
    """没列出来的店合在一行：（「其他 2 家店」, 「3 笔 · 25.00 元」）。"""
    if shops.empty:
        return None
    return f"其他 {len(shops)} {unit}", f"{int(shops['count'].sum())} 笔 · {shops['sum'].sum():.2f} 元"


def biggest_day(df: pd.DataFrame, month: str) -> dict:
    """这个月花得最多的一天，都花在了哪。"""
    s = _spend(df, month)
    if s.empty:
        return {"title": "这个月还没有消费记录", "amount": 0.0, "note": "", "items": [], "items_label": "",
                "rest": None, "rows": s}
    by_day = s.groupby("date")["amount"].sum()
    day = by_day.idxmax()
    rows = s[s["date"] == day].sort_values("amount", ascending=False)
    weekday = "一二三四五六日"[day.day_of_week]
    return {
        "title": f"{day:%m月%d日}（周{weekday}），花得最多的一天",
        "amount": round(float(by_day.max()), 2),
        "note": f"这一天有 {len(rows)} 笔消费。",
        "items": [(r.counterparty, f"{r.amount:.2f} 元 · {r.category}") for r in rows.head(3).itertuples()],
        "items_label": "金额最大的三笔" if len(rows) > 3 else "这天的每一笔",
        "rest": (f"其他 {len(rows) - 3} 笔", f"{rows['amount'].iloc[3:].sum():.2f} 元") if len(rows) > 3 else None,
        "rows": rows,
    }


def discoveries(df: pd.DataFrame) -> list[dict]:
    """看板顶部的「发现」：每条都有依据、都能点开看是哪几笔。第一条是最重要的，单独突出显示。

    每条：icon（图标）、text（一句话）、rows（相关的交易，可能为空）。
    """
    from core.dashboard import FLEX, by_category, daily, kpis   # 放在这里，避免和 dashboard 互相引用

    s = spending(df)
    k = kpis(df)
    if s.empty or k["支出"] <= 0:
        return []
    found = []

    cats = by_category(df)
    top = cats.iloc[0]
    found.append({"icon": ":material/pie_chart:", "rows": s[s["category"] == top["category"]],
                  "text": f"钱最多花在「{top['category']}」：{top['amount']:,.0f} 元，占 {top['amount'] / k['支出']:.0%}"})

    flex_rows = s[s["type"] == FLEX]
    flex_names = "、".join(cats.loc[cats["type"] == FLEX, "category"].head(3))
    found.append({"icon": ":material/local_cafe:", "rows": flex_rows,
                  "text": f"自己选择花的部分（{flex_names}…）占 {k['弹性占比']:.0%}"})

    d = daily(df)
    peak = d.loc[d["amount"].idxmax()]
    peak_rows = s[s["date"] == peak["date"]]
    main_cat = peak_rows.groupby("category")["amount"].sum().idxmax()
    found.append({"icon": ":material/event:", "rows": peak_rows,
                  "text": f"花得最多的是 {peak['date']:%m月%d日}：{peak['amount']:,.0f} 元，主要在「{main_cat}」"})

    shop = _favorite_overall(s)        # 看板选了哪段时间，就看这段时间里最常去的店
    if shop:
        found.append(shop)

    # 周末 vs 工作日：差别明显（多 / 少 20% 以上）才说
    from core.dashboard import by_day_type
    from core.daytype import WEEKEND, WORKDAY, day_types
    stats = by_day_type(df).set_index("day_type")
    if {WORKDAY, WEEKEND} <= set(stats.index) and stats.loc[WORKDAY, "daily"] > 0:
        ratio = stats.loc[WEEKEND, "daily"] / stats.loc[WORKDAY, "daily"]
        if ratio >= 1.2 or ratio <= 0.8:
            words = f"是工作日的 {ratio:.1f} 倍" if ratio >= 1.2 else f"只有工作日的 {ratio:.0%}"
            found.append({"icon": ":material/weekend:", "rows": s[day_types(s["date"]) == WEEKEND],
                          "text": f"周末平均每天花 {stats.loc[WEEKEND, 'daily']:,.0f} 元，{words}"})

    no_spend = int((d["amount"] <= 0).sum())
    if no_spend:
        found.append({"icon": ":material/sentiment_satisfied:", "rows": s.iloc[0:0],
                      "text": f"有 {no_spend} 天一分钱没花"})
    return found


def _favorite_overall(s: pd.DataFrame) -> dict | None:
    s = s[~s["category"].isin(PRIVATE_CATEGORIES)]
    if s.empty:
        return None
    visits = s.groupby("counterparty")["amount"].agg(["count", "sum"]).sort_values(["count", "sum"], ascending=False)
    top, r = visits.index[0], visits.iloc[0]
    return {"icon": ":material/storefront:", "rows": s[s["counterparty"] == top],
            "text": f"最常去「{top}」：{int(r['count'])} 次，一共 {r['sum']:,.0f} 元"}


QUESTIONS = {
    "这个月，奶茶喝了多少钱？": milk_tea,
    "我最常光顾的是哪家店？": favorite_shop,
    "哪一天花得最多？": biggest_day,
}
