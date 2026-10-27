"""统一交易表的结构定义……"""
import pandas as pd
# 统一后的列名（英文），顺序就是表格里列的顺序
COLUMNS =[
  "id","time","amount","direction","counterparty","item","platform","pay_method","status","raw_type","category","category_source",
]

# 界面上显示的中文名
COLUMN_LABELS ={
    "id": "编号", "time": "时间", "amount": "金额", "direction": "收/支",
    "counterparty": "交易对方", "item": "商品", "platform": "平台",
    "pay_method": "支付方式", "status": "状态", "raw_type": "平台分类",
    "category": "分类", "category_source": "分类来源",
}
DIRECTIONS = ["支出", "收入", "不计收支"]
PLATFORMS = ["微信", "支付宝"]
# 支出分类（产品决策 Q5、Q7，见 docs/改进清单.md）。原则：按「买了什么」分，不按「在哪买」分
CATEGORIES = ["餐饮", "零食饮品", "购物", "交通", "娱乐", "生活服务", "学习", "医疗", "社交", "其他"]

def empty_table() -> pd.DataFrame:
    """返回一张空的交易表（只有列名，没有数据）。"""
    return pd.DataFrame(columns=COLUMNS)
