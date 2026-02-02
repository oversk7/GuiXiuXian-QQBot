"""
AI引导系统 - 为玩家提供游戏帮助和指令推荐
"""
import aiohttp
import asyncio
import re
import logging
from typing import List, Dict, Any
from nonebot import on_message, on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import text
from .models.db import safe_session
from .models.player import Player
from .models.story_session import StorySession
from .utils import message_add_head
from .config import Config

logger = logging.getLogger(__name__)

async def call_ai_with_fallback(messages: list) -> dict:
    """
    调用AI API并支持fallback降级机制

    Args:
        messages: 对话消息列表

    Returns:
        AI API返回结果

    Raises:
        Exception: 所有provider均失败时抛出异常
    """
    from .config import config

    # 读取AI配置
    ai_config = config.game_config.get("ai_dialogue", {})
    provider = ai_config.get("provider", "zhipu")
    zhipu_config = ai_config.get("zhipu", {})
    ai302_config = ai_config.get("ai302", {})
    timeout = zhipu_config.get("timeout", 30)

    # 降级策略配置
    fallback_config = ai_config.get("fallback", {})
    fallback_enabled = fallback_config.get("enabled", True)
    fallback_provider = fallback_config.get("fallback_provider", "ai302")

    errors = []

    # 尝试主provider
    try:
        if provider == "zhipu":
            logger.info(f"[AI引导] 使用智谱AI调用...")
            result = await call_zhipu_api(
                messages,
                model=zhipu_config.get("model", "GLM-4-Flash-250414"),
                timeout=timeout
            )
            logger.info(f"[AI引导] 智谱AI调用成功")
            return result
        elif provider == "ai302":
            logger.info(f"[AI引导] 使用302.ai调用...")
            result = await call_302ai_api(
                messages,
                model=ai302_config.get("model", "gpt-3.5-turbo"),
                timeout=timeout
            )
            logger.info(f"[AI引导] 302.ai调用成功")
            return result
        else:
            raise ValueError(f"不支持的provider: {provider}")

    except Exception as e:
        error_msg = f"{provider} 调用失败: {type(e).__name__}: {str(e)}"
        logger.warning(f"[AI引导] {error_msg}")
        errors.append(error_msg)

        # 如果fallback未启用，直接抛出异常
        if not fallback_enabled:
            raise

        # 尝试fallback provider
        try:
            fallback = fallback_provider
            if fallback == provider:
                # fallback provider与主provider相同，直接抛出异常
                raise Exception(f"主provider和fallback provider相同，无法降级")

            logger.warning(f"[AI引导] 尝试降级到备用provider: {fallback}")

            if fallback == "zhipu":
                result = await call_zhipu_api(
                    messages,
                    model=zhipu_config.get("model", "GLM-4-Flash-250414"),
                    timeout=timeout
                )
                logger.info(f"[AI引导] 备用provider {fallback} 调用成功")
                return result
            elif fallback == "ai302":
                result = await call_302ai_api(
                    messages,
                    model=ai302_config.get("model", "gpt-3.5-turbo"),
                    timeout=timeout
                )
                logger.info(f"[AI引导] 备用provider {fallback} 调用成功")
                return result
            else:
                raise ValueError(f"不支持的fallback provider: {fallback}")

        except Exception as fallback_error:
            fallback_error_msg = f"{fallback} 调用失败: {type(fallback_error).__name__}: {str(fallback_error)}"
            logger.error(f"[AI引导] {fallback_error_msg}")
            errors.append(fallback_error_msg)

            # 所有provider都失败，抛出综合异常
            raise Exception(f"所有AI provider均失败: {'; '.join(errors)}")

def is_admin(user_id: str) -> bool:
    """检查用户是否为管理员"""
    config = Config()
    admin_ids = config.game_config.get("admin", {}).get("admin_ids", [])
    return user_id in admin_ids


def is_sub_admin(user_id: str) -> bool:
    """检查用户是否为子管理员"""
    config = Config()
    sub_admin_ids = config.game_config.get("admin", {}).get("sub_admin_ids", [])
    return user_id in sub_admin_ids


async def call_zhipu_api(messages, model="GLM-4.5-Flash", timeout=30):
    """调用智谱AI API（异步版本）"""
    from .config import config

    # 从配置文件读取API密钥
    ai_config = config.game_config.get("ai_dialogue", {})
    zhipu_config = ai_config.get("zhipu", {})
    api_key = zhipu_config.get("api_key", "")

    if not api_key:
        raise ValueError("智谱AI API密钥未配置，请在config.yaml中配置 ai_dialogue.zhipu.api_key")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "thinking.type": "disabled"
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        raise TimeoutError(f"AI API调用超时（{timeout}秒）")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"网络请求失败: {str(e)}")


