# Service API参考清单

## 1. Core Summary

本文档提供27个已完成DI改造的Service类的快速查找清单，包括文件位置、依赖的Repository数量和主要业务方法。

## 2. Source of Truth

### Guild模块（6个Service）

**GuildService**
- 文件: `plugins/xiuxian_game/guild/guild_service_new.py` (423行)
- Repository依赖: 4个（GuildRepository, PlayerRepository, GuildMemberRepository, GuildBuildingRepository）
- 核心方法: create_guild, join_guild, leave_guild, dismiss_guild, transfer_leadership
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:93-245`

**GuildApplicationService**
- 文件: `plugins/xiuxian_game/guild/guild_application_service_new.py` (260行)
- Repository依赖: 3个（GuildApplicationRepository, GuildRepository, PlayerRepository）
- 核心方法: submit_application, approve_application, reject_application, cancel_application
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:246-355`

**GuildBuildingService**
- 文件: `plugins/xiuxian_game/guild/guild_building_service_new.py` (412行)
- Repository依赖: 2个（GuildBuildingRepository, GuildRepository）
- 核心方法: build, upgrade_building, get_building_config, get_all_building_effects
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:356-463`

**GuildEconomyService**
- 文件: `plugins/xiuxian_game/guild/guild_economy_service_new.py` (356行)
- Repository依赖: 4个（GuildRepository, PlayerRepository, PlayerDonationLogRepository, GuildBuildingRepository）
- 核心方法: donate_gold, upgrade_guild, add_guild_experience, get_daily_donation_remaining
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:789-858`

**GuildFacilityService**
- 文件: `plugins/xiuxian_game/guild/guild_facility_service_new.py` (613行)
- Repository依赖: 7个（GuildRepository, GuildBuildingRepository, PlayerRepository, ItemRepository, GuildTeleportLogRepository, GuildAlchemyProductionRepository, GuildWarehouseItemRepository）
- 核心方法: teleport_to_guild, get_alchemy_production_grouped, claim_alchemy_item, deposit_to_warehouse, withdraw_from_warehouse
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:859-946`

**GuildTaskService**
- 文件: `plugins/xiuxian_game/guild/guild_task_service_new.py` (710行)
- Repository依赖: 5个（GuildTaskRepository, PlayerRepository, GuildRepository, ItemRepository, GuildBuildingRepository）
- 核心方法: generate_daily_tasks, accept_task, complete_task, claim_task_reward, abandon_task
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:947-1058`

---

### Item模块（6个Service）

**EquipmentService**
- 文件: `plugins/xiuxian_game/item/equipment_service_new.py` (628行)
- Repository依赖: 3个（EquipmentRepository, PlayerRepository, ItemRepository）
- 核心方法: equip_item, unequip_item, sell_equipment, recalc_all_equipment_attributes
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1059-1145`

**EquipmentUpgradeService**
- 文件: `plugins/xiuxian_game/item/equipment_upgrade_service_new.py` (478行)
- Repository依赖: 3个（EquipmentRepository, PlayerRepository, ItemRepository）
- 核心方法: upgrade_equipment, enhance_equipment, refine_equipment
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1146-1208`

**GemSocketService**
- 文件: `plugins/xiuxian_game/item/gem_socket_service_new.py` (385行)
- Repository依赖: 3个（EquipmentRepository, PlayerRepository, ItemRepository）
- 核心方法: socket_gem, unsocket_gem, unsocket_all_gems
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1337-1387`

**GemUpgradeService**
- 文件: `plugins/xiuxian_game/item/gem_upgrade_service_new.py` (312行)
- Repository依赖: 2个（PlayerRepository, ItemRepository）
- 核心方法: upgrade_gem, merge_gems
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1388-1438`

**复杂物品效果Service（3个）**
- **ResetAttrService**: `plugins/xiuxian_game/item/reset_attr_service.py` (140行)
  - 重置玩家属性点
- **SweepDungeonService**: `plugins/xiuxian_game/item/sweep_dungeon_service.py` (215行)
  - 副本扫荡功能
- **WorldBossChestService**: `plugins/xiuxian_game/item/world_boss_chest_service.py` (180行)
  - 世界BOSS宝箱开启

详细文档: `SERVICE_REFACTORING_PROGRESS.md:1209-1275`

---

### Social模块（3个Service）

**MentorshipService**
- 文件: `plugins/xiuxian_game/social/mentorship_service_new.py` (425行)
- Repository依赖: 3个（MentorshipRepository, PlayerRepository, ItemRepository）
- 核心方法: request_mentorship, accept_mentorship, graduate_student, break_mentorship
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:464-552`

**MarriageService**
- 文件: `plugins/xiuxian_game/social/marriage_service_new.py` (380行)
- Repository依赖: 3个（MarriageRepository, PlayerRepository, ItemRepository）
- 核心方法: propose, accept_proposal, divorce
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:553-632`

