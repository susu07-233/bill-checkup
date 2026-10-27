"""入口：页面设置 + 导航。

运行方式：uv run streamlit run app.py
页面文件在 app_pages/ 里；这里决定侧边栏显示哪些页面、叫什么名字、用什么图标。
主题（颜色、字体、圆角）在 .streamlit/config.toml 里统一设置。
"""

import streamlit as st

st.set_page_config(page_title="账单体检", page_icon=":material/receipt_long:", layout="wide")

page = st.navigation([
    st.Page("app_pages/home.py", title="首页", icon=":material/home:", default=True),
    st.Page("app_pages/import_bills.py", title="导入", icon=":material/upload_file:", url_path="import"),
    st.Page("app_pages/transactions.py", title="流水", icon=":material/receipt_long:", url_path="transactions"),
    st.Page("app_pages/dashboard.py", title="看板", icon=":material/bar_chart:", url_path="dashboard"),
    st.Page("app_pages/report.py", title="报告", icon=":material/auto_awesome:", url_path="report"),
])
page.run()
