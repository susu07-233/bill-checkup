"""解析账单文件：把微信、支付宝导出的原始账单，转成统一的交易表（见 schema.py）。

所有函数都接收文件的原始内容（bytes），这样既能读本地文件，
也能直接处理 Streamlit 上传控件给的内容。
"""

import io

import pandas as pd

from core.schema import COLUMNS


# ---------- 公用小工具 ----------

def _find_header_row(rows: list[str], keyword: str = "交易时间") -> int:
    """真实账单开头有十几行说明文字，找到真正表头（以「交易时间」开头）是第几行。"""
    for i, row in enumerate(rows):
        if str(row).strip().startswith(keyword):
            return i
    raise ValueError(f"没找到以「{keyword}」开头的表头，可能不是微信 / 支付宝账单")


def _strip_all(df: pd.DataFrame) -> pd.DataFrame:
    """去掉每个格子前后的空格和制表符（支付宝的单号后面会带一个 \\t）。"""
    return df.apply(lambda col: col.astype(str).str.strip())


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    """收尾：补上分类列、按 COLUMNS 排好列的顺序、丢掉时间无效的行。"""
    df = df.copy()
    df["category"] = None          # 分类留到第 7、8 步再填
    df["category_source"] = None
    df = df.dropna(subset=["time"])  # 时间解析失败的行（比如账单末尾的说明）不要
    return df[COLUMNS].reset_index(drop=True)


# ---------- 支付宝 ----------

def parse_alipay(data: bytes) -> pd.DataFrame:
    """解析支付宝账单 CSV。"""
    # 1. 解码。支付宝用 GBK 编码；gb18030 是 GBK 的升级版，能认更多生僻字，更保险
    text = data.decode("gb18030")
    lines = text.splitlines()

    # 2. 跳过开头的说明行，从表头开始交给 pandas 读
    start = _find_header_row(lines)
    raw = pd.read_csv(
        io.StringIO("\n".join(lines[start:])),
        dtype=str,                # 全部先当文本读，单号这种长数字才不会变成科学计数法
        keep_default_na=False,    # 空格子读成 ""，而不是 NaN
    )

    # 3. 每行末尾多一个逗号，会多出一列 "Unnamed: 12"，删掉
    raw = raw.loc[:, ~raw.columns.str.startswith("Unnamed")]
    raw = _strip_all(raw)

    # 4. 一列一列对应到统一格式
    df = pd.DataFrame({
        "id": "ali_" + raw["交易订单号"],
        "time": pd.to_datetime(raw["交易时间"], errors="coerce"),  # 解析不了的变成 NaT，_finish 会丢掉
        "amount": pd.to_numeric(raw["金额"], errors="coerce"),
        "direction": raw["收/支"].replace("", "不计收支"),
        "counterparty": raw["交易对方"],
        "item": raw["商品说明"],
        "platform": "支付宝",
        "pay_method": raw["收/付款方式"],
        "status": raw["交易状态"],
        "raw_type": raw["交易分类"],
    })
    return _finish(df)


# ---------- 微信 ----------

def parse_wechat(data: bytes) -> pd.DataFrame:
    """解析微信账单 xlsx。"""
    # 1. 读 Excel：不要表头（header=None），全部当文本读，空格子填成 ""
    sheet = pd.read_excel(io.BytesIO(data), header=None, dtype=str).fillna("")

    # 2. 在第一列里找表头所在的行
    start = _find_header_row(sheet[0].tolist())

    # 3. 用表头那一行做列名，取它下面的所有行作为数据
    raw = sheet.iloc[start + 1:].copy()
    raw.columns = sheet.iloc[start].tolist()
    raw = _strip_all(raw)

    # 4. 一列一列对应到统一格式（和支付宝的区别：金额带 ¥、中性交易的收/支是 "/"）
    amount_text = raw["金额(元)"].str.replace("¥", "").str.replace(",", "")
    df = pd.DataFrame({
        "id": "wx_" + raw["交易单号"],
        "time": pd.to_datetime(raw["交易时间"], errors="coerce"),
        "amount": pd.to_numeric(amount_text, errors="coerce"),
        "direction": raw["收/支"].replace({"/": "不计收支", "": "不计收支"}),
        "counterparty": raw["交易对方"],
        "item": raw["商品"].replace("/", ""),
        "platform": "微信",
        "pay_method": raw["支付方式"].replace("/", ""),
        "status": raw["当前状态"],
        "raw_type": raw["交易类型"],
    })
    return _finish(df)


# ---------- 自动识别 ----------

def parse_bill(filename: str, data: bytes) -> pd.DataFrame:
    """根据文件名后缀自动选择解析函数。"""
    name = filename.lower()   # 转小写，.XLSX 和 .xlsx 都能认
    if name.endswith(".csv"):
        return parse_alipay(data)
    elif name.endswith(".xlsx"):
        return parse_wechat(data)
    else:
        raise ValueError(f"不支持的文件格式：{filename}（只支持支付宝 .csv 和微信 .xlsx）")
