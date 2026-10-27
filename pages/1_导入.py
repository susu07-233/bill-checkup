"""导入页：上传账单文件 → 解析 → 清洗 → 分类，然后给一份「导入报告」：导入了多少、自动处理了什么。

清洗后的交易表存在 st.session_state["transactions"] 里，其他页面从这里读取；
被排除的记录存在 st.session_state["removed"] 里，方便核对。
"""

import pandas as pd
import streamlit as st

from app_state import ai_settings, clear, load_files
from core.classify import coverage
from core.clean import refunded_amount, cross_month_refunds
from core.demo import demo_files
from core.money import YUAN_COLUMN_FORMAT, yuan
from core.overrides import is_manually_excluded
from core.schema import COLUMN_LABELS, empty_table

st.title("📥 导入账单")
st.write("支持微信账单（.xlsx）和支付宝账单（.csv），可以一次选多个文件。")


def load(files: list[tuple[str, bytes]], use_ai: bool = False):
    with st.spinner("正在解析、分类…" + ("（AI 补全需要十几秒）" if use_ai else "")):
        errors = load_files(files, use_ai=use_ai)
    for err in errors:
        st.error(err)


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

# ---------- 导入报告 ----------
# 只说「导入时做了什么」；金额统计在「看板」，每一笔在「流水」，这里不重复
df = st.session_state.get("transactions", empty_table())
removed = st.session_state.get("removed", pd.DataFrame())
if df.empty:
    st.stop()

st.divider()
counts = "、".join(f"{k} {v} 笔" for k, v in df["platform"].value_counts().items())
st.subheader(f"导入了 {len(df)} 笔交易")
st.caption(f"{counts}；{df['time'].min():%Y-%m-%d} 至 {df['time'].max():%Y-%m-%d}")

if "ai_result" in st.session_state:
    level, message = st.session_state["ai_result"]
    getattr(st, level)(message, icon=":material/smart_toy:")

with st.container(border=True):
    st.markdown("**自动处理**")
    spend = df[df["direction"] == "支出"]
    source = spend["category_source"].value_counts()
    unclassified = int(spend["category"].isna().sum())
    parts = [f"规则 {source.get('规则', 0)} 笔", f"AI {source.get('AI', 0)} 笔", f"手动 {source.get('手动', 0)} 笔"]
    lines = [f":material/category: **分类**：{len(spend)} 笔支出，{coverage(df):.0%} 已分类（"
             + "、".join(p for p in parts if not p.endswith(" 0 笔")) + "）"
             + (f"，还有 **{unclassified} 笔**没认出来，可以在「流水」页手动改" if unclassified else "")]
    if not removed.empty:
        reasons = "、".join(f"{k} {v} 笔" for k, v in removed["reason"].value_counts().items())
        lines.append(f":material/cleaning_services: **排除**：{reasons}（展开下面的列表可以核对）")
    partial = int((spend["status"].map(refunded_amount) > 0).sum())
    if partial:
        lines.append(f":material/undo: **部分退款**：{partial} 笔已按实际花费扣除")
    refunds = cross_month_refunds(df)
    if not refunds.empty:
        lines.append(f":material/event_repeat: **跨月退款**：{len(refunds)} 笔，抵扣支出 {yuan(-refunds['amount'].sum())}")
    excluded = int(is_manually_excluded(df).sum())
    if excluded:
        lines.append(f":material/block: **手动不计入**：{excluded} 笔（之前标记过，已自动套用）")
    neutral = int(((df["direction"] == "不计收支") & ~is_manually_excluded(df)).sum())
    if neutral:
        lines.append(f":material/swap_horiz: **不计收支**：{neutral} 笔充值、理财、转入余额宝等，不算支出或收入")
    st.markdown("\n\n".join(lines))

if not removed.empty:
    with st.expander(f"自动排除的 {len(removed)} 笔"):
        st.dataframe(
            removed[["time", "amount", "counterparty", "item", "platform", "status", "reason"]]
            .rename(columns={**COLUMN_LABELS, "reason": "排除原因"}),
            hide_index=True,
            column_config={"金额": st.column_config.NumberColumn(format=YUAN_COLUMN_FORMAT),
                           "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
            alt="导入时自动排除的交易和原因",
        )

st.markdown("下一步：去 **看板** 看钱花在哪，去 **流水** 查看和修改每一笔。")
if st.button("清空数据", icon=":material/delete:"):
    clear()
    st.rerun()
