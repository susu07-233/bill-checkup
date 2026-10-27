"""问一问：用大白话问账单，比如「上个月奶茶花了多少？」

分两步：
  1. AI 把问题翻译成「查询条件」（时间、分类、关键词、要算什么）—— parse_question
  2. 程序按条件筛选、计算，写出答案 —— run_query
AI 不碰任何交易数据，也不负责算数，所以答案里的数字一定是对的；
页面会把「我理解的问题」显示出来，理解错了一眼就能看出。
"""

import json
from datetime import date

import pandas as pd

from core.ai_classify import AIError
from core.money import yuan
from core.schema import CATEGORIES, CATEGORY_GROUPS, SPENDING_TYPES

METRICS = {
    "sum": "合计金额",
    "count": "笔数",
    "list": "列出明细",
    "top_merchants": "花钱最多的商家",
    "by_category": "按分类汇总",
    "by_month": "按月汇总",
    "max": "最大的一笔",
    "avg_per_day": "日均",
}


def _prompt(today: date, data_start: date, data_end: date) -> str:
    groups = "；".join(f"「{g}」= {'、'.join(c)}" for g, c in {**CATEGORY_GROUPS, **SPENDING_TYPES}.items())
    return f"""你是记账软件的查询助手。用户会用中文问关于自己账单的问题，你要把问题翻译成查询条件（JSON），
由程序去计算。你看不到任何账单数据，不要自己回答问题。

今天是 {today:%Y-%m-%d}；账单的时间范围是 {data_start:%Y-%m-%d} 至 {data_end:%Y-%m-%d}。
支出分类只有这些：{"、".join(CATEGORIES)}。
大类：{groups}。

输出 JSON，字段：
- "start", "end"：日期范围 YYYY-MM-DD，包含两端；问题没提时间就用 null（表示全部时间）。
  「上个月」「这个月」「最近一周」等按今天计算。
- "direction"："支出" 或 "收入"，默认 "支出"。
- "categories"：分类列表（只能用上面的分类名），不限分类用 []。问大类时展开成它包含的分类。
- "keywords"：在商家名、商品名里搜索的关键词列表，满足任意一个即可，不限用 []。
  问具体东西时尽量列全常见写法和品牌，比如问奶茶：["奶茶","蜜雪","喜茶","古茗","茶百道","霸王茶姬","一点点","CoCo"]。
  有关键词时 categories 留空（同一家店可能被分到不同分类，加分类会漏掉），除非用户明确说了分类名。
- "metric"：要算什么，只能是 {list(METRICS)} 之一。
  sum=合计金额，count=笔数，list=列出明细，top_merchants=花钱最多的商家，by_category=按分类汇总，
  by_month=按月汇总，max=最大的一笔，avg_per_day=日均。
- "understanding"：用一句中文复述你理解的问题，比如「2026年9月，零食饮品里和奶茶有关的支出，合计多少」。
如果问题和账单无关、或者无法用这些条件表达，输出 {{"unsupported": true, "understanding": "原因"}}。
只输出 JSON。"""


