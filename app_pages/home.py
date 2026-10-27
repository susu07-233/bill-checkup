"""首页：左边一句话说清楚这是什么、两个入口；右边用示例数据实时生成一个「迷你看板」，
让第一次来的人（比如面试官）不用点进去就知道能看到什么。"""

import altair as alt
import pandas as pd
import streamlit as st

from app_state import load_files
from core.classify import classify
from core.clean import clean
from core.dashboard import NEED, FLEX, TYPE_ORDER, kpis, monthly_by_type
from core.demo import demo_files
from core.money import yuan
from core.overrides import is_local
from core.parse import parse_bill


@st.cache_data(show_spinner=False)
def demo_preview() -> tuple[dict, pd.DataFrame]:
    """示例数据（小林半年）的关键数字和每月必要 / 弹性，首页预览用。只算一次。"""
    df = classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])
    return kpis(df), monthly_by_type(df)


left, right = st.columns([5, 4], gap="large", vertical_alignment="center")

with left:
    st.title("账单体检", anchor=False)
    st.markdown("### 导入微信、支付宝账单，看清钱花在哪、哪些钱可以省")
    privacy = "账单只在本地处理" if is_local() else "在线演示：账单不保存，关掉页面就清空"
    st.markdown(f":blue-badge[:material/lock: {privacy}] "
                ":blue-badge[:material/auto_awesome: 规则 + AI 自动分类] "
                ":blue-badge[:material/school: 为大学生设计]")
    st.space("small")
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("用示例账单试试", type="primary", icon=":material/play_arrow:",
                     help="虚构大学生「小林」半年的微信 + 支付宝账单，所有交易都是编的"):
            load_files(demo_files())
            st.switch_page("app_pages/dashboard.py")
        st.page_link("app_pages/import_bills.py", label="导入我的账单", icon=":material/upload_file:")
    if "transactions" in st.session_state:
        df = st.session_state["transactions"]
        st.caption(f"已导入 {len(df)} 笔交易（{df['time'].min():%Y-%m-%d} 至 {df['time'].max():%Y-%m-%d}），"
                   "可以直接去看板或流水。")

with right, st.container(border=True):
    k, monthly = demo_preview()
    st.caption(":material/visibility: 看板预览 · 示例数据（虚构的大学生小林，半年）")
    with st.container(horizontal=True):
        st.metric("半年总支出", yuan(k["支出"], 0))
        st.metric("弹性支出占比", f"{k['弹性占比']:.0%}", help="零食饮品、购物、娱乐、社交，是可以省的钱")
    blue, orange = "#2a78d6", "#eb6834"
    data = monthly[monthly["type"].isin([NEED, FLEX])].assign(月份=lambda d: d["month"].str[5:].astype(int).astype(str) + " 月")
    chart = alt.Chart(data).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=22).encode(
        x=alt.X("月份:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, domain=False, ticks=False)),
        y=alt.Y("sum(amount):Q", title=None, axis=None),
        color=alt.Color("type:N", scale=alt.Scale(domain=[NEED, FLEX], range=[blue, orange]),
                        legend=alt.Legend(title=None, orient="top")),
        order=alt.Order("sort_key:Q"),
        tooltip=[alt.Tooltip("月份:N"), alt.Tooltip("type:N", title="类型"),
                 alt.Tooltip("amount:Q", title="金额（元）", format=",.0f")],
    ).transform_calculate(sort_key=f"indexof({TYPE_ORDER}, datum.type)").properties(height=170)
    st.altair_chart(chart.configure_view(strokeWidth=0), width="stretch",
                    alt="示例数据每个月的必要和弹性支出")

st.space("medium")

STEPS = [
    (":material/upload_file:", "导入", "直接用微信、支付宝官方导出的账单，可以一次拖进多个文件。"),
    (":material/cleaning_services:", "自动整理",
     "去掉退款和关闭的交易，部分退款按实际花费算，跨月退款抵扣本月，重复导入自动去重。"),
    (":material/category:", "自动分类",
     "规则先分，认不出的交给 AI；在 100 笔真实交易上准确率 87%。分错了可以手动改，会记住。"),
    (":material/insights:", "看懂花销",
     "看板分「必要 / 弹性」，告诉你哪些钱可以省；AI 写月报，还能直接问「上个月奶茶花了多少」。"),
]
for i, (col, (icon, title, text)) in enumerate(zip(st.columns(4, border=True), STEPS), start=1):
    with col:
        st.markdown(f"#### :blue[{icon}]\n**{i}. {title}**")
        st.caption(text)
