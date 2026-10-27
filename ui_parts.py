"""几个页面共用的界面部件。

- show_rows：弹窗「看看这几笔」（首页答案、看板发现都用它）
- ask_box：「问一问」输入框（看板、报告页都用它）
"""

from datetime import date

import pandas as pd
import streamlit as st

from core.ai_classify import AIError
from core.money import YUAN_COLUMN_FORMAT
from core.qa import METRICS, merchant_candidates, parse_question, pick_merchants, run_query
from core.schema import COLUMN_LABELS

EXAMPLES = ["上个月奶茶花了多少？", "这个月花钱最多的 5 个商家", "最大的一笔支出是什么？", "每个月吃喝花了多少？"]


def transactions_table(rows: pd.DataFrame, alt: str):
    st.dataframe(
        rows.sort_values("time", ascending=False)[["time", "amount", "counterparty", "item", "category"]]
        .rename(columns=COLUMN_LABELS),
        hide_index=True,
        column_config={"金额": st.column_config.NumberColumn(format=YUAN_COLUMN_FORMAT),
                       "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
        alt=alt,
    )


@st.dialog("看看这几笔", width="large")
def show_rows(title: str, rows: pd.DataFrame):
    st.markdown(f"**{title}**")
    st.caption(f"{len(rows)} 笔，合计 {rows['amount'].sum():,.2f} 元")
    transactions_table(rows, alt=title)


def ask_box(df: pd.DataFrame, ai, key: str):
    """「问一问」：AI 把问题翻译成查询条件，程序算答案。ai 为 None（没设置 Key）时只显示提示。"""
    if ai is None:
        st.caption("设置好 DeepSeek API Key 后，可以直接问：" + "、".join(f"「{q}」" for q in EXAMPLES))
        return

    allow_names = st.toggle(
        "让 AI 从我账单里的商家中挑（找得到本地小店）", value=True, key=f"qa_allow_names_{key}",
        help="问到具体东西（比如奶茶）时，把这段时间账单里出现过的商家名发给 AI，让它挑出相关的店。"
             "只发商家名和商品名，不发金额和时间；转账、红包、AA 的对方名字不发。关掉就只按常见品牌名搜索。")
    picked = st.pills("试试这些", EXAMPLES, key=f"qa_example_{key}", label_visibility="collapsed")
    typed = st.chat_input("问问你的账单，比如：9 月打车花了多少？", key=f"qa_input_{key}")
    question = typed or picked
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("理解问题…"):
                spec = _understand(question, df, ai, allow_names)
        except AIError as e:
            st.error(str(e))
            return

        answer, table, rows = run_query(df, spec)
        st.markdown(answer)
        if not spec.get("unsupported"):
            how = [spec["understanding"] or METRICS[spec["metric"]]]
            if spec.get("picked"):
                how.append("AI 从你的账单里挑出的店：" + "、".join(s.split("｜")[-1][:12] for s in spec["picked"][:8])
                           + ("……" if len(spec["picked"]) > 8 else ""))
            elif spec["keywords"]:
                how.append("搜索的关键词：" + "、".join(spec["keywords"]))   # 漏了哪家店，一眼能看出来
            st.caption("我理解的问题：" + "　".join(how))
        if table is not None:
            st.dataframe(table, hide_index=True,
                         column_config={"金额": st.column_config.NumberColumn(format=YUAN_COLUMN_FORMAT)},
                         alt="问题的汇总结果")
        if len(rows):
            with st.expander(f"用到的 {len(rows)} 笔交易"):
                transactions_table(rows, alt="回答这个问题用到的交易")


def _understand(question: str, df: pd.DataFrame, ai, allow_names: bool) -> dict:
    """理解问题（同一个问题只问一次 AI，刷新页面不重复花钱）。"""
    cache = st.session_state.setdefault("qa_cache", {})
    cache_key = (question, allow_names, len(df))
    if cache_key not in cache:
        spec = parse_question(question, *ai, today=date.today(),
                              data_start=df["time"].min().date(), data_end=df["time"].max().date())
        if allow_names and spec.get("keywords"):
            spec["picked"] = pick_merchants(spec, merchant_candidates(df, spec), *ai)
        cache[cache_key] = spec
    return cache[cache_key]
