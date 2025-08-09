"""
AI引导系统 - 为玩家提供游戏帮助和指令推荐
"""
import requests
import re
from typing import List, Dict, Any
from nonebot import on_message, on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import text
from .models.db import safe_session
from .models.player import Player
from .models.story_session import StorySession
from .utils import message_add_head
from .config import Config

def is_admin(user_id: str) -> bool:
    """检查用户是否为管理员"""
    config = Config()
    admin_ids = config.game_config.get("admin", {}).get("admin_ids", [])
    return user_id in admin_ids

def call_zhipu_api(messages, model="GLM-4.5-Flash"):
    """调用智谱AI API"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        "Authorization": "Bearer ***REMOVED***",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "thinking.type": "disabled"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return response.json()
    else:
        raise requests.RequestException(f"API调用失败: {response.status_code}, {response.text}")

# 数据库表结构信息，用于AI理解
DATABASE_SCHEMA = """
数据库表结构信息：

1. player表（玩家信息）：
   - id: 玩家平台ID（主键）
   - uid: 自增UID（唯一）
   - nickname: 昵称
   - level: 等级
   - sex: 性别（男/女）
   - exp: 经验值
   - attribute_points: 可分配属性点
   - region: 区域
   - x, y: 坐标位置
   - hp, max_hp: 生命值/最大生命值
   - mp, max_mp: 理智值/最大理智值
   - attack, defense, agility, luck: 基础属性
   - critical_rate, critical_damage, dodge_rate, hit_rate: 战斗属性
   - counter_rate, combo_rate, penetration_rate: 高级战斗属性
   - guild_id: 所属公会ID
   - guild_contribution: 公会贡献值
   - vip: VIP等级
   - gold, gold2: 金币/积分
   - reincarnation_level: 转数
   - inventory_capacity: 背包容量
   - is_secluded: 是否闭关
   - seclusion_start_time: 闭关开始时间
   - last_message_board_check: 最后查看留言板时间
   - created_at: 创建时间

2. guild表（公会信息）：
   - id: 公会ID（主键）
   - name: 公会名称
   - president_id: 会长玩家ID
   - level: 公会等级
   - exp: 公会经验/活跃度
   - treasury: 公会资金库
   - notice: 公会公告
   - base_x, base_y: 公会基地坐标
   - territory_range: 势力范围
   - created_at: 创建时间

3. guild_member表（公会成员）：
   - id: 自增ID
   - guild_id: 公会ID
   - player_id: 玩家ID
   - position: 职位（PRESIDENT/VICE_PRESIDENT/CORE_MEMBER/MEMBER）
   - joined_at: 加入时间

4. guild_building表（公会建筑）：
   - id: 自增ID
   - guild_id: 公会ID
   - building_type: 建筑类型（TRAINING_GROUND/ALCHEMY_ROOM/WAREHOUSE等）
   - level: 建筑等级
   - built_at: 建造时间

5. marriage表（婚姻关系）：
   - id: 自增ID
   - player1_id, player2_id: 结婚双方ID
   - married_at: 结婚时间
   - total_gift_value: 互送礼物总价值

6. mentorship表（师徒关系）：
   - id: 自增ID
   - master_id: 师父ID
   - disciple_id: 徒弟ID
   - established_at: 建立时间
   - mentor_points: 恩师点数
   - disciple_start_level: 徒弟拜师时等级

7. bank_account表（银行账户）：
   - player_id: 玩家ID（主键）
   - balance: 余额
   - last_interest: 上次利息时间

8. inventory表（背包物品）：
   - id: 物品实例ID（主键）
   - player_id: 玩家ID
   - item_id: 物品模板ID
   - quantity: 数量
   - durability: 耐久度（装备）
   - equipped: 是否已穿戴
   - extra_attrs: 附加属性JSON
   - upgrade_level: 装备升阶等级
   - gem_slots_data: 宝石孔位数据JSON
   - created_at: 获得时间

9. world_boss_cycle表（世界BOSS周期）：
   - id: 周期ID（主键）
   - cycle_key: 周期键
   - boss_name: BOSS名称
   - boss_title: BOSS称号
   - started_at: 开始时间
   - next_refresh_at: 下次刷新时间
   - settled: 是否已结算

10. world_boss_damage表（世界BOSS伤害）：
    - id: 自增ID
    - cycle_id: 周期ID
    - player_id: 玩家ID
    - total_damage: 累计伤害
    - last_attack_ts: 上次攻击时间戳
    - attacks_today: 今日攻击次数
    - attacks_reset_date: 攻击重置日期

11. alchemy_record表（炼丹记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - furnace_id: 炉子装备ID
    - recipe_key: 配方键
    - produce_item_id: 产出物品ID
    - produce_per: 每炉产出数量
    - qty: 炉数
    - success_rate: 成功率
    - duration_minutes: 耗时（分钟）
    - materials_used: 使用材料JSON
    - started_at: 开始时间
    - claimed: 是否已领取

12. market_order表（市场订单）：
    - id: 订单ID（主键）
    - player_id: 玩家ID
    - side: 订单类型（BUY/SELL）
    - item_id: 物品ID
    - price: 价格
    - quantity: 数量
    - item_instance_id: 装备实例ID（装备交易）
    - is_instance_trade: 是否装备实例交易
    - equipment_summary: 装备摘要信息
    - created_at: 创建时间

