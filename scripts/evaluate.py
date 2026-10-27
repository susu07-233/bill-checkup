"""评测规则分类：拿标注表里的「正确分类」，和规则分类的结果对比。

运行：uv run python scripts/evaluate.py
输出：
  - 终端打印主要数字
  - docs/评测结果.md            只有汇总数字，不含商家名等个人信息，可以公开
  - private/评测结果_详细.md    包含每一笔分错的交易，只在本地

指标：
  - 覆盖率：规则能给出分类的比例（剩下的是「未分类」，留给第 8 步 AI）
  - 准确率：分对的笔数 / 全部标注笔数（未分类算错）
  - 规则命中准确率：分对的笔数 / 规则给出了分类的笔数（规则「敢说的时候」有多准）
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from common import LABEL_SHEET, PRIVATE, ROOT, load_private_bills
from core.classify import classify, load_rules, match_rule
from core.schema import CATEGORIES

UNCLASSIFIED = "未分类"


def read_labels(path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit("还没有标注表，先运行：uv run python scripts/make_label_sheet.py")
    labels = pd.read_excel(path, sheet_name="标注", dtype=str)
    labels = labels[labels["正确分类"].isin(CATEGORIES)][["编号", "正确分类", "备注（可不填）"]]
    if labels.empty:
        raise SystemExit("标注表里还没有填任何分类")
    return labels.rename(columns={"编号": "id", "正确分类": "truth", "备注（可不填）": "note"})


def main():
    # 调试用：uv run python scripts/evaluate.py 某个标注表.xlsx 输出目录 —— 结果写到输出目录，不动 docs/
    sheet = Path(sys.argv[1]) if len(sys.argv) > 1 else LABEL_SHEET
    public_out = Path(sys.argv[2]) / "评测结果.md" if len(sys.argv) > 2 else ROOT / "docs" / "评测结果.md"
    detail_out = Path(sys.argv[2]) / "评测结果_详细.md" if len(sys.argv) > 2 else PRIVATE / "评测结果_详细.md"

    labels = read_labels(sheet)
    bills = load_private_bills()
    # 重新跑规则分类（忽略网页上的手动修改）
    bills = bills.assign(category=None, category_source=None)
    rules = load_rules()
    predicted = classify(bills, rules)

    data = labels.merge(predicted, on="id", how="left")
    missing = data["direction"].isna().sum()
    if missing:
        print(f"⚠️ 有 {missing} 笔标注在账单里找不到（账单文件可能换过），已跳过")
        data = data[data["direction"].notna()]

    data["pred"] = data["category"].fillna(UNCLASSIFIED)
    data["correct"] = data["pred"] == data["truth"]
    data["rule"] = data.apply(lambda r: match_rule(r, rules), axis=1)

    n = len(data)
    covered = data[data["pred"] != UNCLASSIFIED]
    accuracy = data["correct"].mean()
    coverage = len(covered) / n
    precision = covered["correct"].mean() if len(covered) else 0.0

    # 按「正确分类」统计每一类
    per_cat = (data.groupby("truth")
               .agg(笔数=("id", "size"), 分对=("correct", "sum"),
                    未分类=("pred", lambda s: (s == UNCLASSIFIED).sum()))
               .reindex(CATEGORIES).dropna().astype(int))
    per_cat["准确率"] = (per_cat["分对"] / per_cat["笔数"]).map("{:.0%}".format)

    # 分错的类型：正确是 A，规则分成了 B
    wrong = data[~data["correct"] & (data["pred"] != UNCLASSIFIED)]
    confusion = (wrong.groupby(["truth", "pred"]).size().sort_values(ascending=False)
                 .rename("笔数").reset_index().rename(columns={"truth": "正确分类", "pred": "规则分成了"}))

    summary = [
        f"# 分类评测结果（规则分类 v1）",
        "",
        f"- 评测日期：{date.today()}",
        f"- 评测集：苏宇晨真实账单中随机抽取的 **{n} 笔支出**，由苏宇晨人工标注正确分类",
        f"- 规则数：{len(rules)} 条（写规则时没有看过这份真实账单，避免准确率虚高）",
        "",
        "| 指标 | 数值 | 含义 |",
        "|---|---|---|",
        f"| **准确率** | **{accuracy:.0%}** | 分对的笔数 / 全部 {n} 笔（未分类算错） |",
        f"| 覆盖率 | {coverage:.0%} | 规则能给出分类的比例；剩下 {n - len(covered)} 笔留给第 8 步 AI |",
        f"| 规则命中准确率 | {precision:.0%} | 规则给出分类时，分对的比例 |",
        "",
        "## 每个分类的表现",
        "",
        per_cat.to_markdown(),
        "",
        "## 最常见的分错",
        "",
        confusion.head(10).to_markdown(index=False) if len(confusion) else "没有分错的（只有未分类）",
        "",
    ]
    public = "\n".join(summary)
    public_out.write_text(public, encoding="utf-8")

    def describe(r):
        rule = f"第 {r['rule'].line} 行「{r['rule'].field}含{r['rule'].keyword}」" if r["rule"] else "没有匹配的规则"
        note = f"（备注：{r['note']}）" if isinstance(r["note"], str) and r["note"].strip() else ""
        return f"| {r['counterparty']} | {r['item']} | {r['amount']:.2f} | {r['truth']} | {r['pred']} | {rule}{note} |"

    errors = data[~data["correct"]].sort_values(["truth", "pred"])
    detail = public + "\n".join([
        "## 每一笔分错 / 没分出来的交易（只在本地，不上传）",
        "",
        "| 交易对方 | 商品 | 金额 | 正确分类 | 规则结果 | 原因 |",
        "|---|---|---|---|---|---|",
        *errors.apply(describe, axis=1).tolist(),
        "",
    ])
    detail_out.write_text(detail, encoding="utf-8")

    print(f"\n准确率 {accuracy:.0%} ｜ 覆盖率 {coverage:.0%} ｜ 规则命中准确率 {precision:.0%}（共 {n} 笔）")
    print(f"汇总已写入 {public_out}；分错的明细在 {detail_out}")


if __name__ == "__main__":
    main()
