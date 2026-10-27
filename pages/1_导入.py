"""导入页：上传账单文件 → 解析 → 清洗 → 预览。

清洗后的交易表存在 st.session_state["transactions"] 里，其他页面从这里读取；
被排除的记录存在 st.session_state["removed"] 里，方便核对。
"""

import pandas as pd
import streamlit as st

from app_state import ai_settings, clear, load_files
from core.classify import coverage
from core.clean import cross_month_refunds, totals
from core.demo import demo_files
from core.schema import COLUMN_LABELS, empty_table

st.title("📥 导入账单")
st.write("支持微信账单（.xlsx）和支付宝账单（.csv），可以一次选多个文件。")


def load(files: list[tuple[str, bytes]], use_ai: bool = False):
    with st.spinner("正在解析、分类…" + ("（AI 补全需要十几秒）" if use_ai else "")):
        errors = load_files(files, use_ai=use_ai)
    for err in errors:
        st.error(err)


def show_table(df: pd.DataFrame, extra_columns: dict | None = None):
    """用中文列名显示交易表。"""
    st.dataframe(
        df.drop(columns=["category", "category_source"]).rename(columns={**COLUMN_LABELS, **(extra_columns or {})}),
        hide_index=True,
        width="stretch",
        column_config={
            "金额": st.column_config.NumberColumn(format="¥%.2f"),
            "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        },
    )


# ---------- 上传区 ----------
uploaded = st.file_uploader(
    "把账单文件拖到下面的框里，或点 Upload 选择",
    type=["csv", "xlsx"],
    accept_multiple_files=True,
)
has_key = ai_settings() is not None
use_ai = st.toggle(
    "用 AI 补全规则认不出的分类（DeepSeek）",
    value=has_key,
    disabled=not has_key,
    key="use_ai",
    help="只把规则认不出的支出的「商家名、商品名」发给 DeepSeek，不发时间、金额、支付方式；"
         "转账、红包已经由规则分到「社交」，不会发出去。",
)
if not has_key:
    st.caption("还没有设置 DeepSeek API Key：把 Key 填进项目里的 `.streamlit/secrets.toml`，再重启网站就能用。")

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("开始解析", type="primary", disabled=not uploaded):
        load([(f.name, f.getvalue()) for f in uploaded], use_ai=use_ai)
with col2:
    if st.button("没有账单？用示例账单试试", help="虚构大学生「小林」半年的微信 + 支付宝账单，所有交易都是编的"):
        load(demo_files())

# ---------- 结果预览 ----------
df = st.session_state.get("transactions", empty_table())
removed = st.session_state.get("removed", pd.DataFrame())
if df.empty:
    st.info("还没有导入数据。")
    st.stop()

st.divider()
st.subheader("解析结果")

t = totals(df)
m1, m2, m3, m4 = st.columns(4)
m1.metric("有效交易", f"{len(df)} 笔")
m2.metric("支出", f"¥{t['支出']:,.2f}")
m3.metric("收入", f"¥{t['收入']:,.2f}")
m4.metric("时间范围", f"{df['time'].min():%m/%d}–{df['time'].max():%m/%d}")

counts = df["platform"].value_counts()
st.write("　".join(f"**{k}** {v} 笔" for k, v in counts.items()))

if "ai_result" in st.session_state:
    level, message = st.session_state["ai_result"]
    getattr(st, level)(message, icon=":material/smart_toy:")

spend = df[df["direction"] == "支出"]
unclassified = spend["category"].isna().sum()
if unclassified:
    st.write(f":material/category: 自动分类：支出里 **{coverage(df):.0%}** 已分类，"
             f"还有 **{unclassified} 笔**没认出来，可以在「流水」页手动改。")
else:
    st.write(":material/category: 自动分类：所有支出都已分类，可以在「流水」页查看和修改。")
notes = ["「不计收支」的记录（充值、理财、余额宝转入等）保留在表里，但不算进支出和收入", "部分退款已自动扣除"]
refunds = cross_month_refunds(df)
if not refunds.empty:
    notes.append(f"{len(refunds)} 笔跨月退款（原订单不在这份账单里）已抵扣本月支出 ¥{-refunds['amount'].sum():,.2f}")
st.caption("；".join(notes) + "。")

show_table(df)

if not removed.empty:
    reasons = removed["reason"].value_counts()
    summary = "、".join(f"{k} {v} 笔" for k, v in reasons.items())
    with st.expander(f"🧹 已自动排除 {len(removed)} 笔：{summary}"):
        show_table(removed, {"reason": "排除原因"})

if st.button("清空数据"):
    clear()
    st.rerun()
