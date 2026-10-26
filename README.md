# 💰 账单体检 bill-checkup

导入微信 / 支付宝账单，自动分类，用图表和 AI 报告看清钱花在哪。所有数据只在本地处理。

> 🚧 开发中

## 本地运行

```bash
uv sync
uv run streamlit run app.py
```

## 运行测试

```bash
uv run pytest
```

## 目录结构

```
app.py        首页
pages/        各个页面（导入、流水、看板、报告）
core/         业务逻辑（解析、清洗、分类），不含界面代码
tests/        测试
private/      放真实账单，不会上传到 GitHub
```

## 技术栈

Python · Streamlit · pandas · Plotly
