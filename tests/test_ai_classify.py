"""AI 分类的测试。用一个假的 AI 客户端，不联网、不花钱。"""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from core.ai_classify import SOURCE_AI, AIError, ai_classify
from core.classify import SOURCE_RULE, classify
from core.filters import SOURCE_MANUAL


class FakeAI:
    """假的 AI：按商家名里的词回答；记录每次收到了什么。"""

    def __init__(self, answers=None, fail=False, bad_json=False):
        self.answers = answers or {"烘焙": "餐饮", "货柜": "零食饮品", "小绿车": "交通", "洗衣": "生活服务"}
        self.fail, self.bad_json = fail, bad_json
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        if self.fail:
            raise ConnectionError("network down")
        items = json.loads(kwargs["messages"][1]["content"])
        self.requests.append(items)
        results = []
        for it in items:
            text = it["商家"] + it["商品"]
            category = next((c for k, c in self.answers.items() if k in text), "其他")
            results.append({"i": it["i"], "category": category})
        content = "这不是 JSON" if self.bad_json else json.dumps({"results": results}, ensure_ascii=False)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def tx(i, counterparty, item="", direction="支出", category=None, source=None, raw_type="扫二维码付款"):
    return {"id": f"t{i}", "time": pd.Timestamp("2026-10-01"), "amount": 9.9, "direction": direction,
            "counterparty": counterparty, "item": item, "platform": "微信", "pay_method": "零钱",
            "status": "支付成功", "raw_type": raw_type, "category": category, "category_source": source}


@pytest.fixture
def df():
    return pd.DataFrame([
        tx(1, "金玺烘焙", "收款方备注:二维码收款"),
        tx(2, "金玺烘焙", "收款方备注:二维码收款"),          # 和上一笔一样，只问一次
        tx(3, "恒生活智能货柜", "先选购后付款"),
        tx(4, "第一食堂", category="餐饮", source=SOURCE_RULE),   # 规则已经分好
        tx(5, "燕燕家电", "快速洗-付款", category="其他", source=SOURCE_MANUAL),  # 手动改过
        tx(6, "阿杰", "/", direction="收入"),                  # 收入不分类
    ])


def test_only_unclassified_spending_is_sent(df):
    ai = FakeAI()
    out, stats = ai_classify(df, ai)
    sent = [it["商家"] for batch in ai.requests for it in batch]
    assert sorted(sent) == ["恒生活智能货柜", "金玺烘焙"]          # 去重了；规则分好的、手动的、收入都没发
    assert stats.asked == 2 and stats.classified == 3

    out = out.set_index("id")
    assert out.loc["t1", "category"] == "餐饮" and out.loc["t1", "category_source"] == SOURCE_AI
    assert out.loc["t2", "category"] == "餐饮"
    assert out.loc["t3", "category"] == "零食饮品"
    assert out.loc["t4", "category_source"] == SOURCE_RULE         # 规则结果不动
    assert out.loc["t5", "category"] == "其他"                     # 手动结果不动
    assert pd.isna(out.loc["t6", "category"])                      # 收入不动


def test_only_merchant_item_and_type_are_sent(df):
    ai = FakeAI()
    ai_classify(df, ai)
    assert set(ai.requests[0][0]) == {"i", "商家", "商品", "平台分类"}   # 没有金额、时间、支付方式


def test_pure_ai_mode_reclassifies_everything_except_manual(df):
    ai = FakeAI()
    out, _ = ai_classify(df, ai, only_unclassified=False)
    out = out.set_index("id")
    assert out.loc["t4", "category_source"] == SOURCE_AI          # 「纯 AI」评测时，规则分好的也重新问
    assert out.loc["t5", "category_source"] == SOURCE_MANUAL


def test_batches(df):
    many = pd.DataFrame([tx(i, f"小店{i}") for i in range(95)])
    ai = FakeAI()
    _, stats = ai_classify(many, ai, batch_size=40)
    assert [len(b) for b in ai.requests] == [40, 40, 15]
    assert stats.prompt_tokens == 300 and stats.cost_yuan > 0


def test_unknown_category_is_ignored(df):
    ai = FakeAI(answers={"烘焙": "吃饭"})                        # 不在分类列表里
    out, stats = ai_classify(df, ai)
    assert out.set_index("id").loc["t1", "category"] is None or pd.isna(out.set_index("id").loc["t1", "category"])
    assert "吃饭" in stats.invalid


def test_errors_are_friendly(df):
    with pytest.raises(AIError, match="调用 AI 失败"):
        ai_classify(df, FakeAI(fail=True))
    with pytest.raises(AIError, match="格式不对"):
        ai_classify(df, FakeAI(bad_json=True))


def test_nothing_to_do_makes_no_request():
    done = classify(pd.DataFrame([tx(1, "第一食堂")]))
    ai = FakeAI()
    _, stats = ai_classify(done, ai)
    assert ai.requests == [] and stats.asked == 0


def test_does_not_modify_input(df):
    before = df.copy()
    ai_classify(df, FakeAI())
    pd.testing.assert_frame_equal(df, before)
