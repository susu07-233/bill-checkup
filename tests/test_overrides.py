"""手动修改（不计入、手动分类）保存与套用的测试。"""

import pandas as pd
import pytest

from core.classify import classify
from core.clean import totals
from core.filters import SOURCE_MANUAL
from core.overrides import (
    SOURCE_EXCLUDED,
    apply_overrides,
    exclude,
    is_manually_excluded,
    load_overrides,
    record_category,
    restore,
    save_overrides,
)


def tx(id_, counterparty, amount, direction="支出", raw_type="商户消费"):
    return {"id": id_, "time": pd.Timestamp("2026-10-03"), "amount": amount, "direction": direction,
            "counterparty": counterparty, "item": "", "platform": "微信", "pay_method": "零钱",
            "status": "支付成功", "raw_type": raw_type, "category": None, "category_source": None}


@pytest.fixture
def df():
    return classify(pd.DataFrame([
        tx("big", "某同学", 1525.75, raw_type="转账"),        # 规则分到社交
        tx("food", "第一食堂", 12.0),
        tx("yeb", "余额宝", 300.0, direction="不计收支"),
    ]))


def test_exclude_removes_from_spending(df):
    assert totals(df)["支出"] == 1537.75
    out, ov = exclude(df, {}, ["big"])
    row = out.set_index("id").loc["big"]
    assert row["direction"] == "不计收支" and row["category_source"] == SOURCE_EXCLUDED
    assert totals(out)["支出"] == 12.0
    assert ov == {"big": {"exclude": True, "original_direction": "支出"}}
    assert is_manually_excluded(out).sum() == 1


def test_exclude_ignores_already_neutral(df):
    out, ov = exclude(df, {}, ["yeb"])
    assert ov == {}
    pd.testing.assert_frame_equal(out, df)


def test_restore_brings_back_direction_and_rule_category(df):
    out, ov = exclude(df, {}, ["big"])
    back, ov = restore(out, ov, ["big"], classify)
    row = back.set_index("id").loc["big"]
    assert row["direction"] == "支出" and row["category"] == "社交"
    assert totals(back)["支出"] == 1537.75
    assert ov == {"big": {}}


def test_saved_changes_are_reapplied_after_reimport(df, tmp_path):
    path = tmp_path / "手动修改.json"
    out, ov = exclude(df, {}, ["big"])
    ov = record_category(ov, ["food"], "零食饮品")
    save_overrides(ov, path)

    reimported = apply_overrides(df, load_overrides(path))         # 模拟下次重新导入
    r = reimported.set_index("id")
    assert r.loc["big", "direction"] == "不计收支"
    assert r.loc["food", "category"] == "零食饮品" and r.loc["food", "category_source"] == SOURCE_MANUAL


def test_manual_category_survives_reclassify(df):
    ov = record_category({}, ["food"], "零食饮品")
    out = classify(apply_overrides(df, ov))                         # 再跑一次规则也不会覆盖
    assert out.set_index("id").loc["food", "category"] == "零食饮品"


def test_clear_manual_category():
    ov = record_category({"a": {"category": "餐饮"}}, ["a"], None)
    assert ov == {"a": {}}


def test_missing_or_broken_file_is_empty(tmp_path):
    assert load_overrides(tmp_path / "没有.json") == {}
    bad = tmp_path / "坏.json"
    bad.write_text("{不是 json", encoding="utf-8")
    assert load_overrides(bad) == {}


def test_saved_file_contains_only_ids_and_changes(df, tmp_path):
    path = tmp_path / "手动修改.json"
    _, ov = exclude(df, {}, ["big"])
    save_overrides(ov, path)
    text = path.read_text(encoding="utf-8")
    assert "某同学" not in text and "1525" not in text              # 不存交易内容


def test_online_version_does_not_save_to_shared_file(df, tmp_path):
    """部署到网上时没有 private/ 文件夹：不保存，免得所有访客的修改混在一个文件里。"""
    path = tmp_path / "private" / "手动修改.json"          # private/ 不存在
    _, ov = exclude(df, {}, ["big"])
    save_overrides(ov, path)
    assert not path.exists() and not path.parent.exists()