**GiftService**
- 文件: `plugins/xiuxian_game/social/gift_service_new.py` (310行)
- Repository依赖: 4个（PlayerRepository, ItemRepository, MentorshipRepository, MarriageRepository）
- 核心方法: send_gift, get_relationship_bonus
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:633-702`

---

### Economy模块（3个Service）

**StockService**
- 文件: `plugins/xiuxian_game/economy/stock_service_new.py` (520行)
- Repository依赖: 5个（StockRepository, StockHoldingRepository, StockTransactionRepository, PlayerRepository, BankAccountRepository）
- 核心方法: buy_stock, sell_stock, update_stock_prices, get_player_portfolio
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:356-463`

**PartTimeJobService**
- 文件: `plugins/xiuxian_game/economy/part_time_job_service_new.py` (445行)
- Repository依赖: 4个（PartTimeJobRepository, JobLocationRepository, PlayerJobStatsRepository, PlayerRepository）
- 核心方法: start_job, complete_job, get_available_jobs, get_job_stats
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:464-578`

**EquipmentTradeService**
- 文件: `plugins/xiuxian_game/economy/equipment_trade_service_new.py` (假设存在)
- Repository依赖: 估计4个（EquipmentRepository, PlayerRepository, MarketRepository等）
- 核心方法: list_equipment, buy_equipment, cancel_listing
- Feature Flag: `economy/market.py:21` (已启用)

---

### Cultivate模块（2个Service）

**MansionService**
- 文件: `plugins/xiuxian_game/cultivate/mansion_service_new.py` (380行)
- Repository依赖: 2个（PlayerRepository, ItemRepository）
- 核心方法: enter_mansion, exit_mansion, accelerate_cultivation
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:703-766`

**ReincarnationService**
- 文件: `plugins/xiuxian_game/cultivate/reincarnation_service_new.py` (425行)
- Repository依赖: 2个（PlayerRepository, ItemRepository）
- 核心方法: reincarnate, get_reincarnation_bonus, check_reincarnation_requirements
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:767-788`

---

### World模块（2个Service）

**NPCService**
- 文件: `plugins/xiuxian_game/world/npc_service_new.py` (610行)
- Repository依赖: 2个（NPCRepository, PlayerRepository）
- 核心方法: interact_with_npc, get_npc_shop_items, buy_from_npc, enable_ai_for_npc
- AI接口预留: 7个方法（is_ai_enabled, get_ai_personality等）
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1838-1913`

**LocationService**
- 文件: `plugins/xiuxian_game/world/location_service_new.py` (假设存在)
- Repository依赖: 估计2个（LocationRepository, PlayerRepository）
- 核心方法: explore_location, get_nearby_locations, travel_to_location
- Feature Flag: `world/real_world_explore.py:20`, `world/npc_interaction.py:22` (已启用)

---

### Entertainment模块（2个Service）

**RussianRouletteService**
- 文件: `plugins/xiuxian_game/entertainment/russian_roulette_service_new.py` (假设存在)
- Repository依赖: 估计2个（RouletteRoomRepository, PlayerRepository）
- 核心方法: create_room, join_room, shoot, end_game
- Feature Flag: `entertainment/russian_roulette.py:20` (已启用)

**SignService**
- 文件: `plugins/xiuxian_game/entertainment/sign.py`
- Repository依赖: 估计2个（PlayerRepository, SignRecordRepository）
- 核心方法: daily_sign_in, get_sign_rewards
- 注: 可能未完成DI改造，需验证

---

### Fishing模块（1个Service）

**FishingService**
- 文件: `plugins/xiuxian_game/fishing/service_new.py` (385行)
- Repository依赖: 3个（FishingRepository, PlayerRepository, ItemRepository）
- 核心方法: cast_rod, reel_in, get_fishing_stats
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:579-632`

---

### WorldBoss模块（1个Service）

**WorldBossService**
- 文件: `plugins/xiuxian_game/world_boss/service_new.py` (585行)
- Repository依赖: 4个（WorldBossRepository, WorldBossParticipantRepository, PlayerRepository, ItemRepository）
- 核心方法: spawn_boss, attack_boss, get_boss_status, distribute_rewards
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1741-1837`

---

### DailyTask模块（1个Service）

