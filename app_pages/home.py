"""首页：先引起好奇心，再引导导入（参考 Codex 的改版建议）。

左边：「没买什么，钱都花哪儿了？」+ 三个可以直接点的问题；
右边：小票式的答案卡片，点「看看这几笔」能看到是哪几笔。
答案由程序算（core/curiosity.py），不用 AI；导入了自己的账单就用自己的，没有就用示例数据（小林）。
「它是怎么做到的」放到页面最下面，第一次来的人先看到答案，而不是功能说明。
"""

import pandas as pd
import streamlit as st

from app_state import load_files
from core.classify import classify
from core.clean import clean
from core.curiosity import QUESTIONS, latest_month
from core.demo import demo_files
from core.overrides import is_local
from core.parse import parse_bill
from ui_parts import show_rows


@st.cache_data(show_spinner=False)
def demo_data() -> pd.DataFrame:
    """示例数据（小林半年），首页问题的默认答案来源。只算一次。"""
    return classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])


mine = st.session_state.get("transactions")
use_mine = mine is not None and not mine.empty
df = mine if use_mine else demo_data()
month = latest_month(df)
whose = f"你的 {int(month[5:])} 月" if use_mine else f"小林的 {int(month[5:])} 月 · 示例答案"

question_list = list(QUESTIONS)
asked = st.session_state.setdefault("home_question", question_list[0])

hero = st.container(key="home")          # 右上角的绿色柔光（styles.py）
left, right = hero.columns([5, 4], gap="large", vertical_alignment="center")

with left:
    st.caption(":material/favorite: 给自己的消费，一点好奇心")
    st.title("没买什么，钱都花哪儿了？", anchor=False)
    st.markdown("把微信和支付宝的账单放在一起，看看那些没注意到的小花销。")
    st.space("small")
    for q in question_list:
        if st.button(q, icon=":material/north_east:", width="stretch",
                     type="primary" if q == asked else "secondary", key=f"q_{q}"):
            st.session_state["home_question"] = q
            st.rerun()
    st.caption("点问题看答案" + ("（来自你导入的账单）。" if use_mine else "；现在是示例答案，导入自己的账单就能看到你的。"))
    st.space("small")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.page_link("app_pages/import_bills.py", label="导入我的账单", icon=":material/upload_file:")
        if not use_mine and st.button("翻开小林的示例账单", icon=":material/menu_book:", type="tertiary"):
            load_files(demo_files())
            st.switch_page("app_pages/dashboard.py")


# 小票式答案卡片：抬头 → 大金额 → 虚线隔开的明细 → 「看看这几笔」
with right, st.container(key="receipt"):
    answer = QUESTIONS[asked](df, month)
    with st.container(key="receipt_head", horizontal=True, horizontal_alignment="distribute"):
        st.caption(":material/receipt_long: 账单体检")
        st.caption(whose)
    st.markdown(f"**{answer['title']}**")
    with st.container(key="receipt_total"):
        st.markdown(f"# {answer['amount']:,.2f} 元")        # 统一两位小数，和明细能对上
    st.caption(answer["note"])
    if answer["items"]:
        with st.container(key="receipt_items", gap="xsmall"):
            st.caption(answer["items_label"])               # 比如「支出前三家」：说清楚只列了前几个
            for name, detail in answer["items"]:
                with st.container(horizontal=True, horizontal_alignment="distribute"):
                    st.markdown(name)
                    st.markdown(f":gray[{detail}]")
            if answer["rest"]:                              # 没列出来的合成一行，加起来就是上面的总数
                with st.container(horizontal=True, horizontal_alignment="distribute"):
                    st.markdown(f":gray[{answer['rest'][0]}]")
                    st.markdown(f":gray[{answer['rest'][1]}]")
    if len(answer["rows"]):
        if st.button("看看这几笔", icon=":material/north_east:", type="tertiary"):
            show_rows(answer["title"], answer["rows"])


st.space("large")
privacy = "账单只在本地处理" if is_local() else "在线演示：账单不保存，关掉页面就清空"
with st.expander("它是怎么做到的？", icon=":material/help:"):
    st.markdown(f":green-badge[:material/lock: {privacy}]")
    STEPS = [
        (":material/upload_file:", "导入", "直接用微信、支付宝官方导出的账单，可以一次拖进多个文件。"),
        (":material/cleaning_services:", "自动整理", "去掉退款和关闭的交易，部分退款按实际花费算，跨月退款抵扣本月。"),
        (":material/category:", "自动分类", "规则先分，认不出的交给 AI；分错了可以手动改，会记住。"),
        (":material/insights:", "看懂花销", "看板看钱花在哪；AI 写月报，还能直接问「上个月奶茶花了多少」。"),
    ]
    for col, (icon, title, text) in zip(st.columns(4), STEPS):
        col.markdown(f"**:green[{icon}] {title}**")
        col.caption(text)
