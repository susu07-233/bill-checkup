"""AI 月报：程序先算好统计数字，再请 AI 根据这些数字写点评和省钱建议。

为什么这样分工：AI 算数容易出错，程序算数不会错；AI 擅长把数字写成好懂的话、给建议。

隐私：发给 AI 的只有汇总数字、分类名、花钱最多的几个商家名。
      「社交」（转账、红包、AA）的对方名字不发，朋友的名字不会外传；不发任何一笔交易的明细。
"""

import json

import pandas as pd

from core.ai_classify import AIError
from core.dashboard import (
    FLEX,
    NEED,
    OTHER,
    by_category,
    daily,
    in_month,
    kpis,
    previous_month,
    spending,
    top_merchants,
)

PRIVATE_CATEGORIES = {"社交"}     # 这些分类的商家其实是人名，不发给 AI

REPORT_PROMPT = """你是一位真诚、直接、懂大学生的理财伙伴。下面是一位大学生某段时间的消费统计（JSON），
请写一份简短的中文月报，用 Markdown，严格按这个结构：

**一句话总结**：一句话说清这段时间花钱的整体情况。

**花钱亮点**：2–3 条，挑最值得注意的事实（比如哪类花得最多、和上个月比的变化）。

**需要注意**：1–2 条，指出可能的问题（比如弹性支出偏高、某一天花得特别多）。

**省钱建议**：2–3 条，要具体、能做到，最好带估算（比如「零食饮品每周少花 30 元，一个月能省约 120 元」）。

要求：
1. 只能使用数据里给出的数字，不要编造数据里没有的数字；估算省钱时要写清楚是怎么算的。
2. 金额写成「123.45 元」，不要用 ¥。
3. 「必要」= 餐饮、交通、生活服务、医疗、学习；「弹性」= 零食饮品、购物、娱乐、社交，是可以省的钱。
4. 语气友好但不说教，不要用「亲」「宝」这类称呼；总字数不超过 350 字。"""


def report_facts(df: pd.DataFrame, month: str | None = None) -> dict:
    """算出月报需要的统计数字。month 为空表示全部时间。"""
    view = in_month(df, month) if month else df
    k = kpis(view)
    spend = spending(view)
    cats = by_category(view)
    public = view[~view["category"].isin(PRIVATE_CATEGORIES)]
    merchants = top_merchants(public, 8)
    d = daily(view)

    facts = {
        "时间范围": f"{view['time'].min():%Y-%m-%d} 至 {view['time'].max():%Y-%m-%d}（{k['天数']} 天）",
        "总支出": k["支出"],
        "日均支出": k["日均"],
        "吃喝（餐饮+零食饮品）": k["吃喝"],
        "必要支出": k[NEED],
        "弹性支出": k[FLEX],
        "其他或未分类": k[OTHER],
        "弹性支出占比": f"{k['弹性占比']:.0%}",
        "各分类": [{"分类": r.category, "金额": r.amount, "笔数": int(r.count), "类型": r.type}
                for r in cats.itertuples()],
        "花钱最多的商家（不含转账红包）": [
            {"商家": r.counterparty, "金额": r.amount, "笔数": int(r.count)} for r in merchants.itertuples()],
        "支出笔数": int(len(spend)),
    }
    if not d.empty and d["amount"].max() > 0:
        peak = d.loc[d["amount"].idxmax()]
        day_spend = spend[spend["date"] == peak["date"]]
        facts["花得最多的一天"] = {
            "日期": f"{peak['date']:%m月%d日}", "金额": float(peak["amount"]),
            "主要分类": day_spend.groupby("category")["amount"].sum().idxmax(),
        }
        facts["没花钱的天数"] = int((d["amount"] <= 0).sum())
        weekday = d.groupby("weekday")["amount"].mean()
        facts["平均花得最多的是周几"] = "周" + "一二三四五六日"[int(weekday.idxmax())]

    prev = previous_month(df, month) if month else None
    if prev:
        pk = kpis(in_month(df, prev))
        facts["上个月"] = {
            "月份": prev, "总支出": pk["支出"], "吃喝": pk["吃喝"], "弹性支出占比": f"{pk['弹性占比']:.0%}",
            "各分类": {r.category: r.amount for r in by_category(in_month(df, prev)).itertuples()},
        }
    return facts


def generate_report(facts: dict, client, model: str) -> str:
    """请 AI 写月报，返回 Markdown 文本。"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": REPORT_PROMPT},
                      {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()
    except Exception as e:
        raise AIError(f"生成月报失败：{e}") from e
    return text.replace("¥", "")
