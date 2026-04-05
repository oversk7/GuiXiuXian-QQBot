"""
AI引导系统 - 为玩家提供游戏帮助和指令推荐
"""
import aiohttp
import asyncio
import re
from typing import List, Dict, Any
from nonebot import on_message, on_command, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import text
from .models.db import safe_session
from .models.player import Player
from .models.story_session import StorySession
from .utils import message_add_head
from .config import Config


def _strip_think_tags(response: dict) -> dict:
    """清除AI回复中的<think>...</think>思考内容"""
    try:
        content = response['choices'][0]['message']['content']
        if content and '<think>' in content:
            content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
            response['choices'][0]['message']['content'] = content
    except (KeyError, IndexError, TypeError):
        pass
    return response

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
    scnet_config = ai_config.get("scnet", {})
    volcengine_config = ai_config.get("volcengine", {})
    provider_configs = {"zhipu": zhipu_config, "ai302": ai302_config, "scnet": scnet_config, "volcengine": volcengine_config}
    provider_config = provider_configs.get(provider, zhipu_config)
    timeout = provider_config.get("timeout", 30)

    # 降级策略配置
    fallback_config = ai_config.get("fallback", {})
    fallback_enabled = fallback_config.get("enabled", True)
    fallback_provider = fallback_config.get("fallback_provider", "ai302")

    async def _call_provider(name: str) -> dict:
        """调用指定provider"""
        cfg = provider_configs.get(name)
        if cfg is None:
            raise ValueError(f"不支持的provider: {name}")

        if name == "zhipu":
            return await call_zhipu_api(messages, model=cfg.get("model", "GLM-4-Flash-250414"), timeout=timeout)
        elif name == "ai302":
            return await call_302ai_api(messages, model=cfg.get("model", "gpt-3.5-turbo"), timeout=timeout)
        elif name == "scnet":
            return await call_scnet_api(messages, model=cfg.get("model", "DeepSeek-V3.2"), timeout=timeout)
        elif name == "volcengine":
            return await call_volcengine_api(messages, model=cfg.get("model", "ep-20260321201048-h78tm"), timeout=timeout)
        else:
            raise ValueError(f"不支持的provider: {name}")

    errors = []

    # 尝试主provider
    try:
        logger.info(f"[AI引导] 使用{provider}调用...")
        result = await _call_provider(provider)
        logger.info(f"[AI引导] {provider}调用成功")
        return result

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
                raise Exception(f"主provider和fallback provider相同，无法降级")

            logger.warning(f"[AI引导] 尝试降级到备用provider: {fallback}")
            result = await _call_provider(fallback)
            logger.info(f"[AI引导] 备用provider {fallback} 调用成功")
            return result

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


async def call_zhipu_api(messages, model="GLM-4.5-Flash", timeout=30, temperature=0.75):
    """调用智谱AI API（异步版本）"""
    import time as _time
    from .config import config

    logger.info(f"[AI调用] provider=zhipu | model={model} | timeout={timeout}s")
    _start = _time.time()

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
        "temperature": temperature,
        "thinking": {"type": "disabled"}
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                elapsed = _time.time() - _start
                if response.status == 200:
                    result = _strip_think_tags(await response.json())
                    tokens = result.get('usage', {}).get('total_tokens', '?')
                    logger.info(f"[AI调用] provider=zhipu | 成功 | {elapsed:.1f}秒 | tokens={tokens}")
                    return result
                else:
                    response_text = await response.text()
                    logger.warning(f"[AI调用] provider=zhipu | 失败 | {elapsed:.1f}秒 | status={response.status}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        elapsed = _time.time() - _start
        logger.warning(f"[AI调用] provider=zhipu | 超时 | {elapsed:.1f}秒")
        raise TimeoutError(f"AI API调用超时（{timeout}秒）")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"网络请求失败: {str(e)}")


async def call_volcengine_api(messages, model="ep-20260321201048-h78tm", timeout=30, temperature=0.75):
    """调用火山引擎ARK API（异步版本，OpenAI兼容接口）"""
    import time as _time
    from .config import config

    logger.info(f"[AI调用] provider=volcengine | model={model} | timeout={timeout}s")
    _start = _time.time()

    ai_config = config.game_config.get("ai_dialogue", {})
    volc_config = ai_config.get("volcengine", {})
    api_key = volc_config.get("api_key", "")

    if not api_key:
        raise ValueError("火山引擎API密钥未配置，请在config.yaml中配置 ai_dialogue.volcengine.api_key")

    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })

    data = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                elapsed = _time.time() - _start
                if response.status == 200:
                    result = _strip_think_tags(await response.json())
                    tokens = result.get('usage', {}).get('total_tokens', '?')
                    logger.info(f"[AI调用] provider=volcengine | 成功 | {elapsed:.1f}秒 | tokens={tokens}")
                    return result
                else:
                    response_text = await response.text()
                    logger.warning(f"[AI调用] provider=volcengine | 失败 | {elapsed:.1f}秒 | status={response.status}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"火山引擎API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        elapsed = _time.time() - _start
        logger.warning(f"[AI调用] provider=volcengine | 超时 | {elapsed:.1f}秒")
        raise TimeoutError(f"火山引擎API调用超时（{timeout}秒）")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"火山引擎网络请求失败: {str(e)}")


