"""跑商税率档位（纯函数）

从 economy/merchants.py 提取，按当日累计跑商收入选择累进税率档。
"""

# (档位上限, 税率)；daily_revenue 落在第一个小于上限的档
TRADE_TAX_BRACKETS = [
    (300_000,      0.00),   # 日收入 0-30万: 免税
    (800_000,      0.05),   # 30万-80万: 5%
    (1_500_000,    0.10),   # 80万-150万: 10%
    (999_999_999,  0.15),   # 150万+: 15%
]


def pick_trade_tax_rate(daily_revenue: int) -> float:
    """根据当日累计跑商收入返回适用税率。

    注意：保留原实现语义——daily_revenue >= 999_999_999 时不匹配任何档位，
    返回 0.0（哨兵值边界怪癖，现实中难以触发）。
    """
    tax_rate = 0.0
    for bracket_limit, rate in TRADE_TAX_BRACKETS:
        if daily_revenue < bracket_limit:
            tax_rate = rate
            break
    return tax_rate
