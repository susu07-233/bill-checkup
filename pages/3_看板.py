"""看板页：一屏看懂钱花在哪。重点是「必要 / 弹性」（产品决策 Q13）。

颜色：必要 = 蓝、弹性 = 橙、其他 = 灰（用 dataviz 规范的默认配色，已用校验脚本检查过色盲可分辨）；
深色模式换成同色系的深色版本。每张图都有鼠标悬停提示。
"""

import altair as alt
import pandas as pd
import streamlit as st

from app_state import load_files
from core.dashboard import (
    FLEX,
    NEED,
    OTHER,
    TYPE_ORDER,
    by_category,
    daily,
    insights,
    kpis,
    monthly_by_type,
    months,
    top_merchants,
)
from core.demo import demo_files
from core.money import yuan

st.set_page_config(page_title="看板 · 账单体检", page_icon="📊", layout="wide")
st.title("📊 消费看板")

df = st.session_state.get("transactions")
if df is None or df.empty:
    st.info("还没有导入数据。在左侧点「导入」上传账单，或者直接用示例账单看看效果。")
    if st.button("用示例账单试试", icon=":material/science:"):
        load_files(demo_files())
        st.rerun()
    st.stop()


# ---------- 配色（浅色 / 深色） ----------
DARK = getattr(st.context.theme, "type", "light") == "dark"
TYPE_COLORS = {NEED: "#3987e5" if DARK else "#2a78d6", FLEX: "#d95926" if DARK else "#eb6834", OTHER: "#898781"}
# 消费日历：一个色相（蓝）从浅到深；没花钱的日子用中性灰，不参与色阶
HEAT = ["#184f95", "#2a78d6", "#6da7ec", "#b7d3f6"] if DARK else ["#cde2fb", "#86b6ef", "#3987e5", "#184f95"]
EMPTY_DAY = "#2c2c2a" if DARK else "#f0efec"
INK, MUTED, GRID = ("#f0efec", "#898781", "#2c2c2a") if DARK else ("#0b0b0b", "#898781", "#e1e0d9")
type_scale = alt.Scale(domain=TYPE_ORDER, range=[TYPE_COLORS[t] for t in TYPE_ORDER])
type_legend = alt.Legend(title=None, orient="top", labelColor=INK)


def style(chart: alt.Chart) -> alt.Chart:
    """统一的轴、网格样式：网格和轴线淡一些，让数据本身更显眼。"""
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID, domainColor=GRID,
                            tickColor=GRID, labelFontSize=12, titleFontWeight="normal")
            .configure_legend(labelFontSize=12))


# ---------- 时间范围 ----------
all_months = months(df)
period = st.selectbox("时间范围", ["全部", *reversed(all_months)], width=200,
                      format_func=lambda m: m if m == "全部" else f"{m[:4]} 年 {int(m[5:])} 月")
view = df if period == "全部" else df[df["time"].dt.strftime("%Y-%m") == period]
k = kpis(view)


# ---------- 关键数字 ----------
with st.container(horizontal=True):
    st.metric("总支出", yuan(k["支出"]), border=True)
    st.metric("日均", yuan(k["日均"]), border=True, help=f"总支出 ÷ {k['天数']} 天")
    st.metric("其中吃喝", yuan(k["吃喝"]), border=True, help="餐饮 + 零食饮品")
    st.metric("弹性支出占比", f"{k['弹性占比']:.0%}", border=True,
              help="弹性 = 零食饮品、购物、娱乐、社交，是「可以省」的钱；"
                   "必要 = 餐饮、交通、生活服务、医疗、学习")

with st.container(border=True):
    st.markdown("**:material/lightbulb: 小结**")
    for line in insights(view):
        st.markdown(f"- {line}")


# ---------- 必要 vs 弹性 ----------
left, right = st.columns([2, 3])
with left, st.container(border=True, height="stretch"):
    st.markdown("**必要 vs 弹性**")
    shares = pd.DataFrame({"type": TYPE_ORDER, "amount": [max(k[t], 0) for t in TYPE_ORDER]})
    shares = shares[shares["amount"] > 0]
    shares["share"] = shares["amount"] / shares["amount"].sum()
    shares["label"] = shares.apply(lambda r: f"{r['type']} {r['share']:.0%}", axis=1)
    shares["tip"] = shares["amount"].map(yuan)
    base = alt.Chart(shares).encode(
        x=alt.X("amount:Q", stack="normalize", axis=None),
        order=alt.Order("sort_key:Q"),
        tooltip=[alt.Tooltip("type:N", title="类型"), alt.Tooltip("tip:N", title="金额"),
                 alt.Tooltip("share:Q", title="占比", format=".0%")],
    ).transform_calculate(sort_key=f"indexof({TYPE_ORDER}, datum.type)")
    bar = base.mark_bar(height=44, cornerRadius=4, stroke="white" if not DARK else "#1a1a19", strokeWidth=2).encode(
        color=alt.Color("type:N", scale=type_scale, legend=None))
    labels = base.mark_text(align="center", color="white", fontSize=13, fontWeight="bold").encode(
        x=alt.X("mid:Q", axis=None), text="label:N",
    ).transform_stack(stack="amount", as_=["lo", "hi"], groupby=[], sort=[alt.SortField("sort_key")],
                      offset="normalize").transform_calculate(mid="(datum.lo + datum.hi) / 2")
    st.altair_chart(style((bar + labels).properties(height=60)), width="stretch",
                    alt=f"必要支出占 {k[NEED] / k['支出']:.0%}，弹性支出占 {k['弹性占比']:.0%}" if k["支出"] else "没有支出")
    for t in (NEED, FLEX):
        cats = by_category(view)
        cats = cats[cats["type"] == t]
        detail = "、".join(f"{c} {yuan(a, 0)}" for c, a in zip(cats["category"], cats["amount"]))
        st.markdown(f":{'blue' if t == NEED else 'orange'}[**{t} {yuan(k[t])}**]  \n{detail or '—'}")
    if k[OTHER]:
        st.caption(f"其他 / 未分类 {yuan(k[OTHER])}，没有算进必要或弹性。")

