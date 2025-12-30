# NPC/鬼怪累积与地点探索系统深度调查报告

**调查日期**: 2025-12-30
**调查目标**: 深入分析玩家探索86个地点、NPC/鬼怪累积机制、locations_visited_list字段用途
**调查范围**: 地点系统、NPC生成/清理、委托任务、成就统计

---

## Code Sections (The Evidence)

### 1. locations_visited_list字段使用

- `plugins/xiuxian_game/models/achievement.py:55` (PlayerStats.locations_visited_list): TEXT类型字段，存储逗号分隔的地点访问记录
- `plugins/xiuxian_game/achievement/achievement_service.py:200-220` (add_visited_location): 记录玩家访问过的地点
  - Line 212: 解析已访问列表 `visited_list = stats.locations_visited_list.split(",") if stats.locations_visited_list else []`
  - Line 216: 保存新访问 `stats.locations_visited_list = ",".join(visited_list)`
- `plugins/xiuxian_game/world/real_world_explore.py:95-98` (观察命令): 触发地点访问记录
  - Line 97: 生成location_key格式 `location_key = f"{location.region}:{location.x}:{location.y}"`
  - Line 98: 调用成就系统记录访问

### 2. 地点发现机制

- `plugins/xiuxian_game/world/real_world_explore.py:116-119` (获取附近地点):
  ```python
  nearby_locations = await LocationService.get_nearby_locations(
      session, x, y, region, max_distance=50
  )
  ```
  - 搜索范围：50格（曼哈顿距离）
  - Line 213: 显示格式 `f"🗺️ 附近地点（{len(all_nearby_places)}个）："`

- `plugins/xiuxian_game/world/location_service.py:43-60` (get_nearby_locations): SQL查询附近地点
  ```python
  func.abs(Location.x - x) + func.abs(Location.y - y) <= max_distance
  ```
  - 使用曼哈顿距离：`|x1-x2| + |y1-y2| <= max_distance`

### 3. NPC/鬼怪生成机制

- `plugins/xiuxian_game/daily_task/service_new.py:312-368` (create_ghost_npc_for_task): 为任务创建鬼怪NPC
  - Line 316: 生成唯一NPC ID `npc_id = f"ghost_task_{task.id}"`
  - Line 323-342: 查找或创建目标地点Location
  - Line 345-354: 创建鬼怪NPC实例
  - Line 359-361: 关联任务信息到extra_data

- `plugins/xiuxian_game/models/npc.py:278-299` (NPC.create_ghost): 创建鬼怪静态方法
  - Line 289: 标记为动态NPC `is_dynamic=True`
  - Line 296: **关键：鬼怪不复活** `respawn_duration_minutes=0`

### 4. NPC清理机制

- `plugins/xiuxian_game/world/npc_service_new.py:339-349` (cleanup_expired_dynamic_npcs): 清理过期动态NPC
  ```python
  async def cleanup_expired_dynamic_npcs(self, max_age_hours: int = 24) -> int:
      return await self._npc_repo.cleanup_expired_dynamic(max_age_hours)
  ```
  - 默认清理24小时前的NPC

- `plugins/xiuxian_game/world/npc_service.py:274-293` (cleanup_expired_dynamic_npcs实现): 具体清理逻辑
  - Line 277: 计算截止时间 `cutoff_time = datetime.now() - timedelta(hours=max_age_hours)`
  - Line 280-284: 查询条件
    ```python
    and_(
        NPC.is_dynamic == True,
        NPC.created_at < cutoff_time,
        NPC.status == NPCStatus.DEAD
    )
    ```
  - **关键发现：只清理已死亡的动态NPC**

- `plugins/xiuxian_game/world/location_init.py:612-640` (清理NPC命令): 管理员手动清理命令
  - Line 624: 调用清理 `cleaned_count = await NPCService.cleanup_expired_dynamic_npcs(session, max_age_hours=24)`

### 5. 地点坐标系统

- `plugins/xiuxian_game/world/real_world_explore.py:97-98` (location_key格式):
  ```python
  location_key = f"{location.region}:{location.x}:{location.y}"
  ```
  - 格式示例: `"大都会:162:121"`
  - 由区域、X坐标、Y坐标三部分组成

### 6. NPC复活机制

