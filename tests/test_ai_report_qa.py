"""AI 月报、问一问的测试。用假的 AI 客户端，不联网、不花钱。"""

import json
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from core.ai_classify import AIError
from core.ai_report import generate_report, report_facts
from core.classify import classify
from core.clean import clean
from core.dashboard import in_month, kpis
from core.demo import demo_files
from core.parse import parse_bill
from core.qa import parse_question, run_query, validate


class FakeLLM:
    """假的大模型：返回固定内容，并记下收到了什么。"""

    def __init__(self, content="", fail=False):
        self.content, self.fail, self.sent = content, fail, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        if self.fail:
            raise ConnectionError("network down")
        self.sent.append(kwargs["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


@pytest.fixture(scope="module")
def df():
    return classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])


# ---------- 月报 ----------

def test_report_facts_numbers_match_dashboard(df):
    facts = report_facts(df, "2026-09")
    k = kpis(in_month(df, "2026-09"))
    assert facts["总支出"] == k["支出"]
    assert facts["弹性支出占比"] == f"{k['弹性占比']:.0%}"
    assert facts["上个月"]["月份"] == "2026-08"
    assert sum(c["金额"] for c in facts["各分类"]) == pytest.approx(k["支出"], abs=0.05)


def test_report_facts_keep_friends_private(df):
    text = json.dumps(report_facts(df, "2026-09"), ensure_ascii=False)
    friends = set(df.loc[df["category"] == "社交", "counterparty"])        # 转账、红包、AA 的对方
    assert friends and not any(name in text for name in friends)
    assert "4200" not in text                                             # 没有交易单号


def test_generate_report_sends_facts_and_strips_yen(df):
    ai = FakeLLM("**一句话总结**：这个月花了 ¥1,234.00 元。")
    facts = report_facts(df, "2026-09")
    text = generate_report(facts, ai, "m")
    assert "¥" not in text
    assert json.loads(ai.sent[0][1]["content"]) == json.loads(json.dumps(facts, ensure_ascii=False))


def test_generate_report_error_is_friendly(df):
    with pytest.raises(AIError, match="生成月报失败"):
        generate_report({}, FakeLLM(fail=True), "m")


# ---------- 问一问 ----------

def test_parse_question_sends_no_transactions():
    ai = FakeLLM(json.dumps({"start": "2026-09-01", "end": "2026-09-30", "categories": ["零食饮品"],
                             "keywords": ["奶茶", "蜜雪"], "metric": "sum", "understanding": "9月奶茶"}))
    spec = parse_question("上个月奶茶花了多少？", ai, "m", date(2026, 10, 27), date(2026, 5, 1), date(2026, 10, 26))
    assert spec["start"] == date(2026, 9, 1) and spec["metric"] == "sum"
    system, user = ai.sent[0]
    assert user["content"] == "上个月奶茶花了多少？"
    assert "2026-10-27" in system["content"] and "零食饮品" in system["content"]   # 只有日期、分类说明，没有账单
    assert len(ai.sent[0]) == 2                                                  # 除了说明和问题，什么都没发


def test_validate_fixes_bad_values():
    spec = validate({"start": "不是日期", "categories": ["吃饭", "餐饮"], "metric": "画图", "direction": "x"})
    assert spec["start"] is None and spec["categories"] == ["餐饮"]
    assert spec["metric"] == "sum" and spec["direction"] == "支出"
    assert validate({"unsupported": True, "understanding": "和账单无关"})["unsupported"]


def spec(**kw):
    return validate({"metric": "sum", **kw})


def test_sum_with_keywords(df):
    answer, table, rows = run_query(df, spec(start="2026-09-01", end="2026-09-30", keywords=["瑞幸", "蜜雪"]))
    expected = df[(df["direction"] == "支出") & df["counterparty"].isin(["瑞幸咖啡", "蜜雪冰城"])
                  & (df["time"].dt.month == 9)]
    assert len(rows) == len(expected)
    assert f"{expected['amount'].sum():,.2f} 元" in answer and table is None


