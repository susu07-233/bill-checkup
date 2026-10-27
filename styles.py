"""全站共用的样式：卡片白底 + 轻阴影、统一圆角和间距、正文最大宽度、首页柔光、小票卡片。

颜色、字体、圆角的基础设置在 .streamlit/config.toml；这里只补主题做不到的部分。
只用我们自己起名字的容器（key=... → .st-key-...），不碰 Streamlit 内部的类名，升级时不容易坏。
  page          每一页的最外层（app.py），限制最大宽度
  card_*        白色卡片（看板上的各个图表块、侧栏「当前数据」）
  home          首页最外层，右上角一层很淡的绿色柔光
  receipt       首页的小票卡片；receipt_total 金额、receipt_items 明细行
"""

import streamlit as st

LIGHT = dict(card="#ffffff", line="#ebe7dc", dash="#d9d3c4", glow="rgba(74, 140, 104, 0.13)",
             shadow="rgba(40, 52, 44, 0.06)", muted="#6b6f68")
DARK = dict(card="#1f231f", line="#2e342e", dash="#3e463e", glow="rgba(80, 160, 115, 0.10)",
            shadow="rgba(0, 0, 0, 0.35)", muted="#a6aba4")


def inject():
    c = DARK if getattr(st.context.theme, "type", "light") == "dark" else LIGHT
    st.html(f"""<style>
/* 正文最大宽度：大屏上不把内容拉得太散 */
.st-key-page {{ max-width: 1180px; margin: 0 auto; }}

/* 卡片：纯白底、细边、轻阴影、统一圆角和内边距 */
[class*="st-key-card"] {{
  background: {c['card']};
  border-color: {c['line']} !important;
  border-radius: 16px;
  box-shadow: 0 1px 2px {c['shadow']}, 0 6px 20px {c['shadow']};
  padding: 1.1rem 1.25rem;
}}

/* 流水页的数字小卡片：内边距小一点 */
[class*="st-key-card_metric"] {{ padding: .8rem 1rem; }}

/* 长段文字（AI 月报）：每行不超过约 46 个字，读起来不累 */
.st-key-card_report p, .st-key-card_report li {{ max-width: 46em; line-height: 1.75; }}

/* 首页：右上角非常淡的绿色柔光 */
.st-key-home {{
  background: radial-gradient(ellipse 60% 70% at 100% 0%, {c['glow']}, transparent 70%);
  border-radius: 28px;
  padding: 2.5rem 2rem 2rem;
}}

/* 小票：白纸、等宽数字、虚线分隔、底边锯齿 */
.st-key-receipt {{
  position: relative;
  background: {c['card']};
  border-radius: 14px 14px 0 0;
  padding: 1.6rem 1.6rem 1.4rem;
  filter: drop-shadow(0 6px 14px {c['shadow']}) drop-shadow(0 1px 1px {c['shadow']});
}}
.st-key-receipt::after {{
  content: ""; position: absolute; left: 0; right: 0; bottom: -10px; height: 10px;
  background:
    linear-gradient(135deg, {c['card']} 7px, transparent 0) 0 0 / 14px 10px repeat-x,
    linear-gradient(-135deg, {c['card']} 7px, transparent 0) 0 0 / 14px 10px repeat-x;
}}
.st-key-receipt_head {{ border-bottom: 1px dashed {c['dash']}; padding-bottom: .6rem; }}
.st-key-receipt_total h1 {{
  font-family: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace;
  font-weight: 600; letter-spacing: -0.02em;
}}
.st-key-receipt_items {{ border-top: 1px dashed {c['dash']}; border-bottom: 1px dashed {c['dash']}; padding: .5rem 0; }}
.st-key-receipt_items p {{ font-variant-numeric: tabular-nums; }}
</style>""")
