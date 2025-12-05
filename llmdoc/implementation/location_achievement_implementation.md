# 地点探索成就实现文档

## 实现日期
2025-12-05

## 功能概述
实现了"初探天地"成就的自动追踪和解锁功能。玩家通过探索不同地点来完成成就。

## 成就信息

**成就ID**: `world_explorer`  
**成就名称**: 初探天地 🗺️  
**完成条件**: 探索3个不同的地点  
**奖励**:
- 💰 金币：2000
- ⚡ 经验：600
- 🌙 励志文案："世界那么大，值得去看看。"

## 实现细节

### 1. 数据模型
使用 `PlayerStats` 表追踪地点访问：
- `locations_visited`: 访问过的地点数量（整数）
- `locations_visited_list`: 访问过的地点列表（逗号分隔的字符串）

地点唯一标识格式：`{region}:{x}:{y}`  
示例：`大都会:0:0`, `大都会:100:200`

### 2. 核心方法

#### AchievementService.add_visited_location()
```python
await AchievementService.add_visited_location(
    session, 
    player_id, 
    location_key  # 格式: "region:x:y"
)
```

功能：
- 解析已访问地点列表
- 检查地点是否已访问（去重）
- 添加新地点到列表
- 更新访问计数

### 3. 集成位置

#### 3.1 观察命令 (`real_world_explore.py`)
当玩家使用【观察】命令查看地点时：
- 记录地点访问
- 检查成就解锁
- 在消息中显示成就解锁通知

**代码位置**: `plugins/xiuxian_game/world/real_world_explore.py:95-102`

#### 3.2 导航到达 (`navigation.py`)
当玩家导航到达目的地时：
- 检查目的地是否有特殊地点
- 记录地点访问
- 检查成就解锁
- 在到达消息中显示成就解锁通知

**代码位置**: `plugins/xiuxian_game/world/navigation.py:181-199`

### 4. 成就检查逻辑

成就检查条件 (`achievement_service.py:291-293`):
```python
elif condition_type == "locations_visited":
    # 地点探索
    is_unlocked = stats.locations_visited >= condition_value
```

当 `locations_visited >= 3` 时，自动解锁成就并发放奖励。

## 玩家使用指南

### 如何完成"初探天地"成就？

1. **方式一：使用观察命令**
   - 前往不同的地点（如市集、缉邪司总部等）
   - 使用【观察】命令查看地点信息
   - 系统自动记录访问

2. **方式二：使用导航功能**
   - 使用【前往 地点名】导航到特殊地点
   - 到达后自动记录访问
   - 可以使用【地图】查看所有地点坐标

3. **查看进度**
   - 使用【成就 初探天地】查看详细进度
   - 使用【成就】查看所有成就列表

### 示例流程

```
玩家: 观察
系统: 🏛️ 缉邪司总部
      📍 坐标：(0,0)
      ...

玩家: 前往 上京
系统: 🎯 已到达目标位置 (100,200)
      ...

玩家: 观察
系统: 🏪 上京市集
      📍 坐标：(100,200)
      ...
      
      ✨ 成就解锁！
      ━━━━━━━━━━━━━
      🗺️ 初探天地
      💬 探索3个不同的地点，开始了解这个诡异世界的广阔
      🎁 奖励：金币+2000 怨炁+600
      🌙 世界那么大，值得去看看。
      ━━━━━━━━━━━━━
```

## 技术特性

1. **自动去重**: 重复访问同一地点不会增加计数
2. **实时追踪**: 每次访问立即更新统计数据
3. **自动解锁**: 达成条件后自动解锁并发放奖励
4. **消息通知**: 成就解锁时在当前命令输出中显示

## 测试验证

核心逻辑已通过单元测试验证：
- ✅ 地点列表解析和去重逻辑
- ✅ 访问计数正确更新
- ✅ 成就条件检查逻辑
- ✅ 重复访问不增加计数

## 相关文件

- `plugins/xiuxian_game/world/real_world_explore.py` - 观察命令集成
- `plugins/xiuxian_game/world/navigation.py` - 导航到达集成
- `plugins/xiuxian_game/achievement/achievement_service.py` - 成就服务核心逻辑
- `plugins/xiuxian_game/data/achievements.yaml` - 成就配置
- `plugins/xiuxian_game/models/achievement.py` - 数据模型定义

## 后续扩展建议

1. 可以添加更多探索类成就：
   - "游历四方"：探索10个地点
   - "天涯海角"：探索所有市集
   - "世界行者"：探索50个地点

2. 可以添加特殊地点发现成就：
   - "秘境探索者"：发现隐藏地点
   - "商业大亨"：访问所有市集

3. 可以添加区域探索成就：
   - "大都会探索者"：探索大都会区域所有地点

