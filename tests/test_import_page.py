"""导入页的测试：点「用示例账单试试」后，应该解析、清洗出和直接调用函数一样的结果。"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from core.clean import clean, totals
from core.demo import demo_files
from core.parse import parse_bill

PAGE = Path(__file__).parent.parent / "pages" / "1_导入.py"


def test_sample_button_loads_demo_data():
    kept, removed = clean(pd.concat([parse_bill(n, b) for n, b in demo_files()], ignore_index=True))

    at = AppTest.from_file(str(PAGE)).run()
    sample_button = next(b for b in at.button if "示例账单" in b.label)
    sample_button.click().run()

    assert not at.exception
    assert len(at.session_state["transactions"]) == len(kept)
    assert len(at.session_state["removed"]) == len(removed)
    assert at.metric[0].value == f"{len(kept)} 笔"
    assert at.metric[1].value == f"¥{totals(kept)['支出']:,.2f}"
    assert f"已自动排除 {len(removed)} 笔" in at.expander[0].label