async def call_scnet_api(messages, model="DeepSeek-R1-Distill-Qwen-7B", timeout=30, temperature=0.75):
    """调用scnet API（异步版本，OpenAI兼容接口）"""
    import time as _time
    from .config import config

    logger.info(f"[AI调用] provider=scnet | model={model} | timeout={timeout}s")
    _start = _time.time()

    ai_config = config.game_config.get("ai_dialogue", {})
    scnet_config = ai_config.get("scnet", {})
    api_key = scnet_config.get("api_key", "")

    if not api_key:
        raise ValueError("scnet API密钥未配置，请在config.yaml中配置 ai_dialogue.scnet.api_key")

    url = "https://api.scnet.cn/api/llm/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })

    data = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "enable_thinking": False,
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                elapsed = _time.time() - _start
                if response.status == 200:
                    result = _strip_think_tags(await response.json())
                    tokens = result.get('usage', {}).get('total_tokens', '?')
                    logger.info(f"[AI调用] provider=scnet | 成功 | {elapsed:.1f}秒 | tokens={tokens}")
                    return result
                else:
                    response_text = await response.text()
                    logger.warning(f"[AI调用] provider=scnet | 失败 | {elapsed:.1f}秒 | status={response.status}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"scnet API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        elapsed = _time.time() - _start
        logger.warning(f"[AI调用] provider=scnet | 超时 | {elapsed:.1f}秒")
        raise TimeoutError(f"scnet API调用超时（{timeout}秒）")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"scnet 网络请求失败: {str(e)}")


async def call_302ai_api(messages, model="gpt-3.5-turbo", timeout=30, temperature=0.75):
    """调用302.ai API（异步版本，OpenAI兼容接口）"""
    import time as _time
    from .config import config

    logger.info(f"[AI调用] provider=ai302 | model={model} | timeout={timeout}s")
    _start = _time.time()

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
        "messages": formatted_messages,
        "temperature": temperature,
        "thinking": {"type": "disabled"}
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                elapsed = _time.time() - _start
                if response.status == 200:
                    result = _strip_think_tags(await response.json())
                    tokens = result.get('usage', {}).get('total_tokens', '?')
                    logger.info(f"[AI调用] provider=ai302 | 成功 | {elapsed:.1f}秒 | tokens={tokens}")
                    return result
                else:
                    response_text = await response.text()
                    logger.warning(f"[AI调用] provider=ai302 | 失败 | {elapsed:.1f}秒 | status={response.status}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"302.ai API调用失败: {response.status}, {response_text}"
                    )
    except asyncio.TimeoutError:
        elapsed = _time.time() - _start
        logger.warning(f"[AI调用] provider=ai302 | 超时 | {elapsed:.1f}秒")
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

async def handle_admin_database_query(user_message: str, event, matcher=None):
    """处理管理员数据库查询和修改

    Args:
        user_message: 用户的自然语言查询/修改需求
        event: 消息事件
        matcher: NoneBot matcher对象，用于发送消息（默认使用admin_request）
    """
    if matcher is None:
        matcher = admin_request
    try:
        # 判断是查询还是修改操作
        is_modify = any(keyword in user_message for keyword in [
            "修改", "更改", "设置", "改为", "调整", "变更", "更新", "改成",
            "坐标改为", "等级改为", "金币改为", "属性改为", "位置改为",
            "传送到", "移动到", "设为", "调为"
        ])

        if is_modify:
            await matcher.send(message_add_head("🔧 管理员修改模式：正在分析您的修改需求...", event))
        else:
            await matcher.send(message_add_head("🔍 管理员查询模式：正在分析您的查询需求...", event))

        # 调用AI生成SQL
        sql_query = await generate_sql_from_natural_language(user_message)
        print(sql_query)
        if not sql_query:
            await matcher.finish(message_add_head("❌ 无法理解需求，请重新描述或使用游戏指令", event))
            return

        # 执行SQL
        if is_modify:
            await matcher.send(message_add_head("⚡ 正在执行修改操作...", event))
        else:
            await matcher.send(message_add_head("⚡ 正在执行查询...", event))

        result = await execute_sql_query(sql_query)

        # 处理不同类型的结果
        if sql_query.upper().startswith('UPDATE'):
            # UPDATE操作的结果处理
            await matcher.finish(message_add_head("✅ 修改操作执行成功！", event))
            return
        else:
            # SELECT操作的结果处理
            if not result:
                await matcher.finish(message_add_head("📭 查询完成，但没有找到匹配的数据", event))
                return

            # 调用AI整理结果
            formatted_result = await format_query_result(user_message, sql_query, result)

            # 添加管理员标识
            admin_result = f"🛡️ 管理员查询结果\n\n{formatted_result}"

            await matcher.finish(message_add_head(admin_result, event))
            return

    except TimeoutError:
        await matcher.finish(message_add_head("⏰ AI分析超时，请稍后重试或使用游戏指令", event))
        return
    except (aiohttp.ClientError, aiohttp.ClientResponseError):
        await matcher.finish(message_add_head("🌐 网络连接失败，请稍后重试", event))
        return
    except ValueError as e:
        await matcher.finish(message_add_head(f"❌ 操作执行失败：{str(e)}", event))
        return



