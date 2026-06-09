"""纯数值公式模块

存放零依赖的核心数值公式（突破成功率、跑商税率等），
便于单元测试直接导入（tests/ 通过 sys.path 指向 plugins/xiuxian_game 后
`from formulas.xxx import ...`），不会触发任何 nonebot/数据库导入。

约定：本包内模块不得 import 项目其他模块或第三方库。
"""
