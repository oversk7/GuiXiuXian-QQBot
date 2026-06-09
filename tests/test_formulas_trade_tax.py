"""跑商税率档位单元测试（累进制边界）"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
plugins_path = project_root / "plugins" / "xiuxian_game"
sys.path.insert(0, str(plugins_path))

from formulas.trade_tax import pick_trade_tax_rate


def test_free_bracket():
    assert pick_trade_tax_rate(0) == 0.0
    assert pick_trade_tax_rate(299_999) == 0.0


def test_5_percent_bracket():
    assert pick_trade_tax_rate(300_000) == 0.05
    assert pick_trade_tax_rate(799_999) == 0.05


def test_10_percent_bracket():
    assert pick_trade_tax_rate(800_000) == 0.10
    assert pick_trade_tax_rate(1_499_999) == 0.10


def test_15_percent_bracket():
    assert pick_trade_tax_rate(1_500_000) == 0.15
    assert pick_trade_tax_rate(999_999_998) == 0.15


def test_sentinel_quirk_documented():
    # 已知边界怪癖：日收入 >= 999_999_999（哨兵值）不匹配任何档位，返回 0.0。
    # 本用例记录现状；若改为尾档兜底 0.15，请同步更新此断言。
    assert pick_trade_tax_rate(999_999_999) == 0.0
