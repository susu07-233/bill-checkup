"""所有测试共用的设置。"""

import pytest


@pytest.fixture(autouse=True)
def isolated_overrides_file(tmp_path, monkeypatch):
    """测试里的手动修改写到临时文件，绝不碰 private/手动修改.json（那是真实数据）。"""
    from core import overrides
    monkeypatch.setattr(overrides, "OVERRIDES_FILE", tmp_path / "手动修改.json")
