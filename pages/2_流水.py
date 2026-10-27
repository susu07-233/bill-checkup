"""流水页：筛选、搜索交易，在表格里直接改分类。

改分类的流程：
  表格里改了某一格 → on_change 回调 → 用这一行的 id 找到原交易 → 改 session_state["transactions"]
这样换了筛选条件、去了别的页面，改过的分类都不会丢。
"""

import streamlit as st

from app_state import load_files
from core.clean import totals
from core.demo import demo_files
from core.filters import UNCATEGORIZED, filter_transactions, set_category
from core.schema import CATEGORIES, COLUMN_LABELS, DIRECTIONS, PLATFORMS

EDITOR_KEY = "flow_editor"
VIEW_IDS_KEY = "flow_view_ids"   # 表格里每一行对应的交易 id（回调里用来找到原交易）
SHOWN_COLUMNS = ["time", "amount", "direction", "counterparty", "item", "category", "category_source",
                 "platform", "pay_method", "status", "raw_type"]

st.title("📋 交易流水")

df = st.session_state.get("transactions")
if df is None or df.empty:
    st.info("还没有导入数据。在左侧点「导入」上传账单，或者直接用示例账单看看效果。")
    if st.button("用示例账单试试", icon=":material/science:"):
        load_files(demo_files())
        st.rerun()
    st.stop()


# ---------- 筛选 ----------
with st.container(border=True):
    first_day, last_day = df["time"].min().date(), df["time"].max().date()
    c1, c2 = st.columns([1, 2])
    with c1:
        period = st.date_input("时间范围", value=(first_day, last_day), min_value=first_day, max_value=last_day)
    with c2:
        keyword = st.text_input("搜索", placeholder="商家或商品，多个词用空格隔开，比如：美团 外卖")

    c3, c4, c5 = st.columns([1.1, 1.6, 2.3])
    with c3:
        platforms = st.pills("平台", PLATFORMS, selection_mode="multi", default=PLATFORMS)
    with c4:
        directions = st.pills("收/支", DIRECTIONS, selection_mode="multi", default=["支出", "收入"])
    with c5:
        categories = st.multiselect("分类", [*CATEGORIES, UNCATEGORIZED], placeholder="全部分类")

# date_input 选范围时，只点了开始日期会暂时只返回一个值；清空了就是空的
period = tuple(period) if isinstance(period, (tuple, list)) else (period,)
start = period[0] if len(period) >= 1 else first_day
end = period[1] if len(period) >= 2 else last_day
view = filter_transactions(df, start, end, platforms, directions, categories, keyword)


# ---------- 汇总 ----------
t = totals(view)
with st.container(horizontal=True):
    st.metric("筛选出", f"{len(view)} 笔", border=True)
    st.metric("支出", f"¥{t['支出']:,.2f}", border=True)
    st.metric("收入", f"¥{t['收入']:,.2f}", border=True)

if view.empty:
    st.warning("没有符合条件的交易，换个筛选条件试试。")
    st.stop()


# ---------- 批量改分类 ----------
def apply_bulk(ids: list[str]):
    category = st.session_state["bulk_category"]
    st.session_state["transactions"] = set_category(st.session_state["transactions"], ids, category)
    st.toast(f"已把 {len(ids)} 笔交易设为「{category}」", icon=":material/check:")


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.selectbox("把筛选出的交易都设为", CATEGORIES, key="bulk_category", width=220)
    st.button(f"应用到这 {len(view)} 笔", on_click=apply_bulk, args=(view["id"].tolist(),), icon=":material/done_all:")


# ---------- 交易表格（可以直接改「分类」这一列） ----------
def apply_edits():
    """表格里改了分类 → 写回 session_state["transactions"]。"""
    edits = st.session_state[EDITOR_KEY]["edited_rows"]   # {行号: {列名: 新值}}
    ids = st.session_state[VIEW_IDS_KEY]
    data = st.session_state["transactions"]
    for row, change in edits.items():
        if COLUMN_LABELS["category"] in change:
            data = set_category(data, [ids[row]], change[COLUMN_LABELS["category"]])
    st.session_state["transactions"] = data


table = view[SHOWN_COLUMNS].rename(columns=COLUMN_LABELS).reset_index(drop=True)
st.session_state[VIEW_IDS_KEY] = view["id"].tolist()

category_label = COLUMN_LABELS["category"]
st.data_editor(
    table,
    key=EDITOR_KEY,
    on_change=apply_edits,
    hide_index=True,
    num_rows="fixed",
    placeholder="—",          # 还没分类的格子显示「—」，而不是 None
    disabled=[c for c in table.columns if c != category_label],
    column_config={
        "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm", pinned=True),
        "金额": st.column_config.NumberColumn(format="¥%.2f"),
        category_label: st.column_config.SelectboxColumn(options=CATEGORIES, help="点格子选择分类"),
        "分类来源": st.column_config.TextColumn(help="规则 / AI / 手动"),
    },
    alt="交易流水表，可以修改每笔交易的分类",
)
st.caption("双击「分类」那一格就能修改；其他列是账单原始数据，不能改。负数金额是跨月退款。")

st.download_button(
    "下载筛选结果（CSV，可用 Excel 打开）",
    data=table.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"交易流水_{start:%Y%m%d}-{end:%Y%m%d}.csv",
    mime="text/csv",
    icon=":material/download:",
)
