"""看板页：一屏看懂钱花在哪。重点是「必要 / 弹性」（产品决策 Q13）。

颜色：必要 = 蓝、弹性 = 橙、其他 = 灰（dataviz 规范的默认配色，已用校验脚本检查过色盲可分辨）；
深色模式换成同色系的深色版本。每张图都有鼠标悬停提示。
"""

import altair as alt
import pandas as pd
import streamlit as st

from app_state import require_data
from core.dashboard import (
    FLEX,
    NEED,
    OTHER,
    TYPE_ORDER,
    by_category,
    daily,
    in_month,
    insights,
    kpis,
    monthly_by_type,
    months,
    previous_month,
    top_merchants,
    weekly_by_type,
)
from core.money import yuan
from core.schema import SPENDING_TYPES

st.set_page_config(page_title="看板 · 账单体检", page_icon="📊", layout="wide")
st.title("📊 消费看板")
df = require_data()


# ---------- 配色（浅色 / 深色） ----------
DARK = getattr(st.context.theme, "type", "light") == "dark"
TYPE_COLORS = {NEED: "#3987e5" if DARK else "#2a78d6", FLEX: "#d95926" if DARK else "#eb6834", OTHER: "#898781"}
# 消费日历：一个色相（蓝）从浅到深；没花钱的日子用中性灰，不参与色阶
HEAT = ["#184f95", "#2a78d6", "#6da7ec", "#b7d3f6"] if DARK else ["#cde2fb", "#86b6ef", "#3987e5", "#184f95"]
EMPTY_DAY = "#2c2c2a" if DARK else "#f0efec"
INK, MUTED, GRID = ("#f0efec", "#898781", "#2c2c2a") if DARK else ("#0b0b0b", "#898781", "#e1e0d9")
GAP = "#1a1a19" if DARK else "white"          # 相邻色块之间 2px 的缝
type_scale = alt.Scale(domain=TYPE_ORDER, range=[TYPE_COLORS[t] for t in TYPE_ORDER])
type_legend = alt.Legend(title=None, orient="top", labelColor=INK)
type_order = alt.Order("sort_key:Q")
SORT_KEY = f"indexof({TYPE_ORDER}, datum.type)"   # 堆叠顺序固定：必要在下、弹性在中、其他在上


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
view = df if period == "全部" else in_month(df, period)
k = kpis(view)

# 选了某个月、并且账单里有上个月：数字卡片显示「比上月」
prev = previous_month(df, period) if period != "全部" else None
pk = kpis(in_month(df, prev)) if prev else None


def delta(key: str, percent_points: bool = False):
    if pk is None:
        return None
    if percent_points:
        return f"{(k[key] - pk[key]) * 100:+.0f} 个百分点"
    return f"{k[key] - pk[key]:+,.2f} 元"


# ---------- 关键数字 ----------
with st.container(horizontal=True):
    kw = dict(border=True, delta_color="inverse", delta_description=f"比 {int(prev[5:])} 月" if prev else None)
    st.metric("总支出", yuan(k["支出"]), delta("支出"), **kw)
    st.metric("日均", yuan(k["日均"]), delta("日均"), help=f"总支出 ÷ {k['天数']} 天", **kw)
    st.metric("其中吃喝", yuan(k["吃喝"]), delta("吃喝"), help="餐饮 + 零食饮品", **kw)
    st.metric("弹性支出占比", f"{k['弹性占比']:.0%}", delta("弹性占比", percent_points=True),
              help="弹性 = 零食饮品、购物、娱乐、社交，是「可以省」的钱；必要 = 餐饮、交通、生活服务、医疗、学习",
              **kw)

if period != "全部" and prev is None and any(m < period for m in all_months):
    st.caption("上个月的账单不到 20 天，不做「比上月」，免得得出误导的结论。")

if lines := insights(view):
    with st.container(border=True):
        st.markdown("**:material/lightbulb: 小结**\n\n" + "\n".join(f"- {line}" for line in lines))


