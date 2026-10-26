"""冒烟测试：确认每个页面都能正常打开、不报错。

运行方式：uv run pytest
AppTest 是 Streamlit 自带的测试工具，不用开浏览器就能把页面跑一遍。
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent
PAGES = ["app.py", *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "pages").glob("*.py"))]


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = AppTest.from_file(str(ROOT / page)).run()
    assert not at.exception, f"{page} 运行出错：{at.exception}"