13. market_state表（市场状态）：
    - id: 自增ID
    - market_id: 市场ID
    - item_id: 商品ID
    - current_stock: 当前库存
    - max_stock: 最大库存
    - daily_sold: 今日已售出
    - daily_bought: 今日已收购
    - demand_factor: 需求因子
    - supply_factor: 供给因子
    - last_refresh_date: 上次刷新日期
    - created_at, updated_at: 时间戳

14. trade_record表（跑商交易记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - trade_type: 交易类型（buy/sell）
    - market_id: 市场ID
    - item_id: 商品ID
    - quantity: 交易数量
    - unit_price: 单价
    - total_amount: 总金额
    - trade_time: 交易时间

15. stocks表（股票信息）：
    - id: 股票ID（主键）
    - symbol: 股票代码
    - name: 股票名称
    - stock_type: 股票类型（TECH/FINANCE/ENERGY等）
    - base_price: 基础价格
    - current_price: 当前价格
    - total_shares: 总股本
    - circulating_shares: 流通股本
    - volatility: 波动率
    - trend_factor: 趋势因子
    - is_active: 是否可交易
    - created_at, updated_at: 时间戳

16. stock_holdings表（股票持仓）：
    - id: 持仓ID（主键）
    - player_id: 玩家ID
    - stock_id: 股票ID
    - shares: 持有股数
    - avg_cost: 平均成本价
    - total_cost: 总成本
    - created_at, updated_at: 时间戳

17. stock_transactions表（股票交易记录）：
    - id: 交易ID（主键）
    - player_id: 玩家ID
    - stock_id: 股票ID
    - transaction_type: 交易类型（BUY/SELL）
    - shares: 交易股数
    - price: 交易价格
    - total_amount: 交易总金额
    - commission: 手续费
    - created_at: 创建时间

18. stock_price_history表（股票价格历史）：
    - id: 历史ID（主键）
    - stock_id: 股票ID
    - price: 价格
    - change_amount: 变动金额
    - change_rate: 变动比例
    - volume: 成交量
    - recorded_at: 记录时间

19. part_time_job表（打工记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - job_location_id: 工作地点ID
    - job_type: 工作类型
    - is_working: 是否正在工作
    - start_time: 开始时间
    - end_time: 预计结束时间
    - completed_time: 实际完成时间
    - base_reward: 基础奖励
    - bonus_reward: 额外奖励
    - total_reward: 总奖励
    - work_duration_hours: 工作时长
    - consecutive_days: 连续工作天数
    - special_event: 特殊事件描述
    - extra_data: 额外数据JSON
    - created_at, updated_at: 时间戳

20. job_location表（工作地点）：
    - id: 地点ID（主键）
    - location_id: 地点标识
    - name: 地点名称
    - description: 地点描述
    - x, y: 坐标
    - region: 所属区域
    - available_jobs: 可用工作配置JSON
    - is_active: 是否激活
    - required_level: 所需最低等级
    - max_workers: 最大同时工作人数
    - created_at, updated_at: 时间戳

21. player_job_stats表（玩家打工统计）：
    - id: 统计ID（主键）
    - player_id: 玩家ID
    - total_jobs_completed: 完成工作总数
    - total_earnings: 总收入
    - total_work_hours: 总工作小时数
    - current_streak: 当前连续工作天数
    - max_streak: 最大连续工作天数
    - last_work_date: 最后工作日期
    - favorite_job_type: 最喜欢的工作类型
    - favorite_location: 最喜欢的工作地点
    - achievements: 成就数据JSON
    - created_at, updated_at: 时间戳

22. daily_task表（每日任务）：
    - id: 任务ID（主键）
    - player_id: 玩家ID
    - task_type: 任务类型（ghost_elimination/pen_spirit_case等）
    - title: 任务标题
    - description: 任务描述
    - target_region: 目标区域
    - target_x, target_y: 目标坐标
    - status: 任务状态（available/accepted/completed/expired）
    - enemy_name: 敌人名称
    - enemy_level, enemy_hp, enemy_attack, enemy_defense, enemy_agility: 敌人属性
    - exp_reward: 经验奖励
    - gold_reward: 金币奖励
    - guild_points_reward: 公会积分奖励
    - task_date: 任务日期
    - accepted_at: 接取时间
    - completed_at: 完成时间
    - created_at: 创建时间

23. guild_task_record表（公会任务记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - guild_id: 公会ID
    - task_type: 任务类型（daily_sign/daily_donation/exploration等）
    - task_date: 任务日期
    - progress: 完成进度
    - points_reward: 获得积分
    - guild_exp_reward: 公会经验奖励
    - completed_at: 完成时间

24. player_task_stats表（玩家任务统计）：
    - id: 统计ID（主键）
    - player_id: 玩家ID
    - total_explorations: 总探索次数
    - total_combat_victories: 总战斗胜利次数
    - total_commissions: 总委托完成次数
    - today_explorations: 今日探索次数
    - today_combat_victories: 今日战斗胜利次数
    - today_commissions: 今日委托完成次数
    - week_commissions: 本周委托完成次数
    - week_daily_tasks: 本周日常任务完成次数
    - last_daily_reset: 上次日常重置日期
    - last_weekly_reset: 上次周常重置日期

