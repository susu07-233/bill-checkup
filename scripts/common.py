"""脚本共用：读取 private/ 里的真实账单。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # 让脚本能 import core

from core.clean import clean      # noqa: E402
from core.parse import parse_bill  # noqa: E402

PRIVATE = ROOT / "private"
LABEL_SHEET = PRIVATE / "分类标注表.xlsx"


def load_private_bills() -> pd.DataFrame:
    """读取 private/ 里所有账单（标注表除外），解析 + 清洗。"""
    files = [p for p in sorted(PRIVATE.glob("*")) if p.suffix.lower() in (".csv", ".xlsx") and p != LABEL_SHEET
             and not p.name.startswith(("~$", "评测"))]
    if not files:
        sys.exit(f"private/ 里没有账单文件：{PRIVATE}")
    kept, _ = clean(pd.concat([parse_bill(p.name, p.read_bytes()) for p in files], ignore_index=True))
    print(f"读取了 {len(files)} 个账单文件，共 {len(kept)} 笔有效交易")
    return kept