def parse_question(question: str, client, model: str, today: date, data_start: date, data_end: date) -> dict:
    """请 AI 把问题翻译成查询条件，并检查一遍，不合法的部分改成默认值。"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _prompt(today, data_start, data_end)},
                      {"role": "user", "content": question}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        spec = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        raise AIError(f"AI 返回的格式不对：{e}") from e
    except Exception as e:
        raise AIError(f"调用 AI 失败：{e}") from e
    return validate(spec)


def validate(spec: dict) -> dict:
    """检查查询条件：日期能不能解析、分类在不在列表里、metric 合不合法。"""
    if spec.get("unsupported"):
        return {"unsupported": True, "understanding": str(spec.get("understanding") or "这个问题我没法用账单回答")}

    def to_date(value):
        try:
            return pd.Timestamp(value).date() if value else None
        except (ValueError, TypeError):
            return None

    return {
        "start": to_date(spec.get("start")),
        "end": to_date(spec.get("end")),
        "direction": spec.get("direction") if spec.get("direction") in ("支出", "收入") else "支出",
        "categories": [c for c in spec.get("categories") or [] if c in CATEGORIES],
        "keywords": [str(k).strip() for k in spec.get("keywords") or [] if str(k).strip()],
        "metric": spec.get("metric") if spec.get("metric") in METRICS else "sum",
        "understanding": str(spec.get("understanding") or ""),
    }


def select(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """按查询条件挑出交易。"""
    rows = df[df["direction"] == spec["direction"]]
    day = rows["time"].dt.date
    if spec["start"]:
        rows = rows[day >= spec["start"]]
        day = rows["time"].dt.date
    if spec["end"]:
        rows = rows[day <= spec["end"]]
    if spec["categories"]:
        rows = rows[rows["category"].isin(spec["categories"])]
    if spec["keywords"]:
        text = (rows["counterparty"].astype(str) + " " + rows["item"].astype(str)).str.lower()
        hit = pd.Series(False, index=rows.index)
        for word in spec["keywords"]:
            hit |= text.str.contains(word.lower(), regex=False)
        rows = rows[hit]
    return rows.sort_values("time", ascending=False)


def run_query(df: pd.DataFrame, spec: dict) -> tuple[str, pd.DataFrame | None, pd.DataFrame]:
    """执行查询。返回（答案文字, 汇总表或 None, 用到的交易）。"""
    if spec.get("unsupported"):
        return f"这个问题我回答不了：{spec['understanding']}", None, df.iloc[0:0]

    rows = select(df, spec)
    word = "花了" if spec["direction"] == "支出" else "收入"
    total = float(rows["amount"].sum())
    if rows.empty:
        hint = []
        data_start, data_end = df["time"].min().date(), df["time"].max().date()
        if (spec["start"] and spec["start"] < data_start) or (spec["end"] and spec["end"] > data_end):
            hint.append(f"账单只有 {data_start:%Y-%m-%d} 至 {data_end:%Y-%m-%d} 的数据")
        if spec["keywords"]:
            hint.append("可以换个说法，或者直接说商家名")
        return "没有找到符合条件的交易。" + ("（" + "；".join(hint) + "）" if hint else ""), None, rows

    metric = spec["metric"]
    if metric == "count":
        return f"一共 **{len(rows)} 笔**，合计 {yuan(total)}。", None, rows
    if metric == "max":
        top = rows.loc[rows["amount"].idxmax()]
        return (f"最大的一笔是 **{yuan(top['amount'])}**：{top['time']:%m月%d日} 在「{top['counterparty']}」"
                f"{('（' + str(top['item']) + '）') if str(top['item']).strip() else ''}。"), None, rows
    if metric == "avg_per_day":
        start = spec["start"] or df["time"].min().date()
        end = spec["end"] or df["time"].max().date()
        days = (end - start).days + 1
        return f"平均每天{word} **{yuan(total / days)}**（{days} 天合计 {yuan(total)}，{len(rows)} 笔）。", None, rows
    if metric in ("top_merchants", "by_category", "by_month"):
        key = {"top_merchants": "counterparty", "by_category": "category"}.get(metric)
        grouped = rows.assign(month=rows["time"].dt.strftime("%Y-%m")).groupby(key or "month")["amount"]
        table = grouped.agg(["sum", "count"]).round(2).rename(columns={"sum": "金额", "count": "笔数"})
        table = table.sort_index() if metric == "by_month" else table.sort_values("金额", ascending=False)
        if metric == "top_merchants":
            table = table.head(10)
        table.index.name = {"top_merchants": "商家", "by_category": "分类", "by_month": "月份"}[metric]
        first = table.index[0]
        lead = (f"最多的是「{first}」{yuan(table.iloc[0]['金额'])}。" if metric != "by_month"
                else f"共 {len(table)} 个月。")
        return f"合计 **{yuan(total)}**，{len(rows)} 笔；{lead}", table.reset_index(), rows
    # sum、list 都先给合计
    return f"一共{word} **{yuan(total)}**，{len(rows)} 笔。", None, rows