# ---------- 必要 vs 弹性 ----------
left, right = st.columns([2, 3])
with left, st.container(border=True, height="stretch"):
    st.markdown("**必要 vs 弹性**")
    shares = pd.DataFrame({"type": TYPE_ORDER, "amount": [max(k[t], 0) for t in TYPE_ORDER]})
    shares = shares[shares["amount"] > 0]
    shares["share"] = shares["amount"] / shares["amount"].sum()
    # 色块宽：写「必要 44%」；色块窄：只写「12%」（类型看颜色和下面的文字）；太窄（< 8%）才不写
    shares["label"] = shares.apply(
        lambda r: f"{r['type']} {r['share']:.0%}" if r["share"] >= 0.22
        else f"{r['share']:.0%}" if r["share"] >= 0.08 else "", axis=1)
    shares["tip"] = shares["amount"].map(yuan)
    base = alt.Chart(shares).encode(
        x=alt.X("amount:Q", stack="normalize", axis=None), order=type_order,
        tooltip=[alt.Tooltip("type:N", title="类型"), alt.Tooltip("tip:N", title="金额"),
                 alt.Tooltip("share:Q", title="占比", format=".0%")],
    ).transform_calculate(sort_key=SORT_KEY)
    bar = base.mark_bar(height=44, cornerRadius=4, stroke=GAP, strokeWidth=2).encode(
        color=alt.Color("type:N", scale=type_scale, legend=None))
    labels = base.mark_text(align="center", color="white", fontSize=13, fontWeight="bold").encode(
        x=alt.X("mid:Q", axis=None), text="label:N",
    ).transform_stack(stack="amount", as_=["lo", "hi"], groupby=[], sort=[alt.SortField("sort_key")],
                      offset="normalize").transform_calculate(mid="(datum.lo + datum.hi) / 2")
    st.altair_chart(style((bar + labels).properties(height=60)), width="stretch",
                    alt=f"必要支出占 {k[NEED] / k['支出']:.0%}，弹性支出占 {k['弹性占比']:.0%}" if k["支出"] else "没有支出")
    # 各分类具体多少钱在下面「各分类支出」图里，这里只列包含哪些分类，避免重复
    for t, color in ((NEED, "blue"), (FLEX, "orange")):
        share = k[t] / k["支出"] if k["支出"] else 0
        st.markdown(f":{color}[**{t} {yuan(k[t])}**]　{share:.0%}  \n"
                    f":gray[{'、'.join(SPENDING_TYPES[t])}]")
    if k[OTHER]:
        st.caption(f"其他 / 未分类 {yuan(k[OTHER])}（{k[OTHER] / k['支出']:.0%}），不算必要或弹性。")

with right, st.container(border=True, height="stretch"):
    st.markdown("**每月支出**")
    monthly = monthly_by_type(view)
    if monthly["month"].nunique() < 2:
        st.caption("只有一个月的数据，导入更多月份后就能看到变化。")
    monthly["月份"] = monthly["month"].map(lambda m: f"{int(m[5:])} 月")
    monthly["tip"] = monthly["amount"].map(yuan)
    chart = alt.Chart(monthly).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28,
                                        stroke=GAP, strokeWidth=2).encode(
        x=alt.X("月份:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("sum(amount):Q", title="元", axis=alt.Axis(format=",.0f", tickCount=5)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend), order=type_order,
        tooltip=[alt.Tooltip("月份:N"), alt.Tooltip("type:N", title="类型"), alt.Tooltip("tip:N", title="金额")],
    ).transform_calculate(sort_key=SORT_KEY).properties(height=280)
    st.altair_chart(style(chart), width="stretch", alt="每月支出，按必要、弹性、其他分段")


# ---------- 每周支出（苏宇晨的需求：按周看花费和占比；按天太碎，每天的情况看下面的日历） ----------
with st.container(border=True):
    head, switch = st.columns([3, 2], vertical_alignment="center")
    head.markdown("**每周支出**")
    show = switch.segmented_control("显示", ["金额", "占比"], default="金额", required=True,
                                    key="weekly_mode", label_visibility="collapsed", width="content")
    weeks = weekly_by_type(view)
    weeks["tip"] = weeks["amount"].map(yuan)
    as_share = show == "占比"
    order = list(dict.fromkeys(weeks.sort_values("week")["label"]))
    chart = alt.Chart(weeks).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, stroke=GAP, strokeWidth=2).encode(
        x=alt.X("label:N", sort=order, title=None,
                axis=alt.Axis(labelAngle=0 if len(order) <= 8 else -45, labelOverlap=True)),
        y=alt.Y("amount:Q", stack="normalize" if as_share else True, title=None if as_share else "元",
                axis=alt.Axis(format=".0%" if as_share else ",.0f", tickCount=5)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend), order=type_order,
        tooltip=[alt.Tooltip("label:N", title="这一周"), alt.Tooltip("type:N", title="类型"),
                 alt.Tooltip("tip:N", title="金额"), alt.Tooltip("share:Q", title="占这一周", format=".0%")],
    ).transform_calculate(sort_key=SORT_KEY).properties(height=260)
    st.altair_chart(style(chart), width="stretch",
                    alt="每周的支出，按必要、弹性、其他分段" + ("，显示每周的占比" if as_share else ""))
    st.caption("每根柱子是一周（周一到周日），第一周和最后一周可能不满 7 天。切到「占比」看每周必要和弹性各占多少。")


