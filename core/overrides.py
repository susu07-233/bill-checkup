"""手动修改：用户手动改的分类、标记为「不计入」的交易，按交易 id 保存在本地文件里。

为什么要保存：只存在网页里的话，刷新页面或重新导入账单就没了，下个月还要再改一遍。
存在哪：private/手动修改.json（private/ 不会上传到 GitHub）。只存交易 id 和改了什么，不存交易内容。

文件格式：
  {
    "wx_4200...": {"category": "餐饮"},
    "wx_1000...": {"exclude": true, "original_direction": "支出"}
  }

「不计入」的交易：收/支 改成「不计收支」，不再算进支出或收入；分类来源显示「手动排除」，可以恢复。
"""

import json
from pathlib import Path

import pandas as pd

from core.filters import SOURCE_MANUAL

OVERRIDES_FILE = Path(__file__).resolve().parent.parent / "private" / "手动修改.json"
SOURCE_EXCLUDED = "手动排除"


def load_overrides(path: Path | None = None) -> dict[str, dict]:
    path = path or OVERRIDES_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}   # 文件坏了就当没有，不影响使用


def save_overrides(overrides: dict[str, dict], path: Path | None = None) -> None:
    path = path or OVERRIDES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in overrides.items() if v}   # 空的记录不存
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")


def apply_overrides(df: pd.DataFrame, overrides: dict[str, dict]) -> pd.DataFrame:
    """把保存的手动修改套用到交易表上（导入账单时调用）。返回新表。"""
    df = df.copy()
    for id_, change in overrides.items():
        rows = df["id"] == id_
        if not rows.any():
            continue
        if change.get("exclude"):
            df.loc[rows, ["direction", "category", "category_source"]] = ["不计收支", None, SOURCE_EXCLUDED]
        elif "category" in change and (df.loc[rows, "direction"] == "支出").all():
            df.loc[rows, ["category", "category_source"]] = [change["category"], SOURCE_MANUAL]
    return df


def record_category(overrides: dict, ids, category: str | None) -> dict:
    """记下手动改的分类；category 为空表示清除手动分类。返回新的字典。"""
    overrides = {k: dict(v) for k, v in overrides.items()}
    for id_ in ids:
        entry = overrides.setdefault(id_, {})
        if category:
            entry["category"] = category
        else:
            entry.pop("category", None)
    return overrides


def exclude(df: pd.DataFrame, overrides: dict, ids) -> tuple[pd.DataFrame, dict]:
    """把交易标记为「不计入」。本来就是「不计收支」的（充值、理财）不用处理。"""
    df, overrides = df.copy(), {k: dict(v) for k, v in overrides.items()}
    for id_ in ids:
        rows = df["id"] == id_
        if not rows.any():
            continue
        direction = df.loc[rows, "direction"].iloc[0]
        if direction == "不计收支":
            continue
        overrides.setdefault(id_, {}).update(exclude=True, original_direction=direction)
        df.loc[rows, ["direction", "category", "category_source"]] = ["不计收支", None, SOURCE_EXCLUDED]
    return df, overrides


def restore(df: pd.DataFrame, overrides: dict, ids, reclassify) -> tuple[pd.DataFrame, dict]:
    """取消「不计入」，恢复原来的收/支，并用 reclassify（规则分类函数）重新给这几笔分类。"""
    df, overrides = df.copy(), {k: dict(v) for k, v in overrides.items()}
    restored = []
    for id_ in ids:
        entry = overrides.get(id_, {})
        if not entry.get("exclude"):
            continue
        rows = df["id"] == id_
        df.loc[rows, ["direction", "category", "category_source"]] = [entry["original_direction"], None, None]
        entry.pop("exclude", None)
        entry.pop("original_direction", None)
        restored.append(id_)
    if restored:
        rows = df["id"].isin(restored)
        df.loc[rows] = apply_overrides(reclassify(df.loc[rows]), overrides)
    return df, overrides


def is_manually_excluded(df: pd.DataFrame) -> pd.Series:
    return df["category_source"] == SOURCE_EXCLUDED
