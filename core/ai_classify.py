"""AI 分类：把规则认不出的支出交给大模型（DeepSeek），让它从固定的分类里选一个。

隐私：
  - 只发「商家名、商品名、平台分类」三样，不发时间、金额、支付方式、交易单号
  - 只发支出；转账、红包、AA 已经被规则分到「社交」，不会发出去（朋友的名字不会外传）
  - 同样的「商家 + 商品」只问一次

用法：
  client = make_client(api_key)
  df, stats = ai_classify(df, client)                 # 只补规则没分出来的
  df, stats = ai_classify(df, client, only_unclassified=False)  # 评测「纯 AI」时用

client 只要有 client.chat.completions.create(...) 就行，测试时可以换成假的。
"""

import json
from dataclasses import dataclass, field

import pandas as pd

from core.filters import SOURCE_MANUAL
from core.schema import CATEGORIES

SOURCE_AI = "AI"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
BATCH_SIZE = 40

# 分类说明只用产品决策 Q5、Q7 里定下的定义和通用例子，不放评测集里出现过的商家，避免准确率虚高
SYSTEM_PROMPT = f"""你是一个记账助手，帮一位中国大学生给消费记录分类。
每条记录给出「商家」「商品」「平台分类」，请判断这笔钱花在了什么上，从下面的分类里选一个：

餐饮：食堂、外卖、餐馆
零食饮品：奶茶、咖啡、零食、饮料、便利店
购物：网购、超市、日用品、衣服、数码
交通：公交地铁、打车、火车票
娱乐：电影、游戏、网吧、视频和音乐会员
生活服务：话费、水电、洗衣、充电、充电宝、快递
学习：教材、打印、考试报名、网课
医疗：药店、医院
社交：转账、红包、AA
其他：以上都不是，或者实在判断不了

规则：
1. 按「买了什么」分，不按「在哪买」分。比如在京东买教材 → 学习，在京东买耳机 → 购物。
2. 只能用上面这 {len(CATEGORIES)} 个分类名，原样输出。
3. 只输出 JSON，格式：{{"results": [{{"i": 编号, "category": "分类"}}]}}，每条记录都要有结果。"""


class AIError(Exception):
    """调用 AI 失败（没联网、Key 不对、余额不足等）。"""


@dataclass
class AIStats:
    asked: int = 0             # 发给 AI 的不同「商家 + 商品」组合数
    classified: int = 0        # 因此分上类的交易笔数
    prompt_tokens: int = 0
    completion_tokens: int = 0
    invalid: list[str] = field(default_factory=list)   # AI 返回了不认识的分类

    @property
    def cost_yuan(self) -> float:
        """粗略估算费用（按 DeepSeek 公开价：输入约 2 元 / 百万 token，输出约 8 元 / 百万 token）。"""
        return self.prompt_tokens / 1e6 * 2 + self.completion_tokens / 1e6 * 8


def make_client(api_key: str, base_url: str = DEFAULT_BASE_URL):
    """创建 AI 客户端。DeepSeek 的接口和 OpenAI 兼容，所以用 openai 这个包。"""
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=base_url, timeout=60)


def _clean_text(value) -> str:
    text = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    return "" if text in ("/", "nan") else text


def _ask(client, model: str, items: list[dict], stats: AIStats) -> dict[int, str]:
    """问一批，返回 {编号: 分类}。"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except Exception as e:  # 网络、Key、余额等问题，统一转成好懂的提示
        raise AIError(f"调用 AI 失败：{e}") from e

    usage = getattr(response, "usage", None)
    if usage:
        stats.prompt_tokens += usage.prompt_tokens or 0
        stats.completion_tokens += usage.completion_tokens or 0

    try:
        results = json.loads(response.choices[0].message.content)["results"]
    except (json.JSONDecodeError, KeyError, TypeError, IndexError) as e:
        raise AIError(f"AI 返回的格式不对：{e}") from e

    answers = {}
    for r in results:
        category = str(r.get("category", "")).strip()
        if category in CATEGORIES:
            answers[int(r["i"])] = category
        else:
            stats.invalid.append(category)
    return answers


def ai_classify(
    df: pd.DataFrame,
    client,
    model: str = DEFAULT_MODEL,
    only_unclassified: bool = True,
    batch_size: int = BATCH_SIZE,
) -> tuple[pd.DataFrame, AIStats]:
    """用 AI 给支出分类，返回（新表, 统计）。不改原表；手动分类的永远不动。"""
    df = df.copy()
    stats = AIStats()

    target = (df["direction"] == "支出") & (df["category_source"] != SOURCE_MANUAL)
    if only_unclassified:
        target &= df["category"].isna()
    if not target.any():
        return df, stats

    # 同样的「商家 + 商品 + 平台分类」只问一次
    keys = df.loc[target].apply(
        lambda r: (_clean_text(r["counterparty"]), _clean_text(r["item"]), _clean_text(r["raw_type"])), axis=1
    )
    unique_keys = list(dict.fromkeys(keys))
    stats.asked = len(unique_keys)

    answers: dict[tuple, str] = {}
    for start in range(0, len(unique_keys), batch_size):
        batch = unique_keys[start:start + batch_size]
        items = [{"i": i, "商家": k[0], "商品": k[1], "平台分类": k[2]} for i, k in enumerate(batch)]
        for i, category in _ask(client, model, items, stats).items():
            if 0 <= i < len(batch):
                answers[batch[i]] = category

    result = keys.map(answers)                      # 没拿到答案的是 NaN
    got = result.notna()
    idx = result[got].index
    df.loc[idx, "category"] = result[got]
    df.loc[idx, "category_source"] = SOURCE_AI
    stats.classified = int(got.sum())
    return df, stats
