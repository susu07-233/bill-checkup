"""导入页：上传账单文件 → 解析 → 清洗 → 预览。

清洗后的交易表存在 st.session_state["transactions"] 里，其他页面从这里读取；
被排除的记录存在 st.session_state["removed"] 里，方便核对。
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from core.clean import clean, cross_month_refunds, totals
from core.parse import parse_bill
from core.schema import COLUMN_LABELS, empty_table

SAMPLES = Path(__file__).parent.parent / "tests" / "fixtures"

st.title("📥 导入账单")
st.write("支持微信账单（.xlsx）和支付宝账单（.csv），可以一次选多个文件。")


def load(files: list[tuple[str, bytes]]):
    """解析多个文件 → 合并 → 清洗，结果存进 session_state。"""
    tables, errors = [], []
    for name, data in files:
        try:
            tables.append(parse_bill(name, data))
        except Exception as e:  # 某个文件解析失败，不影响其他文件
            errors.append(f"**{name}**：{e}")

    if tables:
        kept, removed = clean(pd.concat(tables, ignore_index=True))
        st.session_state["transactions"] = kept.sort_values("time", ascending=False).reset_index(drop=True)
        st.session_state["removed"] = removed
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
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("开始解析", type="primary", disabled=not uploaded):
        load([(f.name, f.getvalue()) for f in uploaded])
with col2:
    if st.button("没有账单？用示例账单试试"):
        load([(p.name, p.read_bytes()) for p in sorted(SAMPLES.glob("*_sample.*"))])

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
    for key in ("transactions", "removed"):
        st.session_state.pop(key, None)
    st.rerun()