# ---------- 分类 & 商家 ----------
def ranking(data: pd.DataFrame, field: str, name: str, alt_text: str):
    """横向条形图：从多到少，颜色表示必要 / 弹性。每行固定 28 像素高，项目多了图就自动变高。"""
    data = data[data["amount"] > 0].assign(tip=lambda d: d["amount"].map(yuan))
    chart = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{field}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=150),
                scale=alt.Scale(paddingInner=0.35)),
        x=alt.X("amount:Q", title="元", axis=alt.Axis(format=",.0f", tickCount=4)),
        color=alt.Color("type:N", scale=type_scale, legend=type_legend),
        tooltip=[alt.Tooltip(f"{field}:N", title=name), alt.Tooltip("type:N", title="类型"),
                 alt.Tooltip("tip:N", title="金额"), alt.Tooltip("count:Q", title="笔数")],
    ).properties(height=alt.Step(28))
    st.altair_chart(style(chart), width="stretch", alt=alt_text)


left, right = st.columns(2)
with left, st.container(border=True, height="stretch"):
    st.markdown("**各分类支出**")
    ranking(by_category(view), "category", "分类", "各分类支出，从多到少，颜色表示必要或弹性")
with right, st.container(border=True, height="stretch"):
    st.markdown("**花钱最多的 10 个商家**")
    ranking(top_merchants(view, 10), "counterparty", "商家", "花钱最多的 10 个商家")


# ---------- 消费日历 ----------
with st.container(border=True):
    st.markdown("**消费日历**")
    cal = daily(view)
    cal["星期"] = cal["weekday"].map(lambda d: "一二三四五六日"[d]).radd("周")
    cal["周"] = cal["week"].dt.strftime("%m/%d")              # 每一周一列，用这周周一的日期做标签
    cal["tip"] = cal["amount"].map(yuan)
    weeks = sorted(cal["周"].unique(), key=lambda s: cal.loc[cal["周"] == s, "week"].iloc[0])
    cap = max(float(cal["amount"].quantile(0.95)), 1.0)       # 极端大额不把颜色拉爆
    few_weeks = len(weeks) <= 16                              # 周数少时格子固定大小，不拉成长条
    chart = alt.Chart(cal).mark_rect(cornerRadius=3, stroke=GAP, strokeWidth=2).encode(
        x=alt.X("周:O", sort=weeks, title=None,
                axis=alt.Axis(labelAngle=0 if few_weeks else -45, labelOverlap=True)),
        y=alt.Y("星期:N", sort=[f"周{d}" for d in "一二三四五六日"], title=None),
        color=alt.condition(
            "datum.amount <= 0",
            alt.value(EMPTY_DAY),
            alt.Color("amount:Q", scale=alt.Scale(domain=[0, cap], range=HEAT, clamp=True, interpolate="rgb"),
                      legend=alt.Legend(title="元", orient="right", format=",.0f")),
        ),
        tooltip=[alt.Tooltip("date:T", title="日期", format="%Y-%m-%d"), alt.Tooltip("星期:N"),
                 alt.Tooltip("tip:N", title="支出")],
    ).properties(height=alt.Step(26), **({"width": alt.Step(44)} if few_weeks else {}))
    st.altair_chart(style(chart), width="content" if few_weeks else "stretch", alt="每天的支出，颜色越深花得越多")
    st.caption("颜色越深花得越多，灰色是没花钱的日子，能看出一周里哪几天最费钱。")
