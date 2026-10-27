"""各个页面共用的数据操作。

导入：解析 → 合并 → 清洗 → 规则分类 → 套用保存的手动修改 →（可选）AI 补全 → 存进 session_state
修改：改分类、标记「不计入」、恢复 —— 同时改 session_state 里的表，并保存到 private/手动修改.json

st.session_state 里的约定：
  transactions —— 清洗后的交易表（流水、看板、报告都读它）
  removed      —— 自动排除的记录（带 reason 列）
  ai_result    —— 最近一次 AI 补全的结果说明（给导入页显示）
"""

import pandas as pd
import streamlit as st

from core import overrides as ov
from core.money import yuan
from core.ai_classify import DEFAULT_BASE_URL, DEFAULT_MODEL, AIError, ai_classify, make_client
from core.classify import classify
from core.clean import clean
from core.filters import set_category
from core.parse import parse_bill


def ai_settings() -> dict | None:
    """读取 .streamlit/secrets.toml 里的 DeepSeek 设置；没设置好就返回 None。"""
    try:
        key = str(st.secrets.get("DEEPSEEK_API_KEY", "")).strip()
        base_url = st.secrets.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
        model = st.secrets.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
    except Exception:  # 没有 secrets.toml 文件
        return None
    if not key.startswith("sk-"):
        return None
    return {"api_key": key, "base_url": base_url, "model": model}


def ai_client():
    """返回 (AI 客户端, 模型名)；没设置 Key 返回 None。"""
    settings = ai_settings()
    if settings is None:
        return None
    return make_client(settings["api_key"], settings["base_url"]), settings["model"]


def require_data() -> pd.DataFrame:
    """页面开头调用：有数据就返回交易表；没有就提示去导入、给一个「用示例账单试试」按钮，并停止这一页。"""
    df = st.session_state.get("transactions")
    if df is not None and not df.empty:
        return df
    st.info("还没有导入数据。在左侧点「导入」上传账单，或者直接用示例账单看看效果。")
    if st.button("用示例账单试试", icon=":material/science:"):
        from core.demo import demo_files
        load_files(demo_files())
        st.rerun()
    st.stop()


def load_files(files: list[tuple[str, bytes]], use_ai: bool = False) -> list[str]:
    """解析多个账单文件并存进 session_state。返回出错的提示（每个文件一条），没出错就是空列表。"""
    tables, errors = [], []
    for name, data in files:
        try:
            tables.append(parse_bill(name, data))
        except Exception as e:  # 某个文件解析失败，不影响其他文件
            errors.append(f"**{name}**：{e}")

    st.session_state.pop("ai_result", None)
    if tables:
        kept, removed = clean(pd.concat(tables, ignore_index=True))
        kept = classify(kept)
        # 手动修改在 AI 之前套用：手动改过分类、标记了不计入的，就不用再问 AI
        kept = ov.apply_overrides(kept, ov.load_overrides())
        if use_ai:
            kept, st.session_state["ai_result"] = fill_with_ai(kept, ai_settings())
        st.session_state["transactions"] = kept.sort_values("time", ascending=False).reset_index(drop=True)
        st.session_state["removed"] = removed
    return errors


def fill_with_ai(df: pd.DataFrame, settings: dict | None, client_factory=make_client):
    """用 AI 补全规则认不出的分类。返回（新表, (提示级别, 提示文字)）。出错时保留规则结果。"""
    if settings is None:
        return df, ("warning", "还没有设置 DeepSeek API Key，这次只用了规则分类。")
    try:
        client = client_factory(settings["api_key"], settings["base_url"])
        out, stats = ai_classify(df, client, model=settings["model"])
    except AIError as e:
        return df, ("error", f"AI 分类没成功，这次只用了规则分类。{e}")
    if stats.asked == 0:
        return out, ("info", "规则已经全部分好了，不需要 AI。")
    return out, ("success", f"AI 补全了 **{stats.classified} 笔**（问了 {stats.asked} 个不同的商家），"
                            f"约花费 {yuan(stats.cost_yuan, 4)}。")


def change_category(ids, category: str | None):
    """手动改分类，并保存下来。"""
    st.session_state["transactions"] = set_category(st.session_state["transactions"], ids, category)
    ov.save_overrides(ov.record_category(ov.load_overrides(), ids, category))


def set_excluded(ids, excluded: bool):
    """标记为「不计入」，或者恢复，并保存下来。"""
    saved = ov.load_overrides()
    if excluded:
        df, saved = ov.exclude(st.session_state["transactions"], saved, ids)
    else:
        df, saved = ov.restore(st.session_state["transactions"], saved, ids, classify)
    st.session_state["transactions"] = df
    ov.save_overrides(saved)


def clear():
    for key in ("transactions", "removed", "ai_result"):
        st.session_state.pop(key, None)
