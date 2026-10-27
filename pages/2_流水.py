"""流水页：筛选、搜索交易，在表格里直接改分类。

改分类的流程：
  表格里改了某一格 → on_change 回调 → 用这一行的 id 找到原交易 → 改 session_state["transactions"]
这样换了筛选条件、去了别的页面，改过的分类都不会丢。
"""

import streamlit as st

from app_state import load_files
from core.clean import totals
from core.demo import demo_files
from core.filters import UNCATEGORIZED, filter_transactions, group_key, set_category, summarize
from core.schema import CATEGORIES, COLUMN_LABELS, DIRECTIONS, PLATFORMS

EDITOR_KEY = "flow_editor"
VIEW_IDS_KEY = "flow_view_ids"   # 表格里每一行对应的交易 id（回调里用来找到原交易）
ALL = "全部"
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

    # 平台、收/支：单选，点哪个就「只看哪个」；required=True 保证不会一个都没选
    c3, c4, c5 = st.columns([1.1, 1.9, 2])
    with c3:
        platform = st.segmented_control("平台", [ALL, *PLATFORMS], default=ALL, required=True)
    with c4:
        direction = st.segmented_control("收/支", [ALL, *DIRECTIONS], default=ALL, required=True)
    with c5:
        # 分类：选项后面带上笔数，一眼看出哪些分类还没有交易
        category_counts = df["category"].fillna(UNCATEGORIZED).replace("", UNCATEGORIZED).value_counts()
        options = [c for c in [*CATEGORIES, UNCATEGORIZED] if category_counts.get(c, 0) > 0]
        nothing_categorized = options == [UNCATEGORIZED]
        categories = st.multiselect(
            "分类",
            options,
            format_func=lambda c: f"{c}（{category_counts.get(c, 0)} 笔）",
            placeholder="还没有交易分类" if nothing_categorized else "全部分类",
            disabled=nothing_categorized,
            help="只列出已经有交易的分类。导入时会自动分类；分错了可以在「明细」里手动改。",
        )

platforms = PLATFORMS if platform == ALL else [platform]
directions = DIRECTIONS if direction == ALL else [direction]

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
    if categories:
        st.warning("选中的分类在这个时间范围里没有交易，换个分类或时间试试。")
    else:
        st.warning("没有符合条件的交易，换个筛选条件试试。")
    st.stop()


# ---------- 查看方式 ----------
MODE_MERCHANT, MODE_CATEGORY, MODE_DETAIL = "按商家汇总", "按分类汇总", "明细"
mode = st.segmented_control(
    "查看方式", [MODE_MERCHANT, MODE_CATEGORY, MODE_DETAIL], default=MODE_MERCHANT, required=True, key="flow_mode",
)

if mode in (MODE_MERCHANT, MODE_CATEGORY):
    by, label = ("counterparty", "商家") if mode == MODE_MERCHANT else ("category", "分类")
    summary = summarize(view, by).rename(columns={by: label})
    st.dataframe(
        summary,
        hide_index=True,
        column_config={
            label: st.column_config.TextColumn(pinned=True),
            "支出": st.column_config.NumberColumn(format="¥%.2f"),
            "收入": st.column_config.NumberColumn(format="¥%.2f"),
            "支出占比": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        },
        alt=f"筛选结果{mode}，每一项的笔数、支出、收入和支出占比",
    )
    st.caption(f"共 {len(summary)} 个{label}，按支出从多到少排序。")

    picked = st.selectbox(
        f"查看某个{label}的每一笔明细",
        summary[label].tolist(),       # 和上面的表格顺序一致：花得多的在前
        index=None,
        placeholder=f"选择{label}…",
        format_func=lambda x: f"{x}　支出 ¥{summary.set_index(label).loc[x, '支出']:,.2f}",
        key=f"pick_{by}",
    )
    if picked is not None:
        rows = view[group_key(view, by) == picked]
        st.subheader(f"{picked} 的 {len(rows)} 笔明细")
        st.dataframe(
            rows[SHOWN_COLUMNS].rename(columns=COLUMN_LABELS),
            hide_index=True,
            placeholder="—",
            column_config={
                "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                "金额": st.column_config.NumberColumn(format="¥%.2f"),
            },
            alt=f"{picked} 的交易明细",
        )
    st.stop()


# ---------- 明细：批量改分类 ----------
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