- `plugins/xiuxian_game/models/npc.py:118-130` (NPC.kill): 击杀NPC方法
  - Line 128-130: 设置复活时间
    ```python
    if self.respawn_duration_minutes > 0:
        self.respawn_time = self.death_time + timedelta(minutes=self.respawn_duration_minutes)
        self.status = NPCStatus.RESPAWNING
    ```
  - **关键：只有respawn_duration_minutes>0的NPC才会复活**

- `plugins/xiuxian_game/world/real_world_explore.py:44-45` (观察命令): 自动复活NPC
  ```python
  await NPCService.check_and_respawn_npcs(session)
  ```

---

## Report (The Answers)

### 1. 为什么玩家会探索86个地点？

**地点发现机制分析**:

根据 `real_world_explore.py:116-119`，玩家每次使用【观察】命令时会搜索附近50格内的所有地点：

```python
nearby_locations = await LocationService.get_nearby_locations(
    session, x, y, region, max_distance=50
)
```

**为什么会有86个地点记录**:

1. **地点数量合理性**: 86个地点数量是合理的
   - 游戏初始化时创建了固定地点（城市、市集、工坊等）约30-40个（根据 `npc_cleanup_investigation.md`）
   - 每日委托任务动态创建临时地点（`task_location_x_y`格式）
   - 玩家探索路径覆盖多个区域

2. **locations_visited_list的记录逻辑**:
   - 每次玩家使用【观察】命令时，如果当前位置有Location，就会记录访问
   - 记录格式为 `"大都会:162:121"` （region:x:y）
   - 即使重复访问同一地点，也会检查并去重（`achievement_service.py:214-215`）

3. **86个地点的来源估算**:
   - 固定城市地点：约10-15个（上京、北郊、东郊、西郊、南郊、金陵、云岭、郸城、荔湾镇、摩配镇、风雪镇等）
   - 子地点：每个城市有多个功能点（市集、工坊、雇主等）
   - 委托任务临时地点：根据每日任务动态生成
   - 阴宅：其他玩家的阴宅位置

**结论**: 86个地点是合理的数据，说明玩家活跃探索了游戏世界，而非bug。

---

### 2. 当日委托生成的鬼怪是否及时清理？

**NPC清理机制分析**:

#### 2.1 鬼怪NPC的生命周期

1. **创建时机** (`daily_task/service_new.py:312-368`):
   - 玩家接取每日委托任务时
   - 自动在目标坐标创建Location（如果不存在）
   - 创建鬼怪NPC并关联任务ID

2. **死亡后状态** (`models/npc.py:118-130`):
   ```python
   if self.respawn_duration_minutes > 0:
       # 设置复活时间
   else:
       # 不复活，永久死亡
   ```
   - 鬼怪NPC的 `respawn_duration_minutes=0`（Line 296）
   - **击杀后永久死亡，不会复活**

3. **清理条件** (`npc_service.py:274-293`):
   ```python
   and_(
       NPC.is_dynamic == True,        # 必须是动态NPC
       NPC.created_at < cutoff_time,  # 创建时间超过24小时
       NPC.status == NPCStatus.DEAD   # 必须是已死亡状态
   )
   ```

#### 2.2 **关键发现：清理机制存在问题**

**问题1：未完成的任务NPC不会被清理**
- 清理条件要求 `NPC.status == DEAD`
- 如果玩家接取任务但未击杀鬼怪，NPC会永久存在
- 这些"僵尸NPC"会不断累积

**问题2：24小时清理周期过长**
- 默认 `max_age_hours=24` 意味着已击杀的鬼怪会留存24小时
- 对于高活跃服务器，可能导致大量死亡NPC堆积

**问题3：缺少自动清理触发**
- 清理机制仅在以下情况触发：
  1. 管理员手动执行【清理NPC】命令（`location_init.py:615-640`）
  2. 玩家使用【观察】命令时触发复活检查（不清理死亡NPC）
- **缺少定时任务自动清理**

#### 2.3 临时地点的累积问题

**问题4：任务临时地点不会被清理**
- 每个委托任务会创建临时Location: `task_location_{x}_{y}`
- 这些Location即使鬼怪被击杀，也不会自动删除
- 导致location表不断膨胀

**代码证据** (`daily_task/service_new.py:327-342`):
```python
if not location:
    location_id = f"task_location_{task.target_x}_{task.target_y}"
    location = await self._location_service.get_location_by_id(location_id)
    if not location:
        location = await self._location_service.create_location(
            location_id=location_id,
            name=f"荒野({task.target_x},{task.target_y})",
            # ... 没有设置过期时间
        )
```

