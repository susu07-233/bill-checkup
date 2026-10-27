"""示例数据：生成一位虚构大学生「小林」半年的账单，格式和真实导出的支付宝 CSV / 微信 xlsx 一样。

用途：
  - 开发看板时用来测试图表（不碰真实账单）
  - 网页上「用示例账单试试」，让没有账单的人（比如面试官）也能体验完整功能

所有数据都是编的。用固定的随机种子，每次生成的结果完全一样，方便测试。

小林的消费规律：
  - 每月 1 号收到家里转的生活费 2000 元；学期中每月做两次家教
  - 学期中每天在食堂吃饭，暑假（7/5–8/30）在家，点外卖多、不去食堂
  - 周末更爱点外卖、聚餐、看电影
  - 每月固定：话费、视频会员、音乐会员、宿舍电费、存一笔余额宝
  - 开学季（9 月初）网购多，放假和国庆前后买火车票
  - 少量特殊情况：交易关闭、全额退款、部分退款、跨月退款
"""

import io
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from openpyxl import Workbook

START = date(2026, 5, 1)
END = date(2026, 10, 26)
VACATION = (date(2026, 7, 5), date(2026, 8, 30))
CARD = "工商银行储蓄卡(6688)"


@dataclass
class Tx:
    """一笔原始交易（还没转成平台格式）。"""
    time: datetime
    platform: str          # "微信" / "支付宝"
    category: str          # 支付宝的「交易分类」或微信的「交易类型」
    counterparty: str
    item: str
    direction: str         # "支出" / "收入" / "不计收支"
    amount: float
    pay_method: str
    status: str
    merchant_no: str = ""
    order_no: str = field(default="", init=False)