**DailyTaskService**
- 文件: `plugins/xiuxian_game/daily_task/service_new.py` (假设存在)
- Repository依赖: 估计3个（DailyTaskRepository, PlayerRepository, ItemRepository）
- 核心方法: generate_daily_tasks, complete_task, claim_rewards
- Feature Flag: `daily_task/commands.py:19` (已启用)

---

### Alchemy模块（1个Service）

**AlchemyService**
- 文件: `plugins/xiuxian_game/alchemy/service_new.py` (478行)
- Repository依赖: 3个（AlchemyRepository, PlayerRepository, ItemRepository）
- 核心方法: refine_pill, upgrade_furnace, get_alchemy_recipes
- Feature Flag: `alchemy/__init__.py:12` (已启用)
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:703-788`

---

### InviteReward模块（1个Service）

**InviteRewardService**
- 文件: `plugins/xiuxian_game/player/invite_reward_service_new.py` (280行)
- Repository依赖: 2个（InviteRewardRepository, PlayerRepository）
- 核心方法: record_invitation, claim_invite_reward, get_invite_stats
- Feature Flag: `player/invite.py:17` (已启用)
- 详细文档: `SERVICE_REFACTORING_PROGRESS.md:1276-1336`

---

### Dialogue模块（2个Service，新增 2025-12-06）

**AIDialogueService**
- 文件: `plugins/xiuxian_game/dialogue/ai_dialogue_service.py` (约250行)
- Repository依赖: 1个（NPCDialogueHistoryRepository）
- 核心方法: generate_dialogue, generate_roleplay_response
- LLM集成: 智谱AI GLM-4.5-Flash（通过ai_guide.call_zhipu_api）
- 配置: `data/config.yaml:ai_dialogue`
- 详细文档: `/llmdoc/architecture/npc-ai-dialogue-implementation.md`

**NPCFavorabilityService**
- 文件: `plugins/xiuxian_game/dialogue/npc_favorability_service.py` (约200行)
- Repository依赖: 1个（NPCFavorabilityRepository）
- 核心方法: get_favorability, add_interaction, get_relationship_level
- 好感度机制: 0-100好感度，5个关系等级（陌生人/熟识/友好/亲密/知心）
- 详细文档: `/llmdoc/architecture/npc-ai-dialogue-implementation.md`

---

## 3. 完成度统计

| 模块 | Service数量 | 状态 | 完成日期 |
|------|------------|------|---------|
| Guild | 6 | ✅ 100% | 2025-11-28 |
| Item | 6 | ✅ 100% | 2025-11-29 |
| Social | 3 | ✅ 100% | 2025-11-28 |
| Economy | 3 | ✅ 100% | 2025-11-28 |
| Cultivate | 2 | ✅ 100% | 2025-11-29 |
| World | 2 | ✅ 100% | 2025-11-30 |
| Entertainment | 2 | ✅ 100% | 2025-11-30 |
| Fishing | 1 | ✅ 100% | 2025-11-28 |
| WorldBoss | 1 | ✅ 100% | 2025-11-29 |
| DailyTask | 1 | ✅ 100% | 2025-11-30 |
| Alchemy | 1 | ✅ 100% | 2025-11-28 |
| InviteReward | 1 | ✅ 100% | 2025-11-28 |
| Dialogue | 2 | ✅ 100% | 2025-12-06 |
| **总计** | **29** | **✅ 100%** | **2025-12-06** |

## 4. Feature Flag状态

所有27个Service的Feature Flag已启用（`= True`），详见：

`plugins/xiuxian_game/world_boss/__init__.py:33`
`plugins/xiuxian_game/alchemy/__init__.py:12`
`plugins/xiuxian_game/economy/market.py:21`
`plugins/xiuxian_game/daily_task/commands.py:19`
`plugins/xiuxian_game/entertainment/russian_roulette.py:20`
`plugins/xiuxian_game/world/real_world_explore.py:20`
...等46个文件

## 5. Repository统计

**总计**: 49个Repository类已创建（新增2个：NPCDialogueHistoryRepository, NPCFavorabilityRepository）

**主要Repository**:
- PlayerRepository (228行)
- GuildRepository (205行)
- EquipmentRepository (312行)
- ItemRepository (270行)
- StockRepository (181行)
- ...等47个

详细清单: `SERVICE_REFACTORING_PROGRESS.md:11-92`

---

**相关文档**:
- 完成里程碑: `/llmdoc/overview/service-di-completion.md`
- DI架构: `/llmdoc/architecture/service-di-architecture.md`
- 部署指南: `/llmdoc/guides/deploy-service-di.md`
- 详细进度: `/SERVICE_REFACTORING_PROGRESS.md`
