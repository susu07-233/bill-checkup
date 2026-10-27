"""规则分类：按 core/rules.csv 里的规则，给每笔支出自动分类。

规则表从上往下匹配，第一条匹配上的规则生效。规则表的顺序就是优先级：
  1. 交易类型（转账、红包、AA）→ 社交
  2. 商品名里的关键词（先看「买了什么」：京东买教材 → 学习）
  3. 商家名里的关键词（商品看不出来，再看「在哪买」：京东 → 购物）
  4. 支付宝自带的分类（微信账单没有这一栏）
都匹配不上 → 不分类（页面上显示「未分类」，第 8 步交给 AI）。

其他约定：
  - 只给「支出」分类（包括跨月退款这种负数支出）；收入、不计收支不分类
  - 用户手动改过的分类（category_source == "手动"）不会被覆盖
  - 关键词不区分大小写；「支付宝分类」要求完全一致，并且只看支付宝的交易
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.filters import SOURCE_MANUAL
from core.schema import CATEGORIES

RULES_FILE = Path(__file__).parent / "rules.csv"
SOURCE_RULE = "规则"

# 规则表里的「字段」→ 交易表里的列
FIELD_COLUMNS = {"交易类型": "raw_type", "商品": "item", "商家": "counterparty", "支付宝分类": "raw_type"}


@dataclass(frozen=True)
class Rule:
    line: int          # 在规则表里是第几行（方便排查是哪条规则分的）
    field: str
    keyword: str
    category: str

    def matches(self, row: pd.Series) -> bool:
        value = str(row[FIELD_COLUMNS[self.field]] or "")
        if self.field == "支付宝分类":
            return row["platform"] == "支付宝" and value == self.keyword
        return self.keyword.lower() in value.lower()


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    """读规则表。用 Excel 改过、另存为 GBK 编码也能读。"""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gb18030")
    table = pd.read_csv(pd.io.common.StringIO(text), dtype=str, keep_default_na=False)

    rules = []
    for i, r in table.iterrows():
        field, keyword, category = r["字段"].strip(), r["关键词"].strip(), r["分类"].strip()
        if not keyword:
            continue
        if field not in FIELD_COLUMNS:
            raise ValueError(f"规则表第 {i + 2} 行：字段「{field}」不认识，只能是 {list(FIELD_COLUMNS)}")
        if category not in CATEGORIES:
            raise ValueError(f"规则表第 {i + 2} 行：分类「{category}」不在分类列表里：{CATEGORIES}")
        rules.append(Rule(line=i + 2, field=field, keyword=keyword, category=category))
    return rules


def match_rule(row: pd.Series, rules: list[Rule]) -> Rule | None:
    """找到第一条匹配的规则；都不匹配返回 None。"""
    return next((rule for rule in rules if rule.matches(row)), None)


def classify(df: pd.DataFrame, rules: list[Rule] | None = None) -> pd.DataFrame:
    """给支出自动分类，返回新表（不改原表）。手动分类的保留不动。"""
    rules = load_rules() if rules is None else rules
    df = df.copy()

    to_classify = (df["direction"] == "支出") & (df["category_source"] != SOURCE_MANUAL)
    matched = df[to_classify].apply(lambda row: match_rule(row, rules), axis=1)

    df.loc[to_classify, "category"] = matched.map(lambda r: r.category if r else None)
    df.loc[to_classify, "category_source"] = matched.map(lambda r: SOURCE_RULE if r else None)
    return df


def coverage(df: pd.DataFrame) -> float:
    """支出里有多少比例已经有分类（0–1）。"""
    spend = df[df["direction"] == "支出"]
    return float(spend["category"].notna().mean()) if len(spend) else 0.0