class _Generator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.txs: list[Tx] = []

    # ---------- 小工具 ----------
    def at(self, day: date, start: str, end: str) -> datetime:
        """在当天 start–end 之间随机取一个时间。"""
        h1, m1 = map(int, start.split(":"))
        h2, m2 = map(int, end.split(":"))
        seconds = self.rng.randint(h1 * 3600 + m1 * 60, h2 * 3600 + m2 * 60)
        return datetime.combine(day, datetime.min.time()) + timedelta(seconds=seconds)

    def price(self, lo: float, hi: float) -> float:
        """随机价格，带一点真实感：要么整数 / 一位小数，要么 .9 结尾。"""
        value = self.rng.uniform(lo, hi)
        style = self.rng.random()
        if style < 0.4:
            return float(round(value))
        if style < 0.7:
            return round(int(value) + 0.9, 2)
        return round(value, 1)

    def add(self, *args, **kwargs) -> Tx:
        tx = Tx(*args, **kwargs)
        self.txs.append(tx)
        return tx

    def wx(self, time, kind, who, item, amount, direction="支出", pay="零钱", status="支付成功", merchant="") -> Tx:
        return self.add(time, "微信", kind, who, item, direction, amount, pay, status, merchant)

    def ali(self, time, kind, who, item, amount, direction="支出", pay=None, status="交易成功", merchant="") -> Tx:
        pay = pay or self.rng.choice([CARD, CARD, "余额宝", "花呗"])
        return self.add(time, "支付宝", kind, who, item, direction, amount, pay, status, merchant)

    # ---------- 每天的消费 ----------
    def daily(self, d: date):
        rng = self.rng
        weekend = d.weekday() >= 5
        vacation = VACATION[0] <= d <= VACATION[1]

        if not vacation:  # 食堂
            if rng.random() < 0.55:
                self.wx(self.at(d, "06:50", "08:20"), "商户消费", "第一食堂", "早餐", self.price(4, 8))
            if rng.random() < 0.85:
                self.wx(self.at(d, "11:30", "12:40"), "商户消费", rng.choice(["第一食堂", "第二食堂"]), "午餐", self.price(10, 18))
            if rng.random() < 0.6:
                self.wx(self.at(d, "17:20", "18:40"), "商户消费", rng.choice(["第一食堂", "第二食堂"]), "晚餐", self.price(9, 16))

        p_takeout = 0.5 if vacation else (0.45 if weekend else 0.2)
        if rng.random() < p_takeout:  # 外卖
            t = self.at(d, "11:00", "20:30")
            dish = rng.choice(["黄焖鸡米饭", "麻辣烫", "炸鸡汉堡", "螺蛳粉", "盖浇饭", "寿司", "烤肉饭"])
            if rng.random() < 0.6:
                self.ali(t, "餐饮美食", rng.choice(["美团", "饿了么"]), f"外卖订单-{dish}", self.price(18, 42))
            else:
                self.wx(t, "商户消费", "美团", f"美团订单-{dish}", self.price(18, 42))

        if rng.random() < 0.3:  # 奶茶咖啡
            shop, lo, hi = rng.choice([("瑞幸咖啡", 9.9, 19), ("蜜雪冰城", 5, 12), ("喜茶", 15, 25), ("古茗", 10, 18)])
            self.wx(self.at(d, "09:00", "21:30"), "商户消费", shop, rng.choice(["生椰拿铁", "柠檬水", "奶茶", "美式咖啡"]), self.price(lo, hi))

        if rng.random() < 0.25:  # 超市、便利店
            if rng.random() < 0.6:
                self.wx(self.at(d, "08:00", "22:30"), "扫二维码付款", "校园超市", "/", self.price(3, 30))
            else:
                self.ali(self.at(d, "08:00", "23:00"), "日用百货", rng.choice(["罗森便利店", "美宜佳"]), "便利店消费", self.price(5, 35))

        if not vacation and rng.random() < (0.35 if weekend else 0.15):  # 公交地铁
            self.ali(self.at(d, "08:00", "21:00"), "交通出行", "城市公交地铁", "乘车码", self.price(2, 5))
        if rng.random() < 0.05:  # 打车
            self.ali(self.at(d, "07:30", "23:30"), "交通出行", "滴滴出行", "快车行程", self.price(14, 45))

        if rng.random() < 0.16:  # 网购
            self.online_shopping(d)

        if not vacation and rng.random() < 0.12:  # 打印复印
            self.wx(self.at(d, "08:30", "21:00"), "扫二维码付款", "图文打印店", "/", self.price(1, 9))

        if weekend:
            if rng.random() < 0.25:  # 周末聚餐 AA
                self.wx(self.at(d, "18:00", "21:00"), "群收款", "室友聚餐AA", "/", self.price(35, 90))
            if rng.random() < 0.1:
                self.ali(self.at(d, "13:00", "21:00"), "文化休闲", "猫眼电影", "电影票", self.price(35, 75))
            if rng.random() < 0.06:
                self.wx(self.at(d, "14:00", "23:00"), "扫二维码付款", "极速网咖", "/", self.price(10, 30))

        if rng.random() < 0.035:
            self.ali(self.at(d, "10:00", "23:59"), "文化休闲", "Steam", "游戏购买", self.price(20, 120))
        if rng.random() < 0.025:
            self.ali(self.at(d, "09:00", "21:00"), "医疗健康", "大参林药房", "药品", self.price(8, 60))
        if rng.random() < 0.03:  # 发红包
            self.wx(self.at(d, "09:00", "23:00"), "微信红包（单发）", rng.choice(["阿杰", "小雨", "老王"]), "/", self.price(5, 50),
                    status="对方已收钱")
        if rng.random() < 0.03:  # 收红包
            self.wx(self.at(d, "09:00", "23:00"), "微信红包", rng.choice(["阿杰", "小雨", "表姐"]), "/", self.price(6, 66),
                    direction="收入", pay="/", status="已存入零钱")
        if rng.random() < 0.03:  # 转账给同学
            self.wx(self.at(d, "09:00", "23:00"), "转账", rng.choice(["阿杰", "小雨", "老王"]), "/", self.price(20, 100),
                    status="对方已收钱")

    def online_shopping(self, d: date, big: bool = False):
        rng = self.rng
        t = self.at(d, "09:00", "23:59")
        lo, hi = (100, 400) if big else (15, 160)
        choice = rng.random()
        if choice < 0.5:
            item = rng.choice(["抽纸", "洗衣液", "T恤", "数据线", "台灯", "收纳盒", "运动鞋", "帆布包"])
            self.ali(t, rng.choice(["日用百货", "服饰装扮"]), rng.choice(["淘宝商家", "天猫超市"]), item, self.price(lo, hi),
                     status=rng.choice(["交易成功"] * 5 + ["等待确认收货"]))
        elif choice < 0.8:
            item = rng.choice(["零食大礼包", "袜子", "手机壳", "床单", "水杯"])
            self.wx(t, "商户消费", "拼多多", item, self.price(lo * 0.6, hi * 0.6))
        else:
            item = rng.choice(["蓝牙耳机", "键盘", "移动硬盘", "教材", "电饭煲"])
            self.wx(t, "商户消费", "京东", item, self.price(lo * 1.5, hi * 1.5))

    # ---------- 每月固定 ----------
    def monthly(self, year: int, month: int):
        rng = self.rng
        vacation_month = month in (7, 8)

        def day(n):
            return date(year, month, n)

        self.wx(self.at(day(1), "09:00", "12:00"), "转账", "妈妈", "/", 2000.0, direction="收入", pay="/", status="已收钱")
        self.ali(self.at(day(rng.randint(1, 3)), "10:00", "22:00"), "充值缴费", "中国移动", "话费充值", 50.0, pay=CARD)
        self.wx(self.at(day(5), "03:00", "03:30"), "商户消费", "腾讯视频", "VIP会员自动续费", 25.0)
        self.ali(self.at(day(20), "03:00", "03:30"), "文化休闲", "网易云音乐", "黑胶VIP自动续费", 15.0, pay=CARD)
        self.ali(self.at(day(2), "10:00", "12:00"), "投资理财", "余额宝", "余额宝-转入", 300.0, direction="不计收支", pay=CARD)
        if not vacation_month:
            self.ali(self.at(day(rng.randint(8, 12)), "10:00", "22:00"), "生活服务", "校园电费", "宿舍电费充值", self.price(30, 60), pay=CARD)
            for n in rng.sample(range(6, 27), 2):  # 家教
                self.wx(self.at(day(n), "19:00", "21:30"), "转账", "家教家长", "/", float(rng.choice([150, 200, 200, 250])),
                        direction="收入", pay="/", status="已收钱")

    # ---------- 季节性 + 特殊情况 ----------
    def seasonal_and_special(self):
        rng = self.rng
        # 火车票：暑假回家、开学返校、国庆往返
        for d, item in [(date(2026, 7, 4), "南昌西-赣州西"), (date(2026, 8, 29), "赣州西-南昌西"),
                        (date(2026, 9, 30), "南昌西-赣州西"), (date(2026, 10, 7), "赣州西-南昌西")]:
            self.wx(self.at(d - timedelta(days=rng.randint(5, 12)), "08:00", "22:00"), "商户消费", "中铁网络", f"火车票 {item}", self.price(120, 180))

        for _ in range(4):  # 开学季网购
            self.online_shopping(date(2026, 9, 1) + timedelta(days=rng.randint(0, 9)), big=True)

        self.ali(self.at(date(2026, 9, 15), "10:00", "16:00"), "教育培训", "全国大学英语四六级考试", "报名费", 30.0, pay=CARD)

        # 交易关闭（下单后取消）：每月一笔
        for month in range(5, 11):
            d = date(2026, month, rng.randint(3, 25))
            self.ali(self.at(d, "10:00", "23:00"), "日用百货", "淘宝商家", "订单已取消", self.price(20, 120), status="交易关闭")

        # 全额退款：原订单 + 退款到账
        for d in (date(2026, 6, 12), date(2026, 9, 18)):
            amount = self.price(30, 90)
            buy = self.wx(self.at(d, "10:00", "20:00"), "商户消费", "拼多多", "不合适的衣服", amount, status="已全额退款")
            self.wx(buy.time + timedelta(days=2), "拼多多-退款", "拼多多", "/", amount, direction="收入", status="已全额退款")

        # 部分退款：买 ¥299 的耳机，退差价 ¥50
        buy = self.wx(self.at(date(2026, 9, 3), "20:00", "22:00"), "商户消费", "京东", "蓝牙耳机", 299.0, status="已退款(¥50.00)")
        self.wx(buy.time + timedelta(days=3), "京东-退款", "京东", "/", 50.0, direction="收入", status="已退款¥50.00")

        # 跨月退款：4 月买的五一车票，5 月退票（原订单不在账单里）
        self.wx(self.at(date(2026, 5, 2), "08:00", "10:00"), "中铁网络-退款", "中铁网络", "/", 156.0, direction="收入", status="已全额退款")

    def run(self) -> list[Tx]:
        d = START
        while d <= END:
            if d.day == 1:
                self.monthly(d.year, d.month)
            self.daily(d)
            d += timedelta(days=1)
        self.seasonal_and_special()
        self.txs = [t for t in self.txs if START <= t.time.date() <= END]
        self.txs.sort(key=lambda t: t.time, reverse=True)  # 真实账单是从新到旧
        for i, t in enumerate(self.txs):
            stamp = t.time.strftime("%Y%m%d")
            t.order_no = f"{stamp}2200110{i:05d}" if t.platform == "支付宝" else f"42000{stamp}{i:05d}"
        return self.txs


