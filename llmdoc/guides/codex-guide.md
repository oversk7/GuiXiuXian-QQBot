# 全游戏百科维护指南

## 目标

`图鉴` 提供统一目录、分类分页、名称查询和关联资料查询。物品详情仍复用原有图鉴，保留图片、装备属性、用药记录及专属装备信息的展示条件。

## 数据责任

- `plugins/xiuxian_game/item/catalog.py`：NoneBot 命令入口及现有物品详情。
- `plugins/xiuxian_game/item/codex_service.py`：统一条目、查询、分页与配方关系。
- `plugins/xiuxian_game/item/codex_world.py`：公开世界与养成资料、指定深度的诡域资料。
- `plugins/xiuxian_game/world/npc_definitions.py`：地图初始化与图鉴共用的社交代理、驿丞、情报贩子及社交使者名录；图鉴展示配置中的位置与职能，不代表 NPC 当前存活或营业状态。
- `plugins/xiuxian_game/item/codex_sources.py`：商店、任务、钓鱼、明确配置的诡域获取渠道，以及装备升阶材料用途。
- `plugins/xiuxian_game/item/codex_filters.py`：装备品质及等级上限筛选；`装备 蓝色 100级 2` 的裸数字末项是页码，`100级` 是装备等级要求上限，不表示玩家已满足转生等其他穿戴条件。
- `plugins/xiuxian_game/data/knowledge/codex_help.yaml`：玩家图鉴帮助，按已有机制自动注册 `图鉴帮助`。

公开条目采用 `key/name/category/description/aliases/lines` 结构。`key` 使用带命名空间的稳定标识；关联链接使用稳定标识，避免同名条目互相遮挡。物品从运行中的 `config.items_config` 读取，覆盖启动时动态注册的菜肴。

## 扩展约定

1. 新增现有类别的内容，应更新该玩法的原始配置，不再维护一份百科数值副本。
2. 新类别在对应提供器构建条目，加入公开名称、分类、描述及详情。
3. 来源与用途必须能追溯到玩法实际使用的定义。市场的收购列表不能作为购买来源，随机商店候选池不能称为今日库存。
4. 动态属性标明条件或范围；诡域详情调用既有深度生成函数，不创建地图、不写玩家数据。
5. 不收录管理员操作、NPC 私密人设或剧情谜底。知识正文继续维护在 `data/knowledge/`。
6. 无已收录来源表示资料尚未覆盖，不能断言物品无法获得。历史活动物品也不能据配置存在推断活动正在开放。
7. 新增链接需验证能唯一定位；长列表与详情应保留分页，不能静默丢弃剩余结果。

## 已核实的特殊规则

- 装备锻造的实际逻辑要求至少一枚血肉结晶，不能只展示原配方材料。
- 升阶材料既受装备是否有配方影响，也受 `upgrade_material_tier` 影响；用途读取当前装备实际采用的材料表。
- 目前材料分档最高为 `201-999`，更深层由 `_get_materials_for_level()` 返回默认池；百科不将 999 擅自解释为无限上界。
- 普通鱼池、诡域鱼池、沿海专属鱼和打捞杂物分别读取钓鱼服务定义。

## 验证

使用项目虚拟环境运行 `tests/test_codex*.py`，并回归 `tests/test_catalog_image_fallback.py` 和 `tests/test_command_link_rendering.py`。这些检查不启动数据库迁移，也不写生产数据。上线后仍需在 QQ 中验证实际消息长度、分页和蓝字交互。`test_codex_links.py` 遍历实际条目与物品关联链接，另模拟启动时菜肴注册，检查动态产物与食谱连接。`test_codex_npc_definitions.py` 验证共享名录变化同时影响初始化与图鉴。
