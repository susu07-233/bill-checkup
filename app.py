"""首页：项目入口。

运行方式：uv run streamlit run app.py
Streamlit 会自动把 pages/ 文件夹里的每个 .py 文件变成左侧栏的一个页面，
文件名前面的数字决定排列顺序，数字和下划线不会显示出来。
"""

import streamlit as st

# 页面基础设置：浏览器标签页标题、图标，以及宽屏布局（看板需要更宽的空间）
st.set_page_config(page_title="账单体检", page_icon="💰", layout="wide")

st.title("💰 账单体检")
st.write("导入微信 / 支付宝账单，自动分类，看清钱花在哪。")
st.caption("🔒 所有数据只在本地处理，不会上传。")

st.divider()

# 四张卡片，介绍每个页面的作用，并提供跳转链接
cols = st.columns(4)
pages = [
    ("pages/1_导入.py", "📥 导入", "上传微信、支付宝账单文件"),
    ("pages/2_流水.py", "📋 流水", "查看、筛选、修改每一笔交易"),
    ("pages/3_看板.py", "📊 看板", "趋势、分类占比、商户排行"),
    ("pages/4_报告.py", "📝 报告", "AI 月度点评和提问"),
]
for col, (path, label, desc) in zip(cols, pages):
    with col:
        with st.container(border=True):
            st.page_link(path, label=label)
            st.caption(desc)
