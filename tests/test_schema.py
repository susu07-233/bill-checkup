from core.schema import COLUMNS, COLUMN_LABELS, empty_table


def test_empty_table_has_all_columns():
    table = empty_table()
    assert list(table.columns) == COLUMNS

def test_every_column_has_label():
    assert list(COLUMN_LABELS.keys()) == COLUMNS
