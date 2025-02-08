模块开发遵循以下流程：
[命令注册] → [参数解析] → [数据验证] → [业务逻辑] → [数据持久化] → [结果反馈]

推荐开发顺序：
1. 角色系统（创建/查看角色）
2. 基础修炼系统
3. 背包与道具使用
4. 战斗系统基础框架
5. 任务系统
6. 社交系统（组队/公会）

.
├── plugins
│   └── xiuxian_game
│       ├── __init__.py              # 插件注册
│       ├── config.py                # 配置文件
│       ├── utils.py                 # 通用工具
│       ├── models                   # 数据模型
│       ├── battle                   # 战斗系统
│       │   ├── __init__.py
│       │   ├── core.py              # 战斗核心逻辑
│       │   └── skills.py             # 技能系统
│       ├── dungeon                  # 副本系统
│       │   ├── __init__.py
│       │   └── instances.py
│       ├── economy                  # 经济系统
│       │   ├── __init__.py
│       │   ├── market.py            # 交易市场
│       │   └── inventory.py         # 背包系统
│       ├── social                   # 社交系统
│       │   ├── __init__.py
│       │   ├── guild.py             # 公会系统
│       │   └── team.py              # 组队系统
│       ├── world                    # 世界系统
│       │   ├── __init__.py
│       │   ├── boss.py              # 世界Boss
│       │   └── secret_realm.py      # 秘境系统
│       └── data                     # 数据存储
│           ├── db.py                # 数据库连接
│           └── schemas.py           # 数据模型
└── pyproject.toml