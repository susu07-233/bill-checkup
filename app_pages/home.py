"""首页：一句话说清楚这是什么，给两个入口：先用示例账单体验，或者导入自己的账单。"""

import streamlit as st

from app_state import load_files
from core.demo import demo_files
from core.overrides import is_local

st.title("账单体检", anchor=False)
st.markdown("#### 导入微信、支付宝账单，看清钱花在哪、哪些钱可以省")
privacy = ("账单只在本地处理" if is_local() else "在线演示：账单不保存，关掉页面就清空")
st.markdown(f":blue-badge[:material/lock: {privacy}] "
            ":blue-badge[:material/auto_awesome: 规则 + AI 自动分类] "
            ":blue-badge[:material/school: 为大学生设计]")

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

st.space("medium")

STEPS = [
    (":material/upload_file:", "1. 导入", "直接用微信、支付宝官方导出的账单，可以一次拖进多个文件。"),
    (":material/cleaning_services:", "2. 自动整理",
     "去掉退款和关闭的交易，部分退款按实际花费算，跨月退款抵扣本月，重复导入自动去重。"),
    (":material/category:", "3. 自动分类",
     "规则先分，认不出的交给 AI；在 100 笔真实交易上准确率 87%。分错了可以手动改，会记住。"),
    (":material/insights:", "4. 看懂花销",
     "看板分「必要 / 弹性」，告诉你哪些钱可以省；AI 写月报，还能直接问「上个月奶茶花了多少」。"),
]
for col, (icon, title, text) in zip(st.columns(4, border=True), STEPS):
    with col:
        st.markdown(f"**{icon} {title}**")
        st.caption(text)
