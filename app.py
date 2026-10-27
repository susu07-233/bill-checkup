"""入口：页面设置、导航、侧边栏。

运行方式：uv run streamlit run app.py
页面文件在 app_pages/ 里；这里决定侧边栏显示哪些页面、叫什么名字、用什么图标。
侧边栏除了导航，还一直显示「当前数据」和「AI 状态」，在任何页面都知道自己在看哪份数据。
主题（颜色、字体、圆角）在 .streamlit/config.toml 里统一设置；卡片阴影等补充样式在 styles.py。
"""

import streamlit as st

import styles
from app_state import ai_settings, clear
from core.clean import totals
from core.money import yuan
from core.overrides import is_local

st.set_page_config(page_title="账单体检", page_icon="assets/icon.svg", layout="wide")
st.logo("assets/logo.svg", size="large", icon_image="assets/icon.svg")
styles.inject()

page = st.navigation({
    "开始": [
        st.Page("app_pages/home.py", title="首页", icon=":material/home:", default=True),
        st.Page("app_pages/import_bills.py", title="导入", icon=":material/upload_file:", url_path="import"),
    ],
    "分析": [
        st.Page("app_pages/transactions.py", title="流水", icon=":material/receipt_long:", url_path="transactions"),
        st.Page("app_pages/dashboard.py", title="看板", icon=":material/bar_chart:", url_path="dashboard"),
        st.Page("app_pages/report.py", title="报告", icon=":material/auto_awesome:", url_path="report"),
    ],
})


# ---------- 侧边栏：当前数据 + AI 状态 ----------
with st.sidebar:
    st.space("small")
    with st.container(border=True, key="card_data"):
        st.markdown("**:material/database: 当前数据**")
        df = st.session_state.get("transactions")
        if df is None or df.empty:
            st.caption("还没有导入账单。去「导入」上传，或者在页面上点「用示例账单试试」。")
        else:
            st.markdown(f"### {len(df)} 笔")
            st.caption(f"{df['time'].min():%Y-%m-%d} 至 {df['time'].max():%Y-%m-%d}  \n"
                       f"{st.session_state.get('data_source', '我的账单')}  \n"
                       f"总支出 {yuan(totals(df)['支出'])}")
            if st.button("清空数据", icon=":material/delete:", width="stretch", key="sidebar_clear"):
                clear()
                st.rerun()

    if ai_settings():
        st.markdown(":green-badge[:material/check_circle: AI 已连接（DeepSeek）]")
    else:
        st.markdown(":gray-badge[:material/cloud_off: AI 未设置，只用规则分类]")
    st.caption(":material/lock: " + ("账单只在这台电脑上处理，手动修改保存在本地。" if is_local()
                                     else "在线演示：账单不保存，关掉页面就清空。"))

# 每一页都放在 key=page 的容器里：styles.py 用它限制正文最大宽度
with st.container(key="page"):
    page.run()
