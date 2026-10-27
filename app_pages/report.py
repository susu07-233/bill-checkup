"""报告页：AI 月报 + 问一问。

分工：数字全部由程序算，AI 只负责写文字（月报）和理解问题（问一问），所以答案里的数字不会算错。
隐私：月报只发汇总数字（不发转账、红包对方的名字）；问一问发你的问题，
      另外可以选择让 AI 从账单的商家名里挑（只发商家名，不发金额、时间，不发转账对象）。
"""

import json
from datetime import date

import streamlit as st

import app_state
from app_state import require_data
from core.ai_classify import AIError
from core.ai_report import generate_report, report_facts
from core.dashboard import in_month, insights, months
from core.money import YUAN_COLUMN_FORMAT
from core.qa import METRICS, merchant_candidates, parse_question, pick_merchants, run_query
from core.schema import COLUMN_LABELS

st.title("AI 报告", icon=":material/auto_awesome:", anchor=False)
st.caption("AI 根据统计数字写月报、给省钱建议；也可以直接问账单问题。")
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


# ---------- 问一问 ----------
st.subheader("问一问")
EXAMPLES = ["上个月奶茶花了多少？", "这个月花钱最多的 5 个商家", "最大的一笔支出是什么？", "每个月吃喝花了多少？"]

if ai is None:
    st.caption("设置好 API Key 后，可以直接问：" + "、".join(f"「{q}」" for q in EXAMPLES))
    st.stop()

allow_names = st.toggle(
    "让 AI 从我账单里的商家中挑（找得到本地小店）", value=True, key="qa_allow_names",
    help="问到具体东西（比如奶茶）时，把这段时间账单里出现过的商家名发给 AI，让它挑出相关的店。"
         "只发商家名和商品名，不发金额和时间；转账、红包、AA 的对方名字不发。关掉就只按常见品牌名搜索。")
picked = st.pills("试试这些", EXAMPLES, key="qa_example", label_visibility="collapsed")
typed = st.chat_input("问问你的账单，比如：9 月打车花了多少？")
question = typed or picked


def understand(question: str) -> dict:
    """理解问题（同一个问题只问一次 AI，刷新页面不重复花钱）。"""
    cache = st.session_state.setdefault("qa_cache", {})
    key = (question, allow_names, len(df))
    if key not in cache:
        spec = parse_question(question, *ai, today=date.today(),
                              data_start=df["time"].min().date(), data_end=df["time"].max().date())
        if allow_names and spec.get("keywords"):
            spec["picked"] = pick_merchants(spec, merchant_candidates(df, spec), *ai)
        cache[key] = spec
    return cache[key]


if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("理解问题…"):
                spec = understand(question)
        except AIError as e:
            st.error(str(e))
            st.stop()

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
                st.dataframe(
                    rows[["time", "amount", "counterparty", "item", "category"]].rename(columns=COLUMN_LABELS),
                    hide_index=True,
                    column_config={"金额": st.column_config.NumberColumn(format=YUAN_COLUMN_FORMAT),
                                   "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
                    alt="回答这个问题用到的交易",
                )