# ---------- 转成平台的文件格式 ----------

def _alipay_csv(txs: list[Tx]) -> bytes:
    rows = [t for t in txs if t.platform == "支付宝"]
    header = [
        "------------------------------------------------------------------------------------",
        "导出信息：", "姓名：小林（示例数据）", "支付宝账户：demo***@example.com",
        f"起始时间：[{START} 00:00:00]    终止时间：[{END} 23:59:59]",
        "导出交易类型：[全部]", f"导出时间：[{END} 23:59:59]", f"共{len(rows)}笔记录", "",
        "特别提示：", "1.本文件为示例数据，所有交易均为虚构。", "",
        "------------------------支付宝（中国）网络技术有限公司  电子客户回单------------------------",
        "交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,",
    ]
    lines = [
        ",".join([t.time.strftime("%Y-%m-%d %H:%M:%S"), t.category, t.counterparty, "/", t.item, t.direction,
                  f"{t.amount:.2f}", t.pay_method, t.status, t.order_no + "\t", (t.merchant_no or "") + "\t", ""]) + ","
        for t in rows
    ]
    return ("\r\n".join(header + lines) + "\r\n").encode("gbk")


def _wechat_xlsx(txs: list[Tx]) -> bytes:
    rows = [t for t in txs if t.platform == "微信"]
    wb = Workbook()
    ws = wb.active
    for line in [
        ["微信支付账单明细"], ["微信昵称：[小林（示例数据）]"],
        [f"起始时间：[{START} 00:00:00] 终止时间：[{END} 23:59:59]"], ["导出类型：[全部]"],
        [f"导出时间：[{END} 23:59:59]"], [], [f"共{len(rows)}笔记录"],
        ["注："], ["1. 本文件为示例数据，所有交易均为虚构。"], [],
        ["----------------------微信支付账单明细列表--------------------"],
        ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)", "支付方式", "当前状态", "交易单号", "商户单号", "备注"],
    ]:
        ws.append(line)
    for t in rows:
        ws.append([
            t.time.strftime("%Y-%m-%d %H:%M:%S"), t.category, t.counterparty, t.item or "/",
            "/" if t.direction == "不计收支" else t.direction, f"¥{t.amount:.2f}", t.pay_method,
            t.status, t.order_no, t.merchant_no or "/", "/",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def demo_files(seed: int = 2026) -> list[tuple[str, bytes]]:
    """生成两份示例账单：[(文件名, 文件内容), ...]，可以直接交给 parse_bill。"""
    txs = _Generator(seed).run()
    span = f"{START:%Y%m%d}-{END:%Y%m%d}"
    return [
        (f"支付宝交易明细({span})_示例.csv", _alipay_csv(txs)),
        (f"微信支付账单({span})_示例.xlsx", _wechat_xlsx(txs)),
    ]
