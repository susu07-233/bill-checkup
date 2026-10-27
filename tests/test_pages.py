"""冒烟测试：确认每个页面都能正常打开、不报错。

运行方式：uv run pytest
AppTest 是 Streamlit 自带的测试工具，不用开浏览器就能把页面跑一遍。
首页里有跳转到其他页面的链接，只有通过 app.py（导航）运行才有效，所以首页通过 app.py 测。
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent
PAGES = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "app_pages").glob("*.py") if p.name != "home.py")


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = AppTest.from_file(str(ROOT / page)).run()
    assert not at.exception, f"{page} 运行出错：{at.exception}"


def test_app_opens_on_home_page():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not at.exception
    assert at.title[0].value == "账单体检"


def test_demo_button_goes_to_dashboard():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    next(b for b in at.button if "示例账单" in b.label).click().run()
    assert not at.exception
    assert len(at.session_state["transactions"]) > 400
    assert at.title[0].value == "消费看板"


def test_sidebar_shows_current_data():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert any("还没有导入账单" in c.value for c in at.sidebar.caption)

    next(b for b in at.button if "示例账单" in b.label).click().run()
    df = at.session_state["transactions"]
    assert any(m.value == f"### {len(df)} 笔" for m in at.sidebar.markdown)
    assert any("示例数据" in c.value for c in at.sidebar.caption)

    next(b for b in at.sidebar.button if b.label == "清空数据").click().run()
    assert "transactions" not in at.session_state