def test_category_filter_and_count(df):
    answer, _, rows = run_query(df, spec(categories=["交通"], metric="count"))
    assert f"{(df['category'] == '交通').sum()} 笔" in answer
    assert set(rows["category"]) == {"交通"}


def test_top_merchants_table(df):
    answer, table, _ = run_query(df, spec(metric="top_merchants", start="2026-10-01", end="2026-10-31"))
    assert list(table.columns) == ["商家", "金额", "笔数"] and table["金额"].is_monotonic_decreasing
    assert table.iloc[0]["商家"] in answer


def test_by_month(df):
    _, table, _ = run_query(df, spec(metric="by_month", categories=["餐饮", "零食饮品"]))
    assert list(table["月份"]) == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def test_max_and_avg(df):
    answer, _, rows = run_query(df, spec(metric="max"))
    assert f"{rows['amount'].max():,.2f} 元" in answer
    answer, _, _ = run_query(df, spec(metric="avg_per_day", start="2026-09-01", end="2026-09-30"))
    assert "30 天" in answer


def test_no_match_and_unsupported(df):
    assert run_query(df, spec(keywords=["不存在的商家xyz"]))[0].startswith("没有找到符合条件的交易")
    outside = run_query(df, spec(start="2025-01-01", end="2025-01-31"))[0]
    assert "账单只有 2026-05-01 至 2026-10-26 的数据" in outside          # 告诉用户为什么没找到
    assert "回答不了" in run_query(df, {"unsupported": True, "understanding": "问天气"})[0]


def test_report_skips_comparison_with_partial_month(df):
    late_start = df[df["time"] >= "2026-08-25"]
    assert "上个月" not in report_facts(late_start, "2026-09")


# ---------- 问一问：让 AI 从账单商家里挑（找本地小店） ----------

def test_merchant_candidates_exclude_friends_and_respect_dates(df):
    from core.qa import merchant_candidates
    shops = merchant_candidates(df, spec(start="2026-09-01", end="2026-09-30"))
    friends = set(df.loc[df["category"] == "社交", "counterparty"])
    assert shops and not any(s.split("｜")[0] in friends for s in shops)
    assert len(shops) == len(set(shops))                                   # 去重了
    sept_shops = set(df.loc[df["time"].dt.month == 9, "counterparty"])
    assert all(s.split("｜")[0] in sept_shops for s in shops)              # 只有这个时间范围里的


def test_pick_merchants_finds_shops_keywords_miss(df):
    from core.qa import merchant_candidates, pick_merchants
    q = spec(start="2026-09-01", end="2026-09-30", keywords=["奶茶"], understanding="9月奶茶")
    candidates = merchant_candidates(df, q)
    wanted = [i for i, s in enumerate(candidates) if s.startswith(("古茗", "蜜雪冰城"))]
    ai = FakeLLM(json.dumps({"picked": wanted + [9999, "x"]}))            # 非法编号会被忽略
    q["picked"] = pick_merchants(q, candidates, ai, "m")
    assert set(q["picked"]) == {candidates[i] for i in wanted}
    sent = ai.sent[0][1]["content"]
    assert "金额" not in sent and "2026" not in sent                       # 只发商家名

    _, _, rows = run_query(df, q)
    by_keyword = (rows["counterparty"] + rows["item"]).str.contains("奶茶")
    from_pick = rows["counterparty"].isin(["古茗", "蜜雪冰城"])
    assert {"古茗", "蜜雪冰城"} <= set(rows["counterparty"])               # AI 挑中的店都算进来
    assert (by_keyword | from_pick).all()                                  # 每一笔要么关键词命中，要么是 AI 挑的店
    assert (~by_keyword & from_pick).any()                                 # 有关键词搜不到、靠 AI 挑出来的
