"""金额的显示格式：统一写成「1,234.50 元」。

不用「¥」：人民币和日元都用这个符号，容易被看成日元（苏宇晨测试时提出）。
"""

YUAN_COLUMN_FORMAT = "%.2f 元"   # 给表格的 NumberColumn 用


def yuan(amount: float, digits: int = 2) -> str:
    """把金额写成「1,234.50 元」。"""
    return f"{amount:,.{digits}f} 元"
