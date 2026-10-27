"""日子类型：工作日 / 周末 / 节假日（按中国法定节假日，含调休）。

节假日数据来自开源库 chinesecalendar（每年国务院公布安排后更新），不手写，避免算错调休：
  - 节假日：在法定假期里（比如国庆 10/1–10/7，包括其中的周末）
  - 周末：普通的周六、周日（调休要上班的周末不算）
  - 工作日：其余的日子（包括调休上班的周六、周日）
库里没有的年份（太早或太新），只按周几判断周末。
"""

from datetime import date
from functools import lru_cache

import chinese_calendar
import pandas as pd

WORKDAY, WEEKEND, HOLIDAY = "工作日", "周末", "节假日"
DAY_TYPES = [WORKDAY, WEEKEND, HOLIDAY]

HOLIDAY_NAMES = {
    "New Year's Day": "元旦", "Spring Festival": "春节", "Tomb-sweeping Day": "清明",
    "Labour Day": "劳动节", "Dragon Boat Festival": "端午", "Mid-autumn Festival": "中秋",
    "National Day": "国庆", "Anti-Fascist 70th Day": "抗战胜利纪念日",
}


@lru_cache(maxsize=4096)
def day_info(day: date) -> tuple[str, str | None]:
    """返回（日子类型, 节日名）。节日名只有节假日才有。"""
    try:
        off, name = chinese_calendar.get_holiday_detail(day)
    except NotImplementedError:              # 库里没有这一年
        return (WEEKEND if day.weekday() >= 5 else WORKDAY), None
    if not off:
        return WORKDAY, None                 # 包括调休上班的周末
    if name:
        return HOLIDAY, HOLIDAY_NAMES.get(name, name)
    return WEEKEND, None


def day_type(day: date) -> str:
    return day_info(day)[0]


def day_types(dates: pd.Series) -> pd.Series:
    """给一列日期（Timestamp）标上日子类型。"""
    return dates.map(lambda t: day_type(t.date()))


def holiday_names(df: pd.DataFrame) -> list[str]:
    """这段时间里有哪些节假日，比如 ["中秋", "国庆"]。"""
    if df.empty:
        return []
    names = []
    for t in pd.date_range(df["time"].min().normalize(), df["time"].max().normalize(), freq="D"):
        kind, name = day_info(t.date())
        if kind == HOLIDAY and name and name not in names:
            names.append(name)
    return names


def count_days(start: date, end: date) -> dict[str, int]:
    """start 到 end（含）之间，三类日子各有几天。算「日均」要用：周末花的钱要除以周末的天数。"""
    counts = {t: 0 for t in DAY_TYPES}
    for t in pd.date_range(start, end, freq="D"):
        counts[day_type(t.date())] += 1
    return counts
