"""工作日 / 周末 / 节假日的测试。"""

from datetime import date

import pandas as pd
import pytest

from core.classify import classify
from core.clean import clean
from core.dashboard import by_day_type, kpis
from core.daytype import HOLIDAY, WEEKEND, WORKDAY, count_days, day_info, day_type
from core.demo import demo_files
from core.parse import parse_bill


@pytest.mark.parametrize("day, expected", [
    (date(2026, 10, 1), (HOLIDAY, "国庆")),
    (date(2026, 10, 4), (HOLIDAY, "国庆")),      # 国庆假期里的周日，算节假日不算周末
    (date(2026, 9, 27), (HOLIDAY, "中秋")),
    (date(2026, 10, 10), (WORKDAY, None)),       # 调休上班的周六，算工作日
    (date(2026, 10, 17), (WEEKEND, None)),       # 普通周六
    (date(2026, 10, 14), (WORKDAY, None)),       # 普通周三
    (date(2026, 2, 17), (HOLIDAY, "春节")),
])
def test_day_info(day, expected):
    assert day_info(day) == expected


def test_years_not_in_the_library_fall_back_to_weekends():
    assert day_type(date(1990, 1, 6)) == WEEKEND        # 周六
    assert day_type(date(1990, 1, 8)) == WORKDAY        # 周一


def test_count_days_october_2026():
    c = count_days(date(2026, 10, 1), date(2026, 10, 31))
    assert sum(c.values()) == 31
    assert c[HOLIDAY] == 7                               # 国庆 7 天
    assert c[WEEKEND] == 6                               # 10/17、18、24、25、31 + 10/11（周日）；10/10 调休上班


@pytest.fixture(scope="module")
def df():
    return classify(clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))[0])


def test_by_day_type_adds_up(df):
    t = by_day_type(df).set_index("day_type")
    assert round(t["amount"].sum(), 2) == kpis(df)["支出"]
    assert t["days"].sum() == kpis(df)["天数"]
    for _, r in t.iterrows():
        assert abs(r["daily"] - r["amount"] / r["days"]) < 0.01
        assert r["need_daily"] + r["flex_daily"] <= r["daily"] + 0.01


def test_demo_weekends_cost_more_per_day(df):
    """示例数据里小林周末爱点外卖、聚餐，周末日均应该比工作日高。"""
    t = by_day_type(df).set_index("day_type")
    assert t.loc[WEEKEND, "daily"] > t.loc[WORKDAY, "daily"]
