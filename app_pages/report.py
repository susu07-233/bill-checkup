"""报告页：AI 月报 + 问一问。

分工：数字全部由程序算，AI 只负责写文字（月报）和理解问题（问一问），所以答案里的数字不会算错。
隐私：月报只发汇总数字（不发转账、红包对方的名字）；问一问发你的问题，
      另外可以选择让 AI 从账单的商家名里挑（只发商家名，不发金额、时间，不发转账对象）。
"""

import json

import streamlit as st

import app_state
from app_state import require_data
from core.ai_classify import AIError
from core.ai_report import generate_report, report_facts
from core.dashboard import in_month, insights, months
from ui_parts import ask_box

st.title("AI 报告", icon=":material/auto_awesome:", anchor=False)
st.caption("AI 根据统计数字写一份月度回顾，也可以直接问账单问题。")
df = require_data()
ai = app_state.ai_client()

if ai is None:
    st.info("还没有设置 DeepSeek API Key，AI 月报和问一问暂时用不了。把 Key 填进项目里的 "
            "`.streamlit/secrets.toml`，再重启网站就能用。下面先显示程序自动写的小结。",
            icon=":material/key:")


# ---------- 月报 ----------
all_months = months(df)
period = st.selectbox("月份", [*reversed(all_months), "全部"], width=200,
                      format_func=lambda m: m if m == "全部" else f"{m[:4]} 年 {int(m[5:])} 月")
month = None if period == "全部" else period
view = df if month is None else in_month(df, month)
facts = report_facts(df, month)

with st.container(border=True):
    st.markdown(f"**:material/description: {'全部时间' if month is None else f'{int(month[5:])} 月'}月报**")
    cache = st.session_state.setdefault("reports", {})
    cache_key = (period, len(view), round(float(view["amount"].sum()), 2))   # 数据变了就重新生成

    if ai is None:
        st.markdown("\n".join(f"- {line}" for line in insights(view)))
    else:
        if cache_key in cache:
            st.markdown(cache[cache_key])
        label = "重新生成" if cache_key in cache else "生成月报"
        if st.button(label, icon=":material/auto_awesome:", type="secondary" if cache_key in cache else "primary"):
            with st.spinner("AI 正在写月报，大约十秒…"):
                try:
                    cache[cache_key] = generate_report(facts, *ai)
                    st.rerun()
                except AIError as e:
                    st.error(str(e))
        st.caption("统计数字由程序计算；「能省多少」是 AI 按这些数字估算的，仅供参考。")

    with st.expander("发给 AI 的数据"):
        st.caption("只有汇总数字；转账、红包、AA 的对方名字不会发出去。")
        st.code(json.dumps(facts, ensure_ascii=False, indent=1), language="json")


# ---------- 问一问（和看板上的是同一个部件） ----------
st.subheader("问一问")
ask_box(df, ai, key="report")
