"""首页「好奇心问题」的测试。"""

import pandas as pd
import pytest

from core.classify import classify
from core.clean import clean
from core.curiosity import QUESTIONS, biggest_day, favorite_shop, latest_month, milk_tea
from core.demo import demo_files
from core.parse import parse_bill


@pytest.fixture(scope="module")
def df():
    return classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])


def test_latest_month(df):
    assert latest_month(df) == "2026-10"


def test_milk_tea(df):
    a = milk_tea(df, "2026-10")
    assert a["amount"] == round(a["rows"]["amount"].sum(), 2) > 0
    assert set(a["rows"]["counterparty"]) <= {"蜜雪冰城", "喜茶", "古茗", "瑞幸咖啡"}   # 瑞幸只算商品是奶茶的那几笔
    assert len(a["items"]) <= 3 and f"{len(a['rows'])} 笔" in a["note"]


def test_milk_tea_excludes_tea_leaves():
    rows = pd.DataFrame([
        {"id": "a", "time": pd.Timestamp("2026-10-02"), "amount": 12.0, "direction": "支出", "counterparty": "爷爷不泡茶",
         "item": "外卖订单", "platform": "微信", "pay_method": "零钱", "status": "", "raw_type": "", "category": "餐饮",
         "category_source": "AI"},
        {"id": "b", "time": pd.Timestamp("2026-10-03"), "amount": 30.0, "direction": "支出", "counterparty": "超市",
         "item": "西湖龙井茶叶", "platform": "微信", "pay_method": "零钱", "status": "", "raw_type": "", "category": "零食饮品",
         "category_source": "规则"},
    ])
    a = milk_tea(rows, "2026-10")
    assert list(a["rows"]["id"]) == ["a"]                    # 本地奶茶店算，茶叶不算


def test_favorite_shop_skips_friends(df):
    a = favorite_shop(df, "2026-10")
    friends = set(df.loc[df["category"] == "社交", "counterparty"])
    assert a["title"].split("「")[1].rstrip("」") not in friends
    assert "次" in a["note"]


def test_biggest_day(df):
    a = biggest_day(df, "2026-10")
    assert a["amount"] == round(a["rows"]["amount"].sum(), 2)
    assert a["rows"]["date"].nunique() == 1


def test_all_questions_answer(df):
    for question, answer in QUESTIONS.items():
        result = answer(df, "2026-10")
        assert result["title"] and result["note"], question


def test_discoveries_have_evidence(df):
    from core.curiosity import discoveries
    found = discoveries(df)
    assert 4 <= len(found) <= 6
    assert any("周末平均每天花" in f["text"] for f in found)              # 示例数据周末明显花得多
    top = found[0]
    assert "钱最多花在" in top["text"] and len(top["rows"]) > 0
    cat = top["text"].split("「")[1].split("」")[0]
    assert (top["rows"]["category"] == cat).all()                      # 点开看到的就是这个分类的交易
    assert all({"icon", "text", "rows"} <= set(f) for f in found)
    assert "可以省" not in " ".join(f["text"] for f in found)            # 语气：不说「该省」


def test_discoveries_empty_when_no_spending(df):
    from core.curiosity import discoveries
    assert discoveries(df[df["direction"] == "收入"]) == []


def test_delivery_orders_show_the_shop_name():
    from core.curiosity import _shop_name
    row = {"counterparty": "饿了么", "item": "爷爷不泡茶上饶铅山辛弃疾广场店外卖订单"}
    assert _shop_name(row).startswith("爷爷不泡茶")
    assert _shop_name({"counterparty": "古茗", "item": "奶茶"}) == "古茗"
