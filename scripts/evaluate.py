"""评测分类效果：拿标注表里的「正确分类」，和程序的分类结果对比。

运行：uv run python scripts/evaluate.py
  - 没设置 DeepSeek Key：只评测「纯规则」
  - 设置了 Key（.streamlit/secrets.toml）：对比「纯规则 / 纯 AI / 规则 + AI」三种方案
    （只把标注过的那些交易发给 AI，100 笔大约几分钱）

输出：
  - 终端打印主要数字
  - docs/评测结果.md            只有汇总数字，不含商家名等个人信息，可以公开
  - private/评测结果_详细.md    包含每一笔分错的交易，只在本地

指标：
  - 准确率：分对的笔数 / 全部标注笔数（未分类算错）
  - 覆盖率：给出了分类的比例
  - 命中准确率：给出分类时，分对的比例
"""

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from common import LABEL_SHEET, PRIVATE, ROOT, load_ai_settings, load_private_bills
from core.ai_classify import ai_classify, make_client
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


def metrics(pred: pd.Series, truth: pd.Series) -> dict:
    covered = pred != UNCLASSIFIED
    correct = pred == truth
    return {"准确率": correct.mean(), "覆盖率": covered.mean(),
            "命中准确率": correct[covered].mean() if covered.any() else 0.0}


def main():
    # 调试用：uv run python scripts/evaluate.py 某个标注表.xlsx 输出目录 —— 结果写到输出目录，不动 docs/
    sheet = Path(sys.argv[1]) if len(sys.argv) > 1 else LABEL_SHEET
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    public_out = out_dir / "评测结果.md" if out_dir else ROOT / "docs" / "评测结果.md"
    detail_out = out_dir / "评测结果_详细.md" if out_dir else PRIVATE / "评测结果_详细.md"

    labels = read_labels(sheet)
    bills = load_private_bills().assign(category=None, category_source=None)   # 忽略网页上的手动修改
    data = labels.merge(bills, on="id", how="inner")
    if len(data) < len(labels):
        print(f"⚠️ 有 {len(labels) - len(data)} 笔标注在账单里找不到（账单文件可能换过），已跳过")
    n = len(data)

    rules = load_rules()
    by_rules = classify(data, rules)
    schemes = {"纯规则": by_rules["category"].fillna(UNCLASSIFIED)}
    costs = {"纯规则": ("—", "—")}

    settings = load_ai_settings()
    if settings:
        client = make_client(settings["api_key"], settings["base_url"])
        for name, base, only_unclassified in [("纯 AI", data, False), ("规则 + AI", by_rules, True)]:
            print(f"正在请 AI 分类（{name}）…")
            started = time.time()
            out, stats = ai_classify(base, client, model=settings["model"], only_unclassified=only_unclassified)
            schemes[name] = out["category"].fillna(UNCLASSIFIED)
            costs[name] = (f"{stats.asked} 个商家，{time.time() - started:.0f} 秒", f"¥{stats.cost_yuan:.4f}")
            if stats.invalid:
                print(f"  AI 返回了 {len(stats.invalid)} 个不认识的分类：{set(stats.invalid)}")
    else:
        print("没有设置 DeepSeek Key，只评测纯规则（Key 填在 .streamlit/secrets.toml）")

    # ---------- 汇总表 ----------
    rows = []
    for name, pred in schemes.items():
        m = metrics(pred, data["truth"])
        rows.append({"方案": name, "准确率": f"**{m['准确率']:.0%}**", "覆盖率": f"{m['覆盖率']:.0%}",
                     "命中准确率": f"{m['命中准确率']:.0%}", "AI 调用": costs[name][0], "费用": costs[name][1]})
        print(f"{name}：准确率 {m['准确率']:.0%} ｜ 覆盖率 {m['覆盖率']:.0%} ｜ 命中准确率 {m['命中准确率']:.0%}")
    comparison = pd.DataFrame(rows)

    # 每个分类、每种方案的准确率
    per_cat = pd.DataFrame({"笔数": data.groupby("truth").size()})
    for name, pred in schemes.items():
        per_cat[name] = (pred == data["truth"]).groupby(data["truth"]).mean().map("{:.0%}".format)
    per_cat = per_cat.reindex(CATEGORIES).dropna()
    per_cat["笔数"] = per_cat["笔数"].astype(int)
    per_cat.index.name = "正确分类"

    best = list(schemes)[-1]
    best_pred = schemes[best]
    wrong = data[(best_pred != data["truth"]) & (best_pred != UNCLASSIFIED)]
    confusion = (pd.DataFrame({"正确分类": wrong["truth"], f"{best}分成了": best_pred[wrong.index]})
                 .value_counts().rename("笔数").reset_index())

    public = "\n".join([
        "# 分类评测结果",
        "",
        f"- 评测日期：{date.today()}",
        f"- 评测集：苏宇晨真实账单中随机抽取的 **{n} 笔支出**，由苏宇晨人工标注正确分类",
        f"- 规则：{len(rules)} 条，写规则时没有看过这份真实账单；AI 的提示词也没有用到评测集里的商家",
        f"- AI 模型：{settings['model'] if settings else '未使用'}；只发送商家名、商品名、平台分类",
        "",
        "## 三种方案对比" if settings else "## 纯规则",
        "",
        comparison.to_markdown(index=False),
        "",
        "- 准确率 = 分对的笔数 / 全部笔数（没给出分类算错）",
        "- 覆盖率 = 给出了分类的比例",
        "- 命中准确率 = 给出分类时，分对的比例",
        "",
        "## 每个分类的准确率",
        "",
        per_cat.to_markdown(),
        "",
        f"## 最常见的分错（{best}）",
        "",
        confusion.head(10).to_markdown(index=False) if len(confusion) else "没有分错的",
        "",
    ])
    public_out.write_text(public, encoding="utf-8")

    # ---------- 本地明细 ----------
    def describe(i):
        r = data.loc[i]
        rule = match_rule(r, rules)
        rule_text = f"第 {rule.line} 行「{rule.field}含{rule.keyword}」" if rule else "无"
        note = f"（备注：{r['note']}）" if isinstance(r["note"], str) and r["note"].strip() else ""
        preds = " | ".join(schemes[s][i] for s in schemes)
        return f"| {r['counterparty']} | {r['item']} | {r['amount']:.2f} | {r['truth']} | {preds} | {rule_text}{note} |"

    any_wrong = pd.concat([(schemes[s] != data["truth"]) for s in schemes], axis=1).any(axis=1)
    detail = public + "\n".join([
        "## 至少一种方案分错的交易（只在本地，不上传）",
        "",
        f"| 交易对方 | 商品 | 金额 | 正确分类 | {' | '.join(schemes)} | 匹配的规则 |",
        "|---|---|---|---|" + "---|" * len(schemes) + "---|",
        *[describe(i) for i in data[any_wrong].sort_values("truth").index],
        "",
    ])
    detail_out.write_text(detail, encoding="utf-8")
    print(f"\n汇总已写入 {public_out}；分错的明细在 {detail_out}")


if __name__ == "__main__":
    main()