with right, st.container(border=True, height="stretch"):
    st.markdown("**每月支出**")
    monthly = monthly_by_type(df if period == "全部" else df[df["time"].dt.strftime("%Y-%m").isin([period])])
    if monthly["month"].nunique() < 2 and period == "全部":
        st.caption("只有一个月的数据，导入更多月份后就能看到变化趋势。")
    monthly["月份"] = monthly["month"].map(lambda m: f"{int(m[5:])} 月")
    monthly["tip"] = monthly["amount"].map(yuan)
    chart = alt.Chart(monthly).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28,
                                        stroke="white" if not DARK else "#1a1a19", strokeWidth=2).encode(
        x=alt.X("月份:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("sum(amount):Q", title="元", axis=alt.Axis(format=",.0f", tickCount=5)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend),
        order=alt.Order("sort_key:Q"),
        tooltip=[alt.Tooltip("月份:N"), alt.Tooltip("type:N", title="类型"), alt.Tooltip("tip:N", title="金额")],
    ).transform_calculate(sort_key=f"indexof({TYPE_ORDER}, datum.type)").properties(height=280)
    st.altair_chart(style(chart), width="stretch", alt="每月支出，按必要、弹性、其他分段")


# ---------- 分类 & 商家 ----------
left, right = st.columns(2)
with left, st.container(border=True, height="stretch"):
    st.markdown("**各分类支出**")
    cats = by_category(view)
    cats = cats[cats["amount"] > 0]
    cats["tip"] = cats["amount"].map(yuan)
    chart = alt.Chart(cats).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("category:N", sort="-x", title=None, scale=alt.Scale(paddingInner=0.35)),
        x=alt.X("amount:Q", title="元", axis=alt.Axis(format=",.0f", tickCount=4)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend),
        tooltip=[alt.Tooltip("category:N", title="分类"), alt.Tooltip("type:N", title="类型"),
                 alt.Tooltip("tip:N", title="金额"), alt.Tooltip("count:Q", title="笔数")],
    ).properties(height=alt.Step(28))           # 每一行固定 28 像素高，分类多了图就自动变高
    st.altair_chart(style(chart), width="stretch", alt="各分类支出，从多到少，颜色表示必要或弹性")

with right, st.container(border=True, height="stretch"):
    st.markdown("**花钱最多的 10 个商家**")
    top = top_merchants(view, 10)
    top["tip"] = top["amount"].map(yuan)
    chart = alt.Chart(top).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("counterparty:N", sort="-x", title=None, axis=alt.Axis(labelLimit=150),
                scale=alt.Scale(paddingInner=0.35)),
        x=alt.X("amount:Q", title="元", axis=alt.Axis(format=",.0f", tickCount=4)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend),
        tooltip=[alt.Tooltip("counterparty:N", title="商家"), alt.Tooltip("tip:N", title="金额"),
                 alt.Tooltip("count:Q", title="笔数")],
    ).properties(height=alt.Step(28))
    st.altair_chart(style(chart), width="stretch", alt="花钱最多的 10 个商家")


# ---------- 消费日历 ----------
with st.container(border=True):
    st.markdown("**消费日历**")
    cal = daily(view)
    cal["星期"] = cal["weekday"].map(lambda d: "一二三四五六日"[d]).radd("周")
    cal["周"] = cal["week"].dt.strftime("%m/%d")              # 每一周一列，用这周周一的日期做标签
    cal["tip"] = cal["amount"].map(yuan)
    cap = max(float(cal["amount"].quantile(0.95)), 1.0)       # 极端大额不把颜色拉爆
    chart = alt.Chart(cal).mark_rect(cornerRadius=3, stroke="white" if not DARK else "#1a1a19", strokeWidth=2).encode(
        x=alt.X("周:O", sort=sorted(cal["周"].unique(), key=lambda s: cal.loc[cal["周"] == s, "week"].iloc[0]),
                title=None, axis=alt.Axis(labelAngle=-45 if cal["周"].nunique() > 12 else 0, labelOverlap=True)),
        y=alt.Y("星期:N", sort=[f"周{d}" for d in "一二三四五六日"], title=None),
        color=alt.condition(
            "datum.amount <= 0",
            alt.value(EMPTY_DAY),
            alt.Color("amount:Q", scale=alt.Scale(domain=[0, cap], range=HEAT, clamp=True, interpolate="rgb"),
                      legend=alt.Legend(title="元", orient="right", format=",.0f")),
        ),
        tooltip=[alt.Tooltip("date:T", title="日期", format="%Y-%m-%d"), alt.Tooltip("星期:N"),
                 alt.Tooltip("tip:N", title="支出")],
    ).properties(height=210)
    st.altair_chart(style(chart), width="stretch", alt="每天的支出，颜色越深花得越多")
    st.caption("蓝色越深花得越多，灰色是一分钱没花的日子；横轴是每周的周一。鼠标移到格子上可以看具体金额。")
