"""各个页面共用的「导入数据」操作：解析 → 合并 → 清洗 → 自动分类 → 存进 session_state。

st.session_state 里的约定：
  transactions —— 清洗后的交易表（流水、看板、报告都读它）
  removed      —— 被排除的记录（带 reason 列）
"""

import pandas as pd
import streamlit as st

from core.classify import classify
from core.clean import clean
from core.parse import parse_bill


def load_files(files: list[tuple[str, bytes]]) -> list[str]:
    """解析多个账单文件并存进 session_state。返回出错的提示（每个文件一条），没出错就是空列表。"""
    tables, errors = [], []
    for name, data in files:
        try:
            tables.append(parse_bill(name, data))
        except Exception as e:  # 某个文件解析失败，不影响其他文件
            errors.append(f"**{name}**：{e}")

    if tables:
        kept, removed = clean(pd.concat(tables, ignore_index=True))
        kept = classify(kept)
        st.session_state["transactions"] = kept.sort_values("time", ascending=False).reset_index(drop=True)
        st.session_state["removed"] = removed
    return errors


def clear():
    for key in ("transactions", "removed"):
        st.session_state.pop(key, None)