25. monthly_card表（月卡记录）：
    - id: 月卡ID（主键）
    - player_id: 玩家ID
    - card_type: 月卡类型（BASIC/PREMIUM）
    - start_time: 开始时间
    - end_time: 结束时间
    - created_at: 创建时间

26. elixir_usage_log表（丹药使用记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - item_id: 丹药ID
    - use_date: 使用日期
    - quantity: 使用数量

27. gift_record表（礼物记录）：
    - id: 记录ID（主键）
    - sender_id: 送礼人ID
    - receiver_id: 收礼人ID
    - item_id: 物品ID
    - item_name: 物品名称
    - quantity: 数量
    - total_value: 总价值
    - gift_type: 礼物类型（marriage/mentorship）
    - sent_at: 送礼时间

28. social_application表（社交申请）：
    - id: 申请ID（主键）
    - applicant_id: 申请人ID
    - target_id: 目标玩家ID
    - guild_id: 公会ID（公会申请）
    - application_type: 申请类型（marriage/mentorship/guild_join）
    - status: 申请状态（pending/approved/rejected）
    - created_at: 申请时间
    - processed_at: 处理时间

29. navigation_task表（导航任务）：
    - player_id: 玩家ID（主键）
    - target_x, target_y: 目标坐标
    - last_update: 上次更新时间

30. world_tile表（世界格子）：
    - id: 格子ID（主键）
    - region: 区域标识
    - x, y: 坐标
    - refreshed_at: 刷新时间
    - event_type: 事件类型
    - seed: 生成种子
    - state: 事件状态JSON

31. world_message表（世界留言）：
    - id: 留言ID（主键）
    - player_id: 玩家ID
    - content: 留言内容
    - created_at: 创建时间

32. story_session表（剧情会话）：
    - id: 会话ID（主键）
    - player_id: 玩家ID
    - story_id: 剧情ID
    - current_node: 当前节点ID
    - is_active: 是否激活
    - story_data: 剧情数据JSON
    - variables: 剧情变量JSON
    - created_at, updated_at: 时间戳

33. russian_roulette_room表（恶魔轮盘房间）：
    - id: 房间ID（主键）
    - room_id: 房间标识
    - group_id: 绑定QQ群ID
    - creator_id: 房主ID
    - player1_id, player2_id: 玩家ID
    - status: 房间状态（waiting/betting/playing/finished）
    - player1_gold_bet, player2_gold_bet: 金币投注
    - player1_items_bet, player2_items_bet: 道具投注JSON
    - max_hp: 最大血量
    - created_at, updated_at: 时间戳

34. russian_roulette_game表（恶魔轮盘游戏）：
    - id: 游戏ID（主键）
    - room_id: 房间ID
    - status: 游戏状态（loading/playing/finished）
    - current_round: 当前回合数
    - current_player_id: 当前行动玩家ID
    - player1_hp, player2_hp: 玩家血量
    - bullets: 弹药序列JSON
    - current_bullet_index: 当前弹药索引
    - player1_items, player2_items: 玩家道具JSON
    - is_sawed_off: 是否使用小刀
    - handcuffed_player_id: 被手铐限制的玩家ID
    - magnifier_info: 放大镜查看结果JSON
    - phone_info: 电话预知结果JSON
    - created_at, updated_at: 时间戳

35. player_donation_log表（玩家捐献记录）：
    - id: 记录ID（主键）
    - player_id: 玩家ID
    - donate_date: 捐献日期
    - amount: 捐献金额

常用查询示例：
- 等级最高的玩家：SELECT nickname, level, uid FROM player ORDER BY level DESC, exp DESC LIMIT 10
- 公会成员数量：SELECT g.name, COUNT(gm.player_id) as member_count FROM guild g LEFT JOIN guild_member gm ON g.id = gm.guild_id GROUP BY g.id ORDER BY member_count DESC
- 财富排行：SELECT nickname, gold, uid FROM player ORDER BY gold DESC LIMIT 10
- 银行存款排行：SELECT p.nickname, p.uid, ba.balance FROM player p JOIN bank_account ba ON p.id = ba.player_id ORDER BY ba.balance DESC LIMIT 10
- 公会资金排行：SELECT name, treasury, level FROM guild ORDER BY treasury DESC LIMIT 10
- 世界BOSS伤害排行：SELECT p.nickname, p.uid, wbd.total_damage FROM world_boss_damage wbd JOIN player p ON wbd.player_id = p.id WHERE wbd.cycle_id = (SELECT id FROM world_boss_cycle ORDER BY started_at DESC LIMIT 1) ORDER BY wbd.total_damage DESC LIMIT 10
- 股票持仓排行：SELECT p.nickname, p.uid, s.name as stock_name, sh.shares, sh.total_cost FROM stock_holdings sh JOIN player p ON sh.player_id = p.id JOIN stocks s ON sh.stock_id = s.id WHERE sh.shares > 0 ORDER BY sh.total_cost DESC LIMIT 10
- 打工收入排行：SELECT p.nickname, p.uid, pjs.total_earnings FROM player_job_stats pjs JOIN player p ON pjs.player_id = p.id ORDER BY pjs.total_earnings DESC LIMIT 10
- 结婚玩家列表：SELECT p1.nickname as player1, p1.uid as uid1, p2.nickname as player2, p2.uid as uid2, m.married_at, m.total_gift_value FROM marriage m JOIN player p1 ON m.player1_id = p1.id JOIN player p2 ON m.player2_id = p2.id ORDER BY m.total_gift_value DESC
- 师徒关系列表：SELECT master.nickname as master_name, master.uid as master_uid, disciple.nickname as disciple_name, disciple.uid as disciple_uid, mt.mentor_points FROM mentorship mt JOIN player master ON mt.master_id = master.id JOIN player disciple ON mt.disciple_id = disciple.id ORDER BY mt.mentor_points DESC