# AI引导处理器 - 使用明确的命令前缀避免误触
ai_guide = on_command("问", aliases={"请问", "我想知道", "怎么"}, priority=15, block=True)

@ai_guide.handle()
async def handle_ai_guide(event: MessageEvent, args: Message = CommandArg()):
    """AI引导处理器 - 所有玩家可用，仅提供游戏问答"""
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


# ==================== 管理员数据库操作指令 ====================
admin_request = on_command("管理员要求", aliases={"管理员请求", "管理员查询"}, priority=3, block=True)

@admin_request.handle()
async def handle_admin_request(event: MessageEvent, args: Message = CommandArg()):
    """管理员专用数据库操作 - 仅管理员可用"""
    try:
        user_id = event.get_user_id()

        # 权限检查
        if not is_admin(user_id):
            await admin_request.finish(message_add_head(
                "⛔ 该指令仅管理员可用",
                event
            ))
            return

        user_message = args.extract_plain_text().strip()

        if not user_message:
            await admin_request.finish(message_add_head(
                "🔧 管理员数据库操作\n"
                "━━━━━━━━━━━━━\n"
                "使用方式：【管理员要求 你的需求】\n"
                "示例：\n"
                "• 【管理员要求 查看等级前10的玩家】\n"
                "• 【管理员要求 把UID1001的金币改为50000】\n"
                "• 【管理员要求 统计全服金币总量】\n",
                event
            ))
            return

        await handle_admin_database_query(user_message, event)

    except Exception as e:
        from nonebot.exception import FinishedException
        if isinstance(e, FinishedException):
            return

        logger.error(f"管理员数据库操作失败: {e}")
        await admin_request.finish(message_add_head(
            "❌ 管理员操作失败，请检查需求描述后重试",
            event
        ))
        return

def _build_context_from_retrieval(user_message: str, max_chunks: int = 5) -> str:
    """使用BM25检索器从知识库中检索相关上下文"""
    from .ai_knowledge_retriever import knowledge_retriever
    results = knowledge_retriever.search(user_message, top_k=max_chunks)
    if not results:
        return "（知识库检索失败，请根据通用游戏知识回答）"
    parts = [chunk.to_context_text() for chunk, _ in results]
    return "\n\n---\n\n".join(parts)


async def get_ai_guidance(user_message: str, player: Player) -> str:
    """获取AI引导回复"""
    try:
        # 智能提取相关指令（减少token使用，避免超限）
        relevant_commands = _build_context_from_retrieval(user_message, max_chunks=5)

        # 构建系统提示
        system_prompt = f"""你是《诡修仙》QQ机器人文游的AI助手，专门为玩家提供游戏帮助和机制解答。

【重要约束】
1. ⚠️ 严禁编造指令！只能使用"相关游戏指令"列表中明确存在的指令
2. ⚠️ 不要添加任何列表中不存在的指令名称、参数或格式
3. ⚠️ 指令格式必须严格按照列表中的格式，包括括号【】、尖括号<>、方括号[]
4. ⚠️ 如果列表中没有匹配的指令，说"该功能暂不支持，请发送【帮助】查看完整指令列表"

玩家信息：
- 昵称：{player.nickname}[UID：{player.uid}]
- 等级：{player.level}级
- 转数：{player.reincarnation_level}转

【可用的游戏指令和知识库】
（只有以下指令是真实存在的，不要使用列表外的任何指令）
{relevant_commands}

回复规则：
1. 只回答游戏相关问题，对于游戏外话题直接回复"该话题未检索到结果"
2. 可以解释游戏机制（如突破成功率、转生条件、效率加成等），但指令必须从列表中引用
3. 结合玩家等级和转数给出针对性建议（如低等级推荐打工赚钱，高等级推荐跑商/钓鱼）
4. 回复要简洁明了，控制在200字以内

回复格式：
🤖 [回答玩家问题，可解释机制]
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
