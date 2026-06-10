"""
属性领域模块

读取入口（两档，见 llmdoc/reference/coding-conventions.md §6.3）:
- 全量真源: Player.get_effective_attributes(session)
- 战斗档: battle.battle_attributes.BattleAttributeCalculator（含 ATTRIBUTE_CAPS 上限）

写入收口: permanent_change.apply_permanent_change（永久属性变更唯一入口）
"""