常用修改示例：
- 修改玩家坐标：UPDATE player SET x = 100, y = 200 WHERE nickname = '玩家昵称'
- 修改玩家金币：UPDATE player SET gold = 50000 WHERE uid = 1001
- 修改玩家等级：UPDATE player SET level = 100, exp = 0 WHERE nickname = '玩家昵称'
- 修改玩家属性：UPDATE player SET attack = 500, defense = 300, agility = 200, luck = 150 WHERE nickname = '玩家昵称'
- 修改公会资金：UPDATE guild SET treasury = 1000000 WHERE name = '公会名称'
- 修改银行余额：UPDATE bank_account SET balance = 500000 WHERE player_id = (SELECT id FROM player WHERE nickname = '玩家昵称')
- 修改背包容量：UPDATE player SET inventory_capacity = 100 WHERE nickname = '玩家昵称'
- 修改玩家VIP等级：UPDATE player SET vip = 5 WHERE nickname = '玩家昵称'
- 修改玩家转数：UPDATE player SET reincarnation_level = 3 WHERE nickname = '玩家昵称'
- 修改玩家生命值：UPDATE player SET hp = 1000, max_hp = 1000 WHERE nickname = '玩家昵称'
"""

async def generate_sql_from_natural_language(query_text: str) -> str:
    """使用AI将自然语言转换为SQL查询"""
    try:
        system_prompt = f"""你是一个SQL查询生成专家，专门将自然语言转换为SQL查询语句。

{DATABASE_SCHEMA}

规则：
1. 只返回SQL语句，不要任何解释或格式化
2. 使用标准SQL语法，兼容SQLite
3. 查询结果限制在100条以内（使用LIMIT）
4. 优先使用JOIN而不是子查询
5. 对于排行类查询，使用ORDER BY + LIMIT
6. 支持SELECT查询和UPDATE修改操作，禁止DELETE、DROP等危险操作
7. 如果涉及公会信息，记得JOIN相关表
8. 玩家昵称显示时优先使用nickname字段
9. UPDATE操作时要使用WHERE条件限制影响范围，避免全表更新
10. 修改玩家数据时，可以通过nickname、uid或id来定位玩家，管理员“我”的UID是100

用户查询：{query_text}