async def call_302ai_api(messages, model="gpt-3.5-turbo", timeout=30):
    """调用302.ai API（异步版本，OpenAI兼容接口）"""
    from .config import config

    # 从配置文件读取API密钥
    ai_config = config.game_config.get("ai_dialogue", {})
    ai302_config = ai_config.get("ai302", {})
    api_key = ai302_config.get("api_key", "")

    if not api_key:
        raise ValueError("302.ai API密钥未配置，请在config.yaml中配置 ai_dialogue.ai302.api_key")

    url = "https://api.302.ai/v1/chat/completions"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 处理messages格式（确保兼容OpenAI格式）
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })

    data = {
        "model": model,
        "messages": formatted_messages
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"302.ai API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        raise TimeoutError(f"302.ai API调用超时（{timeout}秒）")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"302.ai 网络请求失败: {str(e)}")


# 数据库表结构信息，用于AI理解（优化版：专注玩家面板数据）
DATABASE_SCHEMA = """
数据库核心表：player表（玩家面板数据，共87个字段）

【基础信息】
- id: 玩家平台ID（主键，String(32)）
- uid: 自增UID（唯一，Integer）
- nickname: 昵称（String(24)）
- level: 等级（Integer）
- sex: 性别（男/女，String(8)）
- created_at: 创建时间（DateTime）

【经验和属性点】
- exp: 当前经验值（Integer）
- attribute_points: 可分配属性点（Integer）
- reincarnation_level: 转数/冥返次数（Integer）
- breakthrough_fail_count: 当前连续突破失败次数（Integer）

【基础属性】
- attack: 攻击力（Integer）
- defense: 防御力（Integer）
- agility: 敏捷度（Integer）
- luck: 运气值（Integer）
- stamina: 咒抗/精神抗性（Integer）

【HP/MP系统】
- hp: 当前生命值（Integer）
- max_hp: 最大生命值（Integer）
- mp: 当前理智值（Integer）
- max_mp: 最大理智值（Integer）

【扩展战斗属性】
- critical_rate: 暴击率（百分比，Integer）
- critical_power: 暴击力（Integer）
- combo_rate: 连击率（百分比，Integer）
- counter_rate: 反击率（百分比，Integer）
- dodge_rate: 闪避率（百分比，Integer）
- accuracy_rate: 命中率（百分比，Integer）
- skill_crit_rate: 灵爆率（百分比，Integer）
- penetration_rate: 穿透率（百分比，Integer）
- anti_crit_rate: 抗暴率（百分比，Integer）
- lifesteal_rate: 吸血率（百分比，Integer）
- immobilize_rate: 定身率（百分比，Integer）
- true_damage_rate: 真伤率（百分比，Integer）
- regen_rate: 回血率（百分比，Integer）

【战斗统计】
- total_battles: 总战斗次数（Integer）
- total_wins: 总胜利次数（Integer）
- total_damage_dealt: 总造成伤害（Integer）
- resentment: 怨念值（Integer）

【经济系统】
- gold: 金币（BigInteger）
- gold2: 积分（BigInteger）
- mini_game_score: 小游戏积分（Integer）

【签到系统】
- last_sign: 上次签到日期（DateTime，可为空）
- sign_streak: 连续签到天数（Integer）
- last_cultivation: 上次修炼时间（DateTime，可为空）

【坐标系统】
- region: 区域名称（String(32)）
- x: 当前X坐标（Integer）
- y: 当前Y坐标（Integer）
- real_world_x: 现实世界X坐标（Integer）
- real_world_y: 现实世界Y坐标（Integer）
- dungeon_level: 诡域层级/0=现实世界（Integer）
- dungeon_x: 诡域内X坐标（Integer）
- dungeon_y: 诡域内Y坐标（Integer）
- max_dungeon_level: 最高诡域层级（Integer）

【其他系统】
- guild_id: 所属公会ID（Integer，可为空）
- guild_contribution: 公会贡献值（BigInteger）
- mansion_level: 阴宅等级（Integer）
- mansion_x, mansion_y: 阴宅坐标（Integer，可为空）
- inventory_capacity: 背包容量（Integer）
- vip: VIP等级（Integer）
- is_secluded: 是否闭关（Boolean）
- seclusion_start_time: 闭关开始时间（DateTime，可为空）

辅助表（仅需了解关系，不提供详细字段）：
- guild表: 公会信息（与player.guild_id关联）
- inventory表: 背包物品（通过player_id关联玩家）
- bank_account表: 银行账户（通过player_id关联玩家）
- marriage表: 婚姻关系（记录结婚双方）
- mentorship表: 师徒关系（master_id, disciple_id）
- world_boss_damage表: 世界BOSS伤害记录
- alchemy_record表: 炼丹记录
- market_order表: 市场订单
- 其他30余张业务表（stock, part_time_job, daily_task等）

常用查询示例（player表）：
- 等级最高的玩家：SELECT nickname, level, uid FROM player ORDER BY level DESC, exp DESC LIMIT 10
- 财富排行：SELECT nickname, gold, uid FROM player ORDER BY gold DESC LIMIT 10
- 查询特定玩家：SELECT * FROM player WHERE nickname = '玩家昵称' 或 WHERE uid = 1001

常用修改示例（player表）：
- 修改玩家坐标：UPDATE player SET x = 100, y = 200 WHERE uid = 1001
- 修改玩家金币：UPDATE player SET gold = 50000 WHERE uid = 1001
- 修改玩家等级：UPDATE player SET level = 100, exp = 0 WHERE uid = 1001
- 修改玩家属性：UPDATE player SET attack = 500, defense = 300, agility = 200, luck = 150 WHERE uid = 1001
- 修改背包容量：UPDATE player SET inventory_capacity = 100 WHERE uid = 1001
- 修改玩家VIP等级：UPDATE player SET vip = 5 WHERE uid = 1001
- 修改玩家转数：UPDATE player SET reincarnation_level = 3 WHERE uid = 1001
- 修改玩家生命值：UPDATE player SET hp = 1000, max_hp = 1000 WHERE uid = 1001

完整玩家面板数据覆盖示例（根据【面板】命令显示的数据）：
当管理员提供一个玩家的面板数据时，应生成包含所有关键字段的UPDATE语句：

示例1 - 基础面板数据覆盖：
UPDATE player SET
  nickname = '张三',
  level = 100,
  exp = 5000,
  sex = '男',
  hp = 1000,
  max_hp = 1000,
  mp = 800,
  max_mp = 800,
  attack = 500,
  defense = 300,
  agility = 200,
  luck = 150,
  stamina = 50,
  gold = 100000,
  gold2 = 5000,
  attribute_points = 10,
  resentment = 500,
  vip = 3,
  reincarnation_level = 2,
  real_world_x = 100,
  real_world_y = 200,
  dungeon_level = 0
WHERE uid = 1001

示例2 - 完整战斗属性覆盖：
UPDATE player SET
  nickname = '李四',
  level = 150,
  exp = 8000,
  hp = 2000,
  max_hp = 2000,
  mp = 1500,
  max_mp = 1500,
  attack = 800,
  defense = 600,
  agility = 400,
  luck = 200,
  stamina = 80,
  critical_rate = 45,
  critical_power = 30,
  combo_rate = 25,
  counter_rate = 15,
  dodge_rate = 35,
  accuracy_rate = 95,
  skill_crit_rate = 20,
  penetration_rate = 30,
  anti_crit_rate = 25,
  lifesteal_rate = 10,
  immobilize_rate = 5,
  true_damage_rate = 8,
  regen_rate = 12,
  gold = 500000,
  gold2 = 10000,
  resentment = 1000,
  reincarnation_level = 3,
  vip = 5
WHERE nickname = '李四'

示例3 - 坐标系统完整覆盖：
UPDATE player SET
  real_world_x = 390,
  real_world_y = 50,
  dungeon_level = 5,
  dungeon_x = 3,
  dungeon_y = -2,
  max_dungeon_level = 8,
  region = '5层诡域',
  x = 3,
  y = -2
WHERE uid = 1001

⚠️ 重要提示：
1. 根据玩家面板显示的数据，只更新有提供的字段，不要更新未提供的字段
2. 如果面板显示玩家在诡域中，需要同时设置 dungeon_level、dungeon_x、dungeon_y、region、x、y
3. 如果面板显示玩家在现实世界，设置 dungeon_level=0，并更新 real_world_x、real_world_y
4. 装备加成已经持久化在 attack、defense 等基础属性中，不要单独设置装备加成
5. Boolean字段：is_secluded、mansion_allow_others等，使用0/1或true/false
6. DateTime字段可为空的用NULL，例如：last_sign = NULL
7. 定位玩家优先使用 uid，其次 nickname，最后 id（平台ID）
"""

async def generate_sql_from_natural_language(query_text: str) -> str:
    """使用AI将自然语言转换为SQL查询"""
    try:
        system_prompt = f"""你是一个SQL查询生成专家，专门将自然语言转换为SQL查询语句。

{DATABASE_SCHEMA}

【⚠️ 严格约束 - 防止编造字段】
1. ⚠️ 只能使用上面DATABASE_SCHEMA中明确列出的字段名
2. ⚠️ 如果schema中没有某个字段，不要编造，改用其他方法或直接拒绝
3. ⚠️ 不要使用别名、注释或任何非标准SQL语法
4. ⚠️ 字段名必须完全匹配，区分大小写

规则：
1. 只返回SQL语句，不要任何解释或格式化
2. 使用标准SQL语法，兼容SQLite
3. 查询结果限制在100条以内（使用LIMIT）
4. 优先使用JOIN而不是子查询
5. 对于排行类查询，使用ORDER BY + LIMIT
6. ⚠️ 只支持SELECT查询和UPDATE修改操作，禁止DELETE、DROP、INSERT、ALTER等危险操作
7. 如果涉及公会信息，记得JOIN相关表
8. 玩家昵称显示时优先使用nickname字段
9. ⚠️ UPDATE操作时必须使用WHERE条件，避免全表更新
10. 修改玩家数据时，可以通过nickname、uid或id来定位玩家

【玩家面板数据覆盖专用规则】：
当用户提供一个玩家的完整面板数据时：
11. 识别面板中提供的所有字段（与schema对比，只使用存在的字段）
12. 生成包含所有识别字段的UPDATE语句，确保字段名与player表完全匹配
13. 注意坐标系统：
    - 如果在诡域：设置dungeon_level>0，dungeon_x，dungeon_y，region（如"5层诡域"）
    - 如果在现实世界：设置dungeon_level=0，real_world_x，real_world_y，region="大都会"
14. ⚠️ 扩展战斗属性字段名务必准确（参考schema中的实际字段名）：
    - critical_power（不是critical_damage）
    - accuracy_rate（不是hit_rate）
    - skill_crit_rate（灵爆率）
    - anti_crit_rate（抗暴率）
15. 识别面板中的"装备加成"时，不要尝试单独设置，因为加成已持久化在基础属性中
16. Boolean字段使用0或1（如is_secluded=0或1）
17. 优先使用WHERE uid = ? 来定位玩家
18. ⚠️ 如果用户要求修改/查询schema中不存在的字段，回复"ERROR: 字段不存在"

用户查询：{query_text}

请生成对应的SQL查询语句（只输出SQL，不要有任何其他文字）："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query_text}
        ]

        result = await call_ai_with_fallback(messages)
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

    except TimeoutError as e:
        print(f"AI生成SQL超时: {e}")
        return ""
    except (aiohttp.ClientError, aiohttp.ClientResponseError) as e:
        print(f"AI API网络错误: {e}")
        return ""
    except ValueError as e:
        # 危险操作检测，重新抛出
        raise e
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

【⚠️ 严格约束】
1. ⚠️ 只基于实际查询结果的数据进行格式化
2. ⚠️ 不要编造、推断或添加任何不存在的数据
3. ⚠️ 如果数据为空，直接说"未找到匹配数据"
4. ⚠️ 不要添加表格外的任何统计、分析或建议

原始查询：{original_query}
SQL语句：{sql_query}
查询结果数量：{len(result_data)}条

格式要求：
1. 用中文回答，语言简洁明了
2. 使用表格或列表形式展示数据
3. 突出重要信息（如排名、数值等）
4. 如果结果超过20条，说明只显示前20条
5. 添加适当的emoji增强可读性
6. 对于UID，显示为"UID:{{uid}}"格式
7. 对于金币等数值，添加适当的单位

请将以下查询结果格式化为用户友好的报告（只展示实际数据，不要添加额外内容）："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(display_data)}
        ]

        result = await call_ai_with_fallback(messages)
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
        print(sql_query)
        if not sql_query:
            await ai_guide.finish(message_add_head("❌ 无法理解需求，请重新描述或使用游戏指令", event))
            return

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
            return
        else:
            # SELECT操作的结果处理
            if not result:
                await ai_guide.finish(message_add_head("📭 查询完成，但没有找到匹配的数据", event))
                return

            # 调用AI整理结果
            formatted_result = await format_query_result(user_message, sql_query, result)

            # 添加管理员标识
            admin_result = f"🛡️ 管理员查询结果\n\n{formatted_result}"

            await ai_guide.finish(message_add_head(admin_result, event))
            return

    except TimeoutError:
        await ai_guide.finish(message_add_head("⏰ AI分析超时，请稍后重试或使用游戏指令", event))
        return
    except (aiohttp.ClientError, aiohttp.ClientResponseError):
        await ai_guide.finish(message_add_head("🌐 网络连接失败，请稍后重试", event))
        return
    except ValueError as e:
        await ai_guide.finish(message_add_head(f"❌ 操作执行失败：{str(e)}", event))
        return

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
  【邀请码】 查看我的邀请码和分级奖励说明
  【绑定邀请码 <邀请码>】 绑定好友邀请码获得奖励
  【邀请状态】 查看邀请奖励发放状态

修炼系统：
描述：突破境界获得属性点，献祭材料获取怨念保驾护航，失败一次+1%成功率
指令：
  【修炼】 获取经验，冷却时间5分钟
  【闭关】 闭关修炼，挂机升级，但效率减半
  【出关】 出关后可继续修炼
  【突破 [镇厄|棺材钉]】 突破境界，可消耗怨念或者棺材钉来确保成功
  【连续突破 [镇厄]】 连续突破直到修为或怨念耗尽，可选择是否使用镇厄
  【冥返】 300级满级后，成为一转高手，从零开始，但每级获得更多属性点，修炼效率增加
  【加点】 分配突破获得的属性点，增强实力
  【加点帮助】 查看属性详解和推荐加点方案
  【免费洗点】 新手专用，30级以下消耗5点咒抗重置属性点
  【献祭】 献祭材料以获取怨念值，用于为突破护航

背包系统：
描述：管理物品，使用道具，查看图鉴。类别可选：消耗品、材料、商品、丹药、装备、宝石。每种丹药都有每日服用上限，合理安排使用计划。宝石类物品支持堆叠
指令：
  【背包 [类别/物品名] [页码]】 类别用于过滤，页码用于翻页，不填则查看所有；也可直接输入物品名查询数量
  【鱼栏 [页码]】 查看鱼类仓储情况，鱼类不占用背包空间
  【使用 <物品名> <数量>】 使用指定道具
  【丢弃 <物品名> <数量>】 丢弃指定道具（鱼类会显示放生文案和功德增加）
  【图鉴 <关键词>】 查看物品或装备描述，丹药会显示每日限制
  【耐药性】 查看今日丹药使用状态
  【丹药加成】 查看历史服用丹药的总属性加成
  【欺骗 <源材料> <目标材料> <目标数量>】 用三倍同品质材料转换为指定材料，欺骗世界

装备系统：
描述：穿戴装备提升属性，用材料锻造新装备，升阶强化，镶嵌宝石。装备栏显示简短编号（1、2、3...）方便操作，支持使用编号或装备名称进行操作。最多穿戴4件装备，且不能重复穿戴。升阶成功率：1-3阶高(95%-85%)，4-6阶中等(80%-70%)，7-10阶较低(60%-25%)，运气值最多+20%成功率，稳定水晶+20%。装备升阶失败损坏时会随机回收一个镶嵌物。镶嵌需要镶嵌锤，拆卸需要拆卸凿，有损坏风险。镶嵌物分10个等级，包括佛珠(暴击率/连击率/闪避率/命中率)、翡翠(反击率)、玛瑙(暴击力)、水晶(穿透率)、紫晶(灵爆率)、符文(抗暴率)等，可用升阶石合成升级。镶嵌物升级失败时会降阶（1级失败会消失），运气值最多+20%成功率，稳定水晶可保护
指令：
  【装备栏】 查看自己装备（显示简短编号）
  【装备详情 <编号/名称>】 查看装备详细信息和升阶效果
  【装备 <编号/名称>】 穿戴指定装备
  【卸下 <编号/名称>】 卸下指定装备
  【一键卸下】 卸下全部装备
  【锻造列表】 查看锻造列表
  【配方 <装备名称>】 查看锻造配方
  【锻造 <装备名称>】 锻造指定装备
  【修理 <编号/名称> [金币比例:怨念比例]】 修理指定装备
  【升阶信息 <编号/名称>】 查看升阶需求和成功率
  【升阶 <编号/名称>】 装备合成升阶（需要多个相同装备+升阶石）
  【升阶 <编号/名称> 稳定水晶】 使用稳定水晶提升成功率
  【升阶列表】 查看可升阶装备（显示简短编号）
  【孔位 <编号/名称>】 查看装备孔位信息
  【镶嵌 <编号/名称> <孔位号> <镶嵌物名称>】 为装备添加稀有属性
  【拆卸 <编号/名称> <孔位号>】 拆卸镶嵌物品（有风险）
  【镶嵌物品】 查看可镶嵌物品列表
  【镶嵌物升级 <镶嵌物名>】 查看镶嵌物升级信息
  【合成镶嵌物 <镶嵌物名>】 升级合成镶嵌物
  【可升级镶嵌物】 查看所有可升级的镶嵌物

跑商系统：
描述：利用不同坐标的差价赚取金币，每日早9点刷新基础价格，一天内的价格受供需波动，及时查看市价避免亏损。缉邪司总部商店位于风雪镇(-5,390)，用积分兑换升阶材料和抗暴符文1-5级，无需加入公会。防刷钱：在某地购买的商品，4小时内不可在同地出售。携带限制：背包中商品总量不能超过500个，防止垄断库存。跑商推荐系统会根据玩家个人交易记录智能过滤受限制影响的路线
指令：
  【市集】 查看当前坐标市场价格表
  【市集列表】 查看全部市集坐标
  【市集详情 <市集名称>】 查看指定市集商品
  【市价 <物品名称>】 查看某商品在各市集的买/卖价
  【购买 <物品> <数量>】 市集仅有商品类物品+血契丹+阴冥草
  【出售 <物品> <数量>】 将商品类物品卖给市场（包括翡翠手镯、香水、红酒等商品）
  【跑商记录 [页数]】 查看市集购买历史
  【跑商推荐】 查看个性化盈利路线推荐（已过滤交易限制）
  【交易限制】 查看当前交易限制情况
  【缉邪司总部】 查看总部商店（风雪镇 -5,390）
  【总部兑换 <物品名称> [数量]】 用积分兑换升阶材料和抗暴符文

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
描述：消耗材料，获得丹药，炼丹炉可通过升阶提升成功率。炼丹失败时会返还50%材料，自动使用最高阶炼丹炉
指令：
  【丹方 [页数|关键词]】 查看或搜索炼丹配方
  【炼丹状态】 查看炼丹状态
  【炼丹 <丹方序号|名称> <数量>】 自动选择最高阶炼丹炉进行炼丹
  【收获丹药】 收获炼制完成的丹药
升阶效果：炼丹炉+0阶成功率×1.0，每升1阶成功率+0.1，最高+10阶成功率×2.0。同时升阶还能降低耐久消耗

银行系统：
描述：冥行存取金币，查询余额时自动利滚利
指令：
  【存 <金额>】 存入冥行
  【取 <金额>】 从冥行取出
  【余额】 查询冥行存款并进行利滚利
  【转账 <UID> <金额>】 向其他玩家转账（收取3%手续费）
  【存款榜】 查看冥行存款排行榜
  【银行投资】 查看气运投资理财选项

投资系统：
描述：投资各类气运项目，获得修仙资源收益。投资类型：法宝气运(高波动，高风险高收益)、金融气运(相对稳定)、灵气气运(中等波动)、丹药气运(较为稳定)、医道气运(中等波动)、材料气运(较高波动)。风险提示：气运投资有风险，投资需谨慎！手续费：交易金额的3%
指令：
  【投资行情】 查看所有可投资项目
  【投资刷新时间】 查看气运价格刷新时间
  【投资气运 <代码> <数量>】 投资气运（使用现金）
  【投资气运 <代码> <数量> 银行】 投资气运（使用银行资金）
  【出售气运 <代码> <数量>】 出售气运（收入到现金）
  【出售气运 <代码> <数量> 银行】 出售气运（收入到银行）
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
描述：训练场修炼加成，丹房领取丹药，传送阵。职位体系：会长 > 副会长 > 核心成员 > 普通成员。只有普通成员不享受经验加成。
指令：
  【创建公会 <公会名>】 创建公会（消耗会长委任书）
  【我的公会】 查看公会信息
  【公会成员 [页码]】 查看成员列表（20人/页）
  【公会列表 [页码]】 查看公会排行榜（显示公会ID）
  【加入公会 <公会ID>】 加入公会（从公会列表获取ID）
  【退会】 退出公会（清空积分和贡献）
  【申请列表】 查看待处理申请（会长/副会长）
  【同意入会 <UID>】 审核入会（会长/副会长）
  【拒绝入会 <UID>】 审核入会（会长/副会长）
  【设置职位 <UID> <职位名>】 设置成员职位
  【踢出公会 <UID>】 踢出公会成员（会长/副会长）
  【设置基地】 在当前位置设立公会基地（会长，3级+）
  【转让会长 <UID>】 转让会长职位
  【解散公会】 解散公会（会长）
  【捐献金币 <金额>】 捐献获得积分，增加公会经验和资金
  【公会升级】 消耗经验和资金升级公会（会长）
  【公会建筑】 查看建筑列表和加成
  【建造 <建筑名>】 建造或升级建筑（会长）
  【公会传送】 传送到公会基地（要求传送阵）
  【公会传送 x y】 在基地时传送到势力范围内坐标（不消耗次数）
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
  【恶魔轮盘帮助】 PVP对战，可以获得对方的赌注（仅金币，系统抽取3%税收）
  【试炼列表】 查看可用的互动剧情
  【月卡】 查看月卡状态和权益

打工系统：
描述：基于坐标的新手友好赚钱玩法，专为年轻玩家优化。工作时长2-3分钟，工资60-180金币，特殊事件最高300金币。工作地点：上京商业中心(0,0)、荔湾镇工业区(120,200)、郸城娱乐街区(120,120)、东郊物流中心(390,50)。
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
  【观察】 查看当前位置信息（地点、NPC、附近玩家）
  【交互 <NPC名称>】 与指定NPC交互（支持部分名称匹配）
  【攻击 <目标>】 攻击玩家或NPC（支持智能匹配，如"攻击 乔强"可匹配"邪教徒·乔强"）
  【NPC列表】 查看当前位置的所有NPC
  【留言 <内容>】 在世界留言板发布信息
  【私信 UID 内容】 给指定修士发送私信
  【留言板 [世界/私信] [页码]】 查看世界留言或私信箱
  【更新】 查看最近一次更新公告
  【世界BOSS】 查看当前BOSS信息与规则
  【讨伐BOSS】 对当前BOSS发起攻击（每日3次，使用完整战斗属性）
  【BOSS排行】 查看本期累计伤害排行榜，获得宝箱
  【开启深渊宝箱】 开启获得的深渊宝箱奖励

副本系统：
描述：每日耗费咒抗进入诡域探索，进入后尽可能拿到更多的经验和材料
指令：
  【传送 <诡域>】 进入指定诡域（支持"第N层诡域"格式）
  【诡域】 查看当前可探索的诡域
  【上|下|左|右】 向指定方向移动一格
  【上一层|下一层】 在诡域中快速切换层级（需已解锁）
  【返回】 返回现实世界并满状态
  【探索】 探索玩家所在地点
  【使用 扫荡令】 扫荡当前诡域，消耗1点咒抗获得经验和材料
  【探索宝箱】 查看可领取的深渊探索者宝箱
  【领取宝箱】 一键领取所有可领取的深渊探索者宝箱

赞助系统：
描述：支持游戏发展，获得月卡权益和背包扩容。8.8元基础月卡（修炼效率+20%，闭关上限9小时，背包+5格，签到获得扫荡令），28.8元高级月卡（修炼效率+50%，闭关上限12小时，背包+20格，副本自动采集，签到获得更多扫荡令），5元永久背包扩容+5格。扫荡令是氪金玩家专属货币，可兑换珍贵的真还魂丹
指令：
  【赞助】 查看赞助码系统帮助
  【月卡】 查看月卡状态和权益
  【月卡兑换】 查看月卡兑换商店
  【兑换真还魂丹 数量】 用月卡兑换真还魂丹
"""

# AI引导处理器 - 使用明确的命令前缀避免误触
ai_guide = on_command("问", aliases={"请问", "提问", "咨询"}, priority=5, block=True)

@ai_guide.handle()
async def handle_ai_guide(event: MessageEvent, args: Message = CommandArg()):
    """AI引导处理器 - 需要明确的命令前缀"""
    try:
        user_message = args.extract_plain_text().strip()

        # 如果没有提供问题，返回使用说明
        if not user_message:
            await ai_guide.finish(message_add_head(
                "💡 助手使用说明\n"
                "━━━━━━━━━━━━━\n"
                "使用方式：【问 你的问题】\n"
                "示例：\n"
                "• 【问 如何升级】\n"
                "• 【请问 怎么赚钱】\n"
                "• 【提问 装备怎么升阶】\n\n"
                "💡 也可以直接发送【帮助】查看完整指令列表",
                event
            ))
            return  # finish后立即返回，避免进入异常处理

        async with safe_session() as session:
            # 使用跨平台工具获取玩家数据
            from .platform_utils import get_unified_player
            player = await get_unified_player(session, event)

            if not player:
                await ai_guide.finish(message_add_head(
                    "⛔ 请先发送【注册】创建角色",
                    event
                ))
                return  # finish后立即返回

            # 检查是否为管理员的数据库查询请求
            if is_admin(event.get_user_id()):
                # 判断是否可能是数据库查询请求
                if is_database_query(user_message):
                    await handle_admin_database_query(user_message, event)
                    return

            # 先发送搜索提示
            await ai_guide.send(message_add_head("🤔 正在思考您的问题...", event))

            # 调用AI进行引导
            response = await get_ai_guidance(user_message, player)
            if response:
                response += "\n━━━━━━━━━━━━━\n💡 【】括号里的才是指令\n💡 发送【帮助】查看完整指令列表"
                await ai_guide.finish(message_add_head(response, event))
                return  # finish后立即返回

    except Exception as e:
        # 忽略 FinishedException（finish的正常退出机制）
        from nonebot.exception import FinishedException
        if isinstance(e, FinishedException):
            return

        logger.error(f"AI引导处理失败: {e}")
        await ai_guide.finish(message_add_head(
            "❌ AI助手处理失败，请发送【帮助】查看游戏指令",
            event
        ))
        return

def extract_relevant_commands(user_message: str, max_systems: int = 3) -> str:
    """
    根据用户问题提取相关的指令系统

    Args:
        user_message: 用户提问内容
        max_systems: 最多返回几个系统的指令（默认3个）

    Returns:
        相关指令的文本
    """
    # 定义关键词到系统的映射
    keyword_map = {
        "注册|昵称|UID|面板|等级|排行|财富|修为|幸运|战力": "玩家系统",
        "修炼|突破|闭关|出关|冥返|加点|洗点|献祭|怨念|棺材钉": "修炼系统",
        "背包|鱼栏|使用|丢弃|图鉴|耐药性|丹药|欺骗": "背包系统",
        "装备|锻造|升阶|镶嵌|孔位|拆卸|修理|卸下|稳定水晶": "装备系统",
        "市集|跑商|购买|出售|市价|缉邪司|总部|兑换": "跑商系统",
        "交易|挂牌|撤牌|查牌|税率|估价": "交易系统",
        "炼丹|丹方|收获|炼丹炉": "炼丹系统",
        "存|取|余额|转账|存款|银行": "银行系统",
        "投资|气运|行情|刷新": "投资系统",
        "结婚|求婚|离婚|配偶|拜师|收徒|师父|徒弟|送礼|恩爱": "社交系统",
        "探索|导航|地图|坐标|移动|传送|观察|NPC|交互": "探索系统",
        "诡域|副本|扫荡|俯瞰|宝箱|怪物": "副本系统",
        "战斗|攻击|切磋|BOSS|讨伐|死斗": "战斗系统",
        "公会|创建|加入|退会|捐献|建筑|任务|基地": "公会系统",
        "委托|接取|完成|刷新|缉邪司": "委托系统",
        "打工|收工|工作|赚钱": "打工系统",
        "钓鱼|鱼栏": "钓鱼系统",
        "阴宅|购买|升级|迁移|费用": "阴宅系统",
        "签到|抽签|摸鱼|月卡|小游戏": "娱乐系统",
        "留言|私信|留言板": "留言板系统",
    }

    # 统计每个系统的匹配分数
    system_scores = {}
    for keywords, system_name in keyword_map.items():
        score = 0
        for keyword in keywords.split("|"):
            if keyword in user_message:
                score += 1
        if score > 0:
            system_scores[system_name] = score

    # 如果没有匹配到任何系统，返回常用系统
    if not system_scores:
        default_systems = ["游戏常识", "玩家系统", "修炼系统"]
        return extract_systems_from_full_text(default_systems)

    # 按分数排序，取top N
    top_systems = sorted(system_scores.items(), key=lambda x: x[1], reverse=True)[:max_systems]
    system_names = [name for name, _ in top_systems]

    # 始终包含"游戏常识"
    if "游戏常识" not in system_names:
        system_names.insert(0, "游戏常识")

    return extract_systems_from_full_text(system_names)

def extract_systems_from_full_text(system_names: list) -> str:
    """从完整指令文本中提取指定系统"""
    lines = AI_COMMANDS_TEXT.split('\n')
    result = []
    current_system = None
    capturing = False

    for line in lines:
        # 检查是否是系统标题
        if line.strip().endswith('系统：') or line.strip().endswith('常识：'):
            current_system = line.strip().rstrip('：')
            if any(sys_name in current_system for sys_name in system_names):
                capturing = True
                result.append(line)
            else:
                capturing = False
        elif capturing:
            # 继续捕获当前系统的内容
            if line.strip() == '':
                # 遇到空行可能是系统结束，但继续添加
                result.append(line)
            else:
                result.append(line)

    return '\n'.join(result)

async def get_ai_guidance(user_message: str, player: Player) -> str:
    """获取AI引导回复"""
    try:
        # 智能提取相关指令（减少token使用，避免超限）
        relevant_commands = extract_relevant_commands(user_message, max_systems=3)

        # 构建系统提示
        system_prompt = f"""你是《诡修仙》QQ机器人文游的AI助手，专门为玩家提供游戏帮助。

【重要约束】
1. ⚠️ 严禁编造指令！只能使用上面"相关游戏指令"列表中明确存在的指令
2. ⚠️ 如果玩家的需求在指令列表中没有匹配的指令，直接说"该功能暂不支持，请发送【帮助】查看完整指令列表"
3. ⚠️ 不要添加任何列表中不存在的指令名称、参数或格式
4. ⚠️ 指令格式必须严格按照列表中的格式，包括括号【】、尖括号<>、方括号[]
5. ⚠️ 对于玩家描述的功能需求，先在列表中搜索，找不到就说不知道

玩家信息：
- 昵称：{player.nickname}[UID：{player.uid}]
- 等级：{player.level}级

【可用的游戏指令列表】
（只有以下指令是真实存在的，不要使用列表外的任何指令）
{relevant_commands}

回复规则：
1. 只回答游戏相关问题，对于游戏外话题直接回复"该话题未检索到结果"
2. 严格从上面的指令列表中推荐，不要编造
3. 如果玩家发送的指令格式错误，告诉他正确格式
4. 回复要简洁明了，控制在150字以内
5. 用简短语言解释指令作用

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

        result = await call_ai_with_fallback(messages)
        return result['choices'][0]['message']['content']

    except asyncio.TimeoutError as e:
        logger.error(f"AI API调用超时: {str(e)}")
        return "🤖 助手响应超时，请稍后重试或发送【帮助】查看游戏指令"
    except aiohttp.ClientError as e:
        logger.error(f"AI API网络请求失败: {str(e)}")
        return "🤖 网络连接失败，请稍后重试或发送【帮助】查看游戏指令"
    except KeyError as e:
        logger.error(f"AI API响应格式异常，缺少字段: {str(e)}, 响应内容: {result if 'result' in locals() else 'N/A'}")
        return "🤖 AI响应格式异常，请发送【帮助】查看游戏指令"
    except Exception as e:
        logger.error(f"AI引导系统未知错误: {type(e).__name__}: {str(e)}", exc_info=True)
        return "🤖 助手暂时无法回应，请发送【帮助】查看游戏指令"