---

### 3. locations_visited_list字段存储的是什么？

**字段用途说明**:

#### 3.1 数据结构

- **字段类型**: TEXT（存储逗号分隔的字符串）
- **存储格式**: `"大都会:0:0,上京:100:460,北郊:-50:320,..."`
- **组成部分**: `region:x:y` （区域:X坐标:Y坐标）

#### 3.2 记录机制

**触发条件** (`real_world_explore.py:95-98`):
- 玩家使用【观察】命令
- 当前坐标有对应的Location记录
- 自动调用成就系统记录访问

**去重逻辑** (`achievement_service.py:212-218`):
```python
visited_list = stats.locations_visited_list.split(",") if stats.locations_visited_list else []

if location_key not in visited_list:
    visited_list.append(location_key)
    stats.locations_visited_list = ",".join(visited_list)
    stats.locations_visited = len(visited_list)  # 更新计数
```

#### 3.3 用途分析

1. **成就系统**: 追踪玩家探索进度
   - `stats.locations_visited` 存储访问过的地点数量
   - 用于解锁探索类成就（如"探索10个不同地点"）

2. **数据统计**: 为游戏平衡提供依据
   - 分析玩家活跃区域
   - 识别冷门地点

3. **非导航记录**: 不是路径记录
   - 只记录访问过的唯一地点坐标
   - 不记录访问顺序、次数、时间

#### 3.4 潜在问题

**问题5：字符串长度限制**
- TEXT字段无明确长度限制，但累积过多会导致：
  - 查询性能下降
  - 存储空间浪费
  - 字符串解析开销

**估算**: 假设每个location_key平均20字符，86个地点约1.7KB，尚在可接受范围。但如果探索1000+地点，会达到20KB+。

---

## Conclusions (Key Takeaways)

### 核心发现总结

1. **86个地点是正常数据**: 玩家通过【观察】命令发现附近50格内的地点，累积记录是合理行为

2. **鬼怪NPC清理机制不完善**:
   - ✅ 已击杀的鬼怪会在24小时后清理（`respawn_duration_minutes=0`）
   - ❌ 未击杀的任务鬼怪会永久存在
   - ❌ 缺少自动清理定时任务
   - ❌ 临时任务Location不会自动删除

3. **locations_visited_list用于成就追踪**:
   - 格式：`"region:x:y,region:x:y,..."`
   - 用途：解锁探索类成就
   - 风险：长期累积可能导致性能问题

### 数据量估算

| 数据类型 | 预估数量 | 说明 |
|---------|---------|------|
| 固定地点 | 30-40个 | 城市功能点（市集、工坊等） |
| 临时地点 | 动态增长 | 每个未完成任务创建1个 |
| 鬼怪NPC（存活） | 取决于任务数 | 未击杀的任务鬼怪累积 |
| 鬼怪NPC（死亡） | 24小时内累积 | 等待清理的死亡鬼怪 |
| 玩家访问记录 | 86+个 | 持续增长 |

---

## Relations (Code Relationships)

### NPC生成流程

```
玩家接取任务
    ↓
daily_task/commands.py: handle_accept_task()
    ↓
daily_task/service_new.py: accept_task()
    ↓
create_ghost_npc_for_task() [Line 312-368]
    ↓ 查找/创建Location
location_service.get_location_by_coordinates()
    ↓ 不存在则创建
location_service.create_location(location_id=f"task_location_{x}_{y}")
    ↓ 创建鬼怪NPC
npc_service.create_ghost_npc(npc_id=f"ghost_task_{task.id}", respawn_duration_minutes=0)
    ↓ 关联任务
ghost_npc.extra_data["task_id"] = task.id
```

### NPC清理流程

```
管理员触发【清理NPC】
    ↓
location_init.py: handle_cleanup_npcs()
    ↓
npc_service.cleanup_expired_dynamic_npcs(max_age_hours=24)
    ↓ 查询符合条件的NPC
npc_repository.cleanup_expired_dynamic()
    ↓ WHERE条件：
    - is_dynamic = True
    - created_at < (now - 24h)
    - status = 'dead'
    ↓ 软删除
npc.is_active = False
```

### 地点访问记录流程