请生成对应的SQL查询语句："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query_text}
        ]

        result = call_zhipu_api(messages)
        sql_content = result['choices'][0]['message']['content'].strip()

        # 提取SQL语句（去除可能的markdown格式）
        sql_match = re.search(r'```sql\s*(.*?)\s*```', sql_content, re.DOTALL | re.IGNORECASE)
        if sql_match:
            sql_query = sql_match.group(1).strip()
        else:
            # 如果没有markdown格式，直接使用内容
            sql_query = sql_content.strip()

        # 安全检查：确保不包含危险操作（允许UPDATE，禁止DELETE等）
        dangerous_keywords = ['DELETE', 'DROP', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        sql_upper = sql_query.upper()
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                raise ValueError(f"检测到危险操作：{keyword}")

        return sql_query

    except Exception as e:
        print(f"AI生成SQL失败: {e}")
        return ""

async def execute_sql_query(sql_query: str) -> List[Dict[str, Any]]:
    """执行SQL查询或修改并返回结果"""
    async with safe_session() as session:
        try:
            result = await session.execute(text(sql_query))

            # 如果是UPDATE操作，需要提交事务
            if sql_query.upper().startswith('UPDATE'):
                await session.commit()
                # UPDATE操作返回空列表，表示成功
                return []

            # SELECT操作处理
            rows = result.fetchall()

            # 转换为字典列表，便于处理
            if rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            return []

        except Exception as e:
            await session.rollback()
            raise Exception(f"SQL执行错误：{str(e)}")

async def format_query_result(original_query: str, sql_query: str, result_data: List[Dict[str, Any]]) -> str:
    """使用AI格式化查询结果"""
    try:
        # 限制结果数量，避免消息过长
        display_data = result_data[:20]  # 最多显示20条

        system_prompt = f"""你是一个数据分析专家，负责将SQL查询结果格式化为易读的中文报告。

原始查询：{original_query}
SQL语句：{sql_query}
查询结果数量：{len(result_data)}条

格式要求：
1. 用中文回答，语言简洁明了
2. 使用表格或列表形式展示数据
3. 突出重要信息（如排名、数值等）
4. 如果结果超过20条，说明只显示前20条
5. 添加适当的emoji增强可读性
6. 对于UID，显示为"UID:{uid}"格式
7. 对于金币等数值，添加适当的单位

请将以下查询结果格式化为用户友好的报告："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(display_data)}
        ]

        result = call_zhipu_api(messages)
        formatted_content = result['choices'][0]['message']['content'].strip()

        # 添加查询统计信息
        stats_info = f"\n\n📊 查询统计：共找到 {len(result_data)} 条记录"
        if len(result_data) > 20:
            stats_info += "，仅显示前20条"

        return formatted_content + stats_info

    except Exception as e:
        # AI格式化失败时，使用简单格式
        formatted_result = f"📊 查询结果（共{len(result_data)}条）：\n\n"

        for i, row in enumerate(result_data[:10], 1):  # 最多显示10条
            formatted_result += f"{i}. "
            for key, value in row.items():
                formatted_result += f"{key}: {value} | "
            formatted_result = formatted_result.rstrip(" | ") + "\n"

        if len(result_data) > 10:
            formatted_result += f"\n... 还有 {len(result_data) - 10} 条记录"

        return formatted_result

def is_database_query(user_message: str) -> bool:
    """判断用户消息是否可能是数据库查询或修改请求"""
    # 数据库查询关键词
    query_keywords = [
        "查询", "查看", "统计", "排行", "排名", "最高", "最多", "最少", "最大", "最小",
        "有多少", "多少个", "哪个", "哪些", "什么", "谁", "前", "名", "榜",
        "玩家", "公会", "等级", "金币", "财富", "修为", "结婚", "师徒", "银行",
        "存款", "攻击", "伤害", "BOSS", "今天", "昨天", "最近"
    ]

    # 数据库修改关键词
    modify_keywords = [
        "修改", "更改", "设置", "改为", "调整", "变更", "更新", "改成",
        "坐标改为", "等级改为", "金币改为", "属性改为", "位置改为",
        "传送到", "移动到", "设为", "调为"
    ]

    # 检查是否包含查询关键词
    for keyword in query_keywords:
        if keyword in user_message:
            return True

    # 检查是否包含修改关键词
    for keyword in modify_keywords:
        if keyword in user_message:
            return True

    # 检查是否是疑问句
    question_patterns = ["？", "?", "吗", "呢", "啊"]
    for pattern in question_patterns:
        if pattern in user_message:
            return True

    return False

async def handle_admin_database_query(user_message: str, event):
    """处理管理员数据库查询和修改"""
    try:
        # 判断是查询还是修改操作
        is_modify = any(keyword in user_message for keyword in [
            "修改", "更改", "设置", "改为", "调整", "变更", "更新", "改成",
            "坐标改为", "等级改为", "金币改为", "属性改为", "位置改为",
            "传送到", "移动到", "设为", "调为"
        ])

        if is_modify:
            await ai_guide.send(message_add_head("🔧 管理员修改模式：正在分析您的修改需求...", event))
        else:
            await ai_guide.send(message_add_head("🔍 管理员查询模式：正在分析您的查询需求...", event))

        # 调用AI生成SQL
        sql_query = await generate_sql_from_natural_language(user_message)

        if not sql_query:
            await ai_guide.finish(message_add_head("❌ 无法理解需求，请重新描述或使用游戏指令", event))

        # 执行SQL
        if is_modify:
            await ai_guide.send(message_add_head("⚡ 正在执行修改操作...", event))
        else:
            await ai_guide.send(message_add_head("⚡ 正在执行查询...", event))

        result = await execute_sql_query(sql_query)

        # 处理不同类型的结果
        if sql_query.upper().startswith('UPDATE'):
            # UPDATE操作的结果处理
            await ai_guide.finish(message_add_head("✅ 修改操作执行成功！", event))
        else:
            # SELECT操作的结果处理
            if not result:
                await ai_guide.finish(message_add_head("📭 查询完成，但没有找到匹配的数据", event))

            # 调用AI整理结果
            formatted_result = await format_query_result(user_message, sql_query, result)

            # 添加管理员标识
            admin_result = f"🛡️ 管理员查询结果\n\n{formatted_result}"

            await ai_guide.finish(message_add_head(admin_result, event))

    except ValueError as e:
        await ai_guide.finish(message_add_head(f"❌ 操作执行失败：{str(e)}", event))

# 预先格式化的AI指令知识库字符串常量 - 避免每次调用时重新拼接
AI_COMMANDS_TEXT = """
游戏常识：
描述：游戏背景和基本概念
指令：
  咒抗类似体力值(签到刷新)，玩家消耗咒抗传送到诡域进行刷怪，死亡后可以【返回】现实世界，两个世界坐标共用，在现实世界可以跑商赚钱

玩家系统：
描述：查看玩家信息、排行榜，注册角色和改名。新手注册：发送【注册】，系统会引导你输入昵称。
指令：
  【面板 [UID]】 查看指定玩家面板
  【财富榜】 查看财富榜
  【修为榜】 查看修为榜
  【幸运榜】 查看幸运榜
  【战力】 查看自身完整属性
  【属性说明】 查看各项属性的作用
  【注册】 注册角色
  【改名 <新名字>】 改名
  【改性别 <男/女>】 修改角色性别

修炼系统：
描述：突破境界获得属性点，献祭材料获取怨念保驾护航
指令：
  【修炼】 获取经验，冷却时间5分钟
  【闭关】 闭关修炼，挂机升级，但效率减半
  【出关】 出关后可继续修炼
  【突破 [镇厄|棺材钉]】 突破境界，可消耗怨念或者棺材钉来确保成功
  【冥返】 300级满级后，成为一转高手，从零开始，但每级获得更多属性点，修炼效率增加
  【加点】 分配突破获得的属性点，增强实力
  【献祭】 献祭材料以获取怨念值，用于为突破护航

背包系统：
描述：管理物品，使用道具，查看图鉴。类别可选：消耗品、材料、商品、丹药、装备。每种丹药都有每日服用上限，合理安排使用计划
指令：
  【背包 [类别] [页码]】 类别用于过滤，页码用于翻页，不填则查看所有
  【使用 <物品名> <数量>】 使用指定道具
  【丢弃 <物品名> <数量>】 丢弃指定道具
  【图鉴 <关键词>】 查看物品或装备描述，丹药会显示每日限制
  【耐药性】 查看今日丹药使用状态
  【丹药加成】 查看历史服用丹药的总属性加成
  【欺骗 <源材料> <目标材料> <目标数量>】 用三倍同品质材料转换为指定材料，欺骗世界

装备系统：
描述：穿戴装备提升属性，用材料锻造新装备，升阶强化，镶嵌宝石。最多穿戴4件装备，且不能重复穿戴。等阶越高成功率越低，失败可能降级或损坏。镶嵌需要镶嵌锤，拆卸需要拆卸凿，有损坏风险。镶嵌物分10个等级，包括佛珠(暴击率/连击率/闪避率/命中率)、翡翠(反击率)、玛瑙(暴击力)、水晶(穿透率)、紫晶(灵爆率)等，可用升阶石合成升级
指令：
  【装备栏】 查看自己装备
  【装备详情 <装备ID/名称>】 查看装备详细信息和升阶效果
  【装备 <装备ID/名称>】 穿戴指定装备
  【卸下 <装备ID/名称>】 卸下指定装备
  【一键卸下】 卸下全部装备
  【锻造列表】 查看锻造列表
  【配方 <装备名称>】 查看锻造配方
  【锻造 <装备名称>】 锻造指定装备
  【修理 <装备ID/名称> [金币比例:怨念比例]】 修理指定装备
  【升阶信息 <装备ID/名称>】 查看升阶需求和成功率
  【升阶 <装备ID/名称>】 装备合成升阶（需要多个相同装备+升阶石）
  【升阶 <装备ID/名称> 稳定水晶】 使用稳定水晶提升成功率
  【升阶列表】 查看可升阶装备
  【孔位 <装备ID/名称>】 查看装备孔位信息
  【镶嵌 <装备名> <孔位号> <镶嵌物名称>】 为装备添加稀有属性
  【拆卸 <装备名> <孔位号>】 拆卸镶嵌物品（有风险）
  【镶嵌物品】 查看可镶嵌物品列表
  【镶嵌物升级 <镶嵌物名>】 查看镶嵌物升级信息
  【合成镶嵌物 <镶嵌物名>】 升级合成镶嵌物
  【可升级镶嵌物】 查看所有可升级的镶嵌物

跑商系统：
描述：利用不同坐标的差价赚取金币，每日早9点刷新基础价格，一天内的价格受供需波动，及时查看市价避免亏损。防刷钱：在某地购买的商品，8小时内不可在同地出售
指令：
  【市集】 查看当前坐标市场价格表
  【市集列表】 查看全部市集坐标
  【市集详情 <市集名称>】 查看指定市集商品
  【市价 <物品名称>】 查看某商品在各市集的买/卖价
  【购买 <物品> <数量>】 市集仅有商品类物品+血契丹+阴冥草
  【出售 <物品> <数量>】 将商品类物品卖给市场（仅限香水、红酒、金表等商品）
  【跑商记录 [页数]】 查看市集购买历史
  【跑商推荐】 查看利润最高的买卖路线

交易系统：
描述：初始6个牌子，玩家可用于出售或者收购物品，挂牌后自动以最优价撮合。交易税收：5000金币以下免税，超出部分按阶梯税率征收。装备交易：支持升阶、镶嵌等个性化属性，按实例交易
指令：
  【交易清单 [页数]】 当前所有在售与求购物品总览
  【查牌 <物品名> [页数]】 查看物品在自由市场的买卖价格
  【挂牌 <出售/收购> <物品名> <单价> [数量]】 最多挂6个牌子
  【我的挂牌 [页数]】 查看自己的所有挂牌订单
  【撤牌 <挂牌ID>】 撤回指定牌子
  【税率】 查看当前阶梯交易税率
  【估价 <装备ID>】 查看装备价值评估和市场参考

炼丹系统：
描述：消耗材料，获得丹药，丹炉属于装备，炉ID即装备ID。炼丹失败时会返还50%材料
指令：
  【丹方】 查看炼丹配方
  【炼丹状态】 查看炼丹状态
  【炼丹 <炉ID> <丹方序号|名称> <数量>】 消耗炉子、材料，获得丹药
  【收获丹药】 收获炼制完成的丹药

银行系统：
描述：冥行存取金币，查询余额时自动利滚利
指令：
  【存 <金额>】 存入冥行
  【取 <金额>】 从冥行取出
  【余额】 查询冥行存款并进行利滚利
  【存款榜】 查看冥行存款排行榜
  【银行投资】 查看灵石投资理财选项

投资系统：
描述：投资各类灵石项目，获得修仙资源收益。投资类型：法宝灵石(高波动，高风险高收益)、金融灵石(相对稳定)、灵气灵石(中等波动)、丹药灵石(较为稳定)、医道灵石(中等波动)、材料灵石(较高波动)。风险提示：灵石投资有风险，投资需谨慎！手续费：交易金额的3%
指令：
  【投资行情】 查看所有可投资项目
  【投资刷新时间】 查看灵石价格刷新时间
  【投资灵石 <代码> <数量>】 投资灵石（使用现金）
  【投资灵石 <代码> <数量> 银行】 投资灵石（使用银行资金）
  【出售灵石 <代码> <数量>】 出售灵石（收入到现金）
  【出售灵石 <代码> <数量> 银行】 出售灵石（收入到银行）
  【我的投资】 查看投资情况
  【投资记录】 查看投资记录

社交系统：
描述：结婚生子，师徒传承，互送礼物增进感情
指令：
  【求婚 <UID>】 向指定玩家求婚
  【求婚申请】 查看收到的求婚申请
  【同意求婚 <UID>】 同意求婚申请
  【拒绝求婚 <UID>】 拒绝求婚申请
  【配偶】 查看配偶信息
  【离婚】 解除婚姻关系
  【拜师 <UID>】 向指定玩家拜师
  【拜师申请】 查看收到的拜师申请
  【收徒 <UID>】 同意拜师申请
  【拒绝收徒 <UID>】 拒绝拜师申请
  【师父】 查看师父信息
  【徒弟】 查看徒弟列表
  【出师 <UID>】 逐出指定徒弟
  【脱离师门】 脱离师父
  【送礼 <UID> <物品名称> <数量>】 向配偶/师父/徒弟送礼
  【送礼记录】 查看送礼历史
  【收礼记录】 查看收礼历史
  【恩爱榜】 查看夫妻恩爱值排行榜
  【恩师榜】 查看师父恩师点排行榜
  【社交统计】 查看社交系统统计信息

公会系统：
描述：全新职位体系，建筑加成，任务系统。职位体系：会长 > 副会长 > 核心成员 > 普通成员。只有普通成员不享受经验加成。训练场建筑提供修炼效率加成，在修炼和闭关时生效
指令：
  【创建公会 <公会名>】 创建公会（消耗会长委任书）
  【我的公会】 查看公会信息
  【公会成员】 查看成员列表
  【公会列表 [页码]】 查看公会排行榜
  【加入公会 <公会ID>】 加入公会
  【退会】 退出公会（清空积分和贡献）
  【申请列表】 查看待处理申请（会长/副会长）
  【同意入会 <UID>】 审核入会（会长/副会长）
  【拒绝入会 <UID>】 审核入会（会长/副会长）
  【设置职位 <UID> <职位名>】 设置成员职位
  【设置基地】 在当前位置设立公会基地（会长，3级+）
  【转让会长 <UID>】 转让会长职位
  【解散公会】 解散公会（会长）
  【捐献金币 <金额>】 捐献获得积分，增加公会经验和资金
  【公会升级】 消耗经验和资金升级公会（会长）
  【公会建筑】 查看建筑列表
  【建造 <建筑名>】 建造或升级建筑（会长）
  【公会属性】 查看建筑提供的加成效果
  【公会任务】 查看任务列表

娱乐系统：
描述：杂七杂八的小游戏和活动。包含PVP切磋功能：无损失的玩家对战，支持暴击、连击、反击等战斗效果。包含日常API功能：摸鱼日历、摸鱼日报、每日一言、抽签占卜等。月卡权益：修炼效率提升、闭关时长增加、背包扩容、签到获得扫荡令等。API功能有频率限制，请适度使用
指令：
  【签到】 每日签到，获取奖励
  【切磋 UID】 PVP切磋，无损失的玩家对战
  【模拟战斗 UID1 UID2】 观看两个玩家的模拟战斗
  【抽签 [问题]】 中国传统诸葛灵签，显示卦象、签诗、解签
  【摸鱼日历】 获取今日摸鱼日历图片
  【每日一言】 获取励志名言警句
  【恶魔轮盘帮助】 PVP对战，可以获得对方的赌注（金币、物品）
  【试炼列表】 查看可用的互动剧情
  【月卡】 查看月卡状态和权益

打工系统：
描述：基于坐标的新手友好赚钱玩法，专为年轻玩家优化。工作时长30分钟-1小时，工资150-300金币，特殊事件最高500金币。工作地点：上京商业中心(0,0)、制造工业区(100,200)、休闲娱乐街区(-50,150)、物流配送中心(200,-100)。收入=基础收入+等级加成+运气加成+连续奖励+特殊事件
指令：
  【打工】 查看当前位置的工作机会
  【打工 <工作名称>】 开始指定工作
  【收工】 完成工作并获得奖励
  【工作状态】 查看当前工作状态
  【工作地点】 查看所有工作地点
  【打工记录】 查看打工历史
  【打工统计】 查看打工数据统计
  【打工帮助】 查看使用指南

世界系统：
描述：依赖敏捷进行坐标移动，可搭配跑商玩法赚钱
指令：
  【导航 [x] [y]】 开启/查看导航进度
  【中断导航】 取消当前导航
  【附近玩家】 查看附近玩家
  【留言 <内容>】 在世界留言板发布信息
  【留言板 [页码]】 查看世界留言板
  【更新】 查看最近一次更新公告
  【世界BOSS】 查看当前BOSS信息与规则
  【攻击BOSS】 对当前BOSS发起攻击（每日3次）
  【BOSS排行】 查看本期累计伤害排行榜，获得宝箱
  【开启深渊宝箱】 开启获得的深渊宝箱奖励

副本系统：
描述：每日耗费咒抗进入诡域探索，进入后尽可能拿到更多的经验和材料
指令：
  【传送 <诡域>】 进入指定诡域
  【诡域】 查看当前可探索的诡域
  【上|下|左|右】 向指定方向移动一格
  【返回】 返回现实世界并满状态
  【探索】 探索玩家所在地点
  【使用 扫荡令】 扫荡当前诡域，消耗1点咒抗获得经验和材料

赞助系统：
描述：支持游戏发展，获得月卡权益和背包扩容。8.8元基础月卡（修炼效率+20%，闭关上限9小时，背包+5格，签到获得扫荡令），28.8元高级月卡（修炼效率+50%，闭关上限12小时，背包+20格，副本自动采集，签到获得更多扫荡令），5元永久背包扩容+5格。扫荡令是氪金玩家专属货币，可兑换珍贵的真还魂丹
指令：
  【赞助】 查看赞助码系统帮助
  【月卡】 查看月卡状态和权益
  【扫荡令兑换】 查看扫荡令兑换商店
  【兑换真还魂丹 数量】 用扫荡令兑换真还魂丹
"""

# AI引导处理器 - 优先级设置为最低，确保不会拦截其他指令
ai_guide = on_message(priority=20, block=False)

@ai_guide.handle()
async def handle_ai_guide(event: MessageEvent):
    """AI引导处理器"""
    try:
        user_message = event.get_plaintext().strip()
        
        # 忽略空消息或过短消息
        if not user_message or len(user_message) < 2:
            return

        # 忽略纯数字消息（可能是剧情选择）
        if user_message.isdigit():
            return

        # 忽略过长消息（可能是复制粘贴的内容）
        if len(user_message) > 100:
            return
            
        async with safe_session() as session:
            player = await session.get(Player, event.get_user_id())
            # 检查是否在剧情状态中
            story_session = await StorySession.get_active_session(session, player.id)
            if story_session:
                return  # 剧情状态中不处理AI引导

            # 检查是否为管理员，如果是则尝试数据库查询
            if is_admin(event.get_user_id()):
                # 判断是否可能是数据库查询请求
                if is_database_query(user_message):
                    await handle_admin_database_query(user_message, event)
                    return

            # 先发送搜索提示，缓解玩家焦虑
            await ai_guide.send(message_add_head("未检测到正确指令，正在思考您的问题...", event))

            # 调用AI进行引导
            response = await get_ai_guidance(user_message, player)
            if response:
                response += "\n━━━━━━━━━━━━━\n【】括号里的才是指令，外面是指令说明"
                await ai_guide.finish(message_add_head(response, event))
                
    except ValueError:
        pass

async def get_ai_guidance(user_message: str, player: Player) -> str:
    """获取AI引导回复"""
    try:
        # 构建系统提示
        system_prompt = f"""你是《诡修仙》QQ机器人文游的AI助手，专门为玩家提供游戏帮助。

玩家信息：
- 昵称：{player.nickname}[UID：{player.uid}]
- 等级：{player.level}级

游戏指令知识库：
{AI_COMMANDS_TEXT}

回复规则：
1. 只回答游戏相关问题，对于游戏外话题直接回复"该话题未检索到结果"
2. 根据玩家问题推荐最相关的指令，优先推荐2-3个核心指令，尽可能先帮玩家填一些已知参数
3. 如果你收到了一条疑似指令的消息，请你告知玩家正确的指令
4. 回复要简洁明了，控制在150字以内
5. 用简短语言解释指令作用，不要长篇大论

回复格式：
🤖 [简短回答]
推荐指令：
• 【指令1 <必选参数> [可选参数]】简要说明
• 【指令2】...

接下来是玩家发送的消息："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        result = call_zhipu_api(messages)
        return result['choices'][0]['message']['content']

    except Exception:
        # AI调用失败时的简单回复
        return "🤖 助手暂时无法回应，请发送【帮助】查看游戏指令"
