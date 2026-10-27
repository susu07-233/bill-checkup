"""规则分类的测试。"""

import pandas as pd
import pytest

from core.classify import SOURCE_RULE, Rule, classify, coverage, load_rules, match_rule
from core.clean import clean
from core.demo import demo_files
from core.filters import SOURCE_MANUAL, set_category
from core.parse import parse_bill
from core.schema import CATEGORIES


def tx(counterparty="", item="", raw_type="商户消费", platform="微信", direction="支出", amount=10.0, **kw):
    """造一笔交易，方便写测试。"""
    return {"id": kw.get("id", f"t{counterparty}{item}"), "time": pd.Timestamp("2026-10-01"), "amount": amount,
            "direction": direction, "counterparty": counterparty, "item": item, "platform": platform,
            "pay_method": "零钱", "status": "支付成功", "raw_type": raw_type,
            "category": kw.get("category"), "category_source": kw.get("category_source")}


def category_of(**kwargs) -> str | None:
    return classify(pd.DataFrame([tx(**kwargs)])).iloc[0]["category"]


# ---------- 规则表本身 ----------

def test_rules_file_is_valid():
    rules = load_rules()
    assert len(rules) > 100
    assert {r.category for r in rules} <= set(CATEGORIES)


def test_bad_category_in_rules_file_is_reported(tmp_path):
    bad = tmp_path / "rules.csv"
    bad.write_text("字段,关键词,分类,说明\n商家,美团,吃饭,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="第 2 行"):
        load_rules(bad)


def test_rules_file_saved_by_excel_as_gbk_still_loads(tmp_path):
    gbk = tmp_path / "rules.csv"
    gbk.write_bytes("字段,关键词,分类,说明\n商家,美团,餐饮,\n".encode("gbk"))
    assert load_rules(gbk) == [Rule(line=2, field="商家", keyword="美团", category="餐饮")]


# ---------- 具体例子 ----------

@pytest.mark.parametrize("kwargs, expected", [
    # 先看商品，再看商家：同样是京东，教材算学习，耳机算购物
    (dict(counterparty="京东", item="大学英语教材"), "学习"),
    (dict(counterparty="京东", item="蓝牙耳机"), "购物"),
    (dict(counterparty="淘宝商家", item="零食大礼包"), "零食饮品"),
    # 商家
    (dict(counterparty="第一食堂", item="/"), "餐饮"),
    (dict(counterparty="瑞幸咖啡", item=""), "零食饮品"),
    (dict(counterparty="滴滴出行", item="快车行程"), "交通"),
    (dict(counterparty="中国移动", item="话费充值"), "生活缴费"),
    (dict(counterparty="STEAM", item=""), "娱乐"),          # 不区分大小写
    # 交易类型：转账、红包、AA 都是社交
    (dict(counterparty="阿杰", raw_type="转账"), "社交"),
    (dict(counterparty="小雨", raw_type="微信红包（单发）"), "社交"),
    (dict(counterparty="室友聚餐AA", raw_type="群收款"), "社交"),
    # 支付宝自带分类兜底
    (dict(counterparty="某某小店", raw_type="餐饮美食", platform="支付宝"), "餐饮"),
    (dict(counterparty="某某小店", raw_type="餐饮美食", platform="微信"), None),   # 微信没有这一栏，不能误用
    # 什么都匹配不上
    (dict(counterparty="张记杂货", item="/"), None),
])
def test_examples(kwargs, expected):
    assert category_of(**kwargs) == expected


def test_match_rule_tells_which_rule():
    rule = match_rule(pd.Series(tx(counterparty="京东", item="大学英语教材")), load_rules())
    assert rule.field == "商品" and rule.keyword == "教材"


# ---------- 分类的范围 ----------

def test_only_spending_is_classified():
    df = pd.DataFrame([
        tx(counterparty="美团", id="a"),
        tx(counterparty="美团", direction="收入", id="b"),
        tx(counterparty="余额宝", direction="不计收支", id="c"),
        tx(counterparty="中铁网络", amount=-156.0, id="d"),      # 跨月退款：负数支出，也要分类
    ])
    out = classify(df).set_index("id")
    assert out.loc["a", "category"] == "餐饮" and out.loc["a", "category_source"] == SOURCE_RULE
    assert out.loc["b", "category"] is None
    assert out.loc["c", "category"] is None
    assert out.loc["d", "category"] == "交通"


def test_manual_category_is_never_overwritten():
    df = pd.DataFrame([tx(counterparty="美团", category="社交", category_source=SOURCE_MANUAL)])
    out = classify(df).iloc[0]
    assert out["category"] == "社交" and out["category_source"] == SOURCE_MANUAL


def test_classify_does_not_modify_input():
    df = pd.DataFrame([tx(counterparty="美团")])
    before = df.copy()
    classify(df)
    pd.testing.assert_frame_equal(df, before)


def test_demo_data_fully_covered():
    kept, _ = clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))
    out = classify(kept)
    assert coverage(out) == 1.0
    # 手动改一笔再重新分类：手动的保留，其余照常
    manual = set_category(out, [out["id"].iloc[0]], "其他")
    again = classify(manual)
    assert again.iloc[0]["category"] == "其他" and again.iloc[0]["category_source"] == SOURCE_MANUAL