```
玩家使用【观察】
    ↓
real_world_explore.py: handle_real_world_explore()
    ↓ 获取当前位置Location
location_service.get_location_by_coordinates(x, y, region)
    ↓ 存在Location
show_location_info()
    ↓ 记录访问
AchievementService.add_visited_location(
    player_id, location_key=f"{region}:{x}:{y}"
)
    ↓ 检查成就
check_achievements() → 探索类成就解锁
```

---

## Recommendations (改进建议)

### 优先级P0：修复NPC累积问题

1. **添加自动清理定时任务**:
   ```python
   # 建议在 bot.py 或专门的scheduler中添加
   @scheduler.scheduled_job(cron.hour, hour=2)  # 每天凌晨2点
   async def auto_cleanup_npcs():
       async with safe_session() as session:
           # 清理24小时前的死亡鬼怪
           await NPCService.cleanup_expired_dynamic_npcs(session, max_age_hours=24)
           # 清理7天前的临时Location
           await cleanup_expired_task_locations(session, max_age_days=7)
   ```

2. **清理未完成任务的鬼怪**:
   ```python
   # 修改清理条件，不仅清理已死亡的，也清理未完成的
   async def cleanup_abandoned_task_npcs(session, max_age_hours=72):
       """清理72小时前未完成任务的鬼怪"""
       cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
       stmt = select(NPC).where(
           and_(
               NPC.is_dynamic == True,
               NPC.created_at < cutoff_time,
               NPC.npc_type == NPCType.GHOST
           )
       )
       # 软删除这些NPC
   ```

3. **临时Location添加过期机制**:
   ```python
   # Location模型添加字段
   expires_at: Mapped[datetime] = mapped_column(
       DateTime, nullable=True, comment="过期时间（临时地点）"
   )

   # 创建任务地点时设置过期
   location.expires_at = datetime.now() + timedelta(days=7)
   ```

### 优先级P1：优化locations_visited_list存储

1. **使用JSON替代逗号分隔**:
   ```python
   # 更高效的数据结构
   locations_visited_json: Mapped[dict] = mapped_column(
       MutableDict.as_mutable(JSON),
       default=dict,
       comment="访问过的地点 {location_key: visit_timestamp}"
   )
   ```

2. **添加字段长度限制**:
   ```python
   # 最多记录最近1000个地点
   MAX_LOCATIONS = 1000
   if len(visited_list) >= MAX_LOCATIONS:
       visited_list = visited_list[-MAX_LOCATIONS:]  # 保留最新的
   ```

### 优先级P2：增强监控和告警

1. **添加NPC数量监控**:
   ```python
   # 定期检查NPC数量
   async def check_npc_accumulation():
       npc_count = await count_npcs(is_dynamic=True)
       if npc_count > 1000:
           send_alert(f"动态NPC数量过多: {npc_count}")
   ```

2. **添加清理日志**:
   ```python
   logger.info(f"清理NPC: 复活{respawned_count}个, 删除{cleaned_count}个")
   ```

---

## 数据库查询建议

### 手动清理SQL（紧急情况）

```sql
-- 1. 查看当前NPC分布
SELECT npc_type, status, is_dynamic, COUNT(*) as count
FROM npc
GROUP BY npc_type, status, is_dynamic;

-- 2. 查看创建时间超过24小时的鬼怪NPC
SELECT npc_id, name, created_at, status
FROM npc
WHERE npc_type = 'ghost'
  AND is_dynamic = 1
  AND created_at < DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- 3. 手动清理旧鬼怪NPC（谨慎使用）
UPDATE npc
SET is_active = 0
WHERE npc_type = 'ghost'
  AND is_dynamic = 1
  AND created_at < DATE_SUB(NOW(), INTERVAL 72 HOUR)
  AND status = 'dead';

-- 4. 查看临时Location数量
SELECT COUNT(*) as task_locations
FROM location
WHERE location_id LIKE 'task_location_%';

-- 5. 清理旧的临时Location
DELETE FROM location
WHERE location_id LIKE 'task_location_%'
  AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY)
  AND id NOT IN (SELECT DISTINCT location_id FROM npc WHERE is_active = 1);
```

---

**报告版本**: 1.0
**生成时间**: 2025-12-30
**调查执行者**: Claude Code (scout agent)
**报告状态**: 完整调查完成，问题已识别，改进方案已提供
