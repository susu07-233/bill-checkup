"""导入页：上传账单文件 → 解析 → 预览。

解析好的交易表存在 st.session_state["transactions"] 里，其他页面从这里读取。
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from core.parse import parse_bill
from core.schema import COLUMN_LABELS, empty_table

SAMPLES = Path(__file__).parent.parent / "tests" / "fixtures"

st.title("📥 导入账单")
st.write("支持微信账单（.xlsx）和支付宝账单（.csv），可以一次选多个文件。")


def load(files: list[tuple[str, bytes]]):
    """解析多个文件，合并后存进 session_state。"""
    tables, errors = [], []
    for name, data in files:
        try:
            tables.append(parse_bill(name, data))
        except Exception as e:  # 某个文件解析失败，不影响其他文件
            errors.append(f"**{name}**：{e}")

    if tables:
        merged = pd.concat(tables, ignore_index=True)
        # 同一份账单导入两次时，靠 id 去重
        merged = merged.drop_duplicates(subset="id").sort_values("time", ascending=False)
        st.session_state["transactions"] = merged.reset_index(drop=True)
    for err in errors:
        st.error(err)


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
if df.empty:
    st.info("还没有导入数据。")
    st.stop()

st.divider()
st.subheader("解析结果")

spend = df.loc[df["direction"] == "支出", "amount"].sum()
income = df.loc[df["direction"] == "收入", "amount"].sum()
m1, m2, m3, m4 = st.columns(4)
m1.metric("交易笔数", f"{len(df)} 笔")
m2.metric("支出", f"¥{spend:,.2f}")
m3.metric("收入", f"¥{income:,.2f}")
m4.metric("时间范围", f"{df['time'].min():%m/%d}–{df['time'].max():%m/%d}")
st.caption("⚠️ 目前还包含已退款、已关闭的交易，第 4 步清洗后会更准确。")

counts = df["platform"].value_counts()
st.write("　".join(f"**{k}** {v} 笔" for k, v in counts.items()))

st.dataframe(
    df.drop(columns=["category", "category_source"]).rename(columns=COLUMN_LABELS),
    hide_index=True,
    width="stretch",
    column_config={
        "金额": st.column_config.NumberColumn(format="¥%.2f"),
        "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
    },
)

if st.button("清空数据"):
    del st.session_state["transactions"]
    st.rerun()
