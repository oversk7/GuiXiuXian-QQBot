"""宠物定制人设服务

允许玩家花费诡烛，通过自然语言描述定制宠物人设。
AI将模糊描述优化为完整的角色人设段落并覆盖默认人设。
"""
from nonebot import logger
from ..ai_guide import call_ai_with_fallback
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .config import PetConfigManager

CUSTOM_PERSONALITY_PRICE = 50  # 诡烛
_pet_config = PetConfigManager()

# 禁止词（防止滥用）
_FORBIDDEN_WORDS = ["管理", "系统", "官方", "GM", "色情", "政治", "违禁"]

# AI优化的元提示词模板
_META_PROMPT = """你是一名专业的AI角色设计师，专门为修仙世界的宠物伙伴设计人设。

宠物信息：
- 种族：{beast_name}（{beast_description}）
- 昵称：{pet_nickname}
- 化形形态：{gender_desc}

玩家的人设需求："{player_description}"

请根据玩家的描述，为这只宠物设计完整的角色人设。要求：
1. 保持与宠物种族特性的一致性（{beast_name}的本质特征不能丢失）
2. 明确体现：性格特质、说话方式和自称、口头禅或常用词汇、行为习惯
3. 符合修仙世界风格，可以有仙气、鬼气、野性等气质
4. 人设描述要自然连贯，像一段角色简介
5. 字数控制在120-200字之间

直接输出人设描述文本，不要加任何前缀、解释或标题。"""


async def generate_custom_personality(
    player_description: str,
    pet_nickname: str,
    beast_name: str,
    beast_description: str,
    transform_gender: str,
    transform_name: str,
) -> str:
    """
    调用AI将玩家的模糊描述优化为完整人设段落。

    Returns:
        AI生成的人设描述文本

    Raises:
        ValueError: 描述含禁止词或AI调用失败
    """
    # 基础内容过滤
    for word in _FORBIDDEN_WORDS:
        if word in player_description:
            raise ValueError(f"描述中包含禁止词：{word}")

    gender_desc = f"{transform_name}（{'男性' if transform_gender == 'male' else '女性'}形态）" if transform_name else "未化形"

    prompt = _META_PROMPT.format(
        beast_name=beast_name,
        beast_description=beast_description,
        pet_nickname=pet_nickname,
        gender_desc=gender_desc,
        player_description=player_description,
    )

    messages = [
        {"role": "system", "content": "你是一名专业的AI角色设计师。"},
        {"role": "user", "content": prompt},
    ]

    result = await call_ai_with_fallback(messages)
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("AI未返回有效结果")

    personality_text = choices[0].get("message", {}).get("content", "").strip()
    if len(personality_text) < 20:
        raise ValueError("AI生成的人设过短，请重新尝试")

    return personality_text


async def customize_pet_personality(
    uow: UnitOfWork,
    player_id: str,
    description: str,
) -> tuple[bool, str]:
    """
    为当前伙伴定制人设：检查诡烛 → 调用AI → 扣费 → 保存。

    Returns:
        (success, message)
    """
    if not description:
        return False, "请描述你想要的人设，例如：定制人设 体贴温柔、说话轻声细语的"

    if len(description) > 100:
        return False, "描述不能超过100字"

    # 获取玩家
    player = await uow.players.get_by_id(player_id)
    if not player:
        return False, "玩家不存在"

    # 检查诡烛
    if player.gui_zhu < CUSTOM_PERSONALITY_PRICE:
        return False, (
            f"诡烛不足！定制人设需要 {CUSTOM_PERSONALITY_PRICE} 诡烛\n"
            f"当前持有：{player.gui_zhu} 诡烛"
        )

    # 获取当前伙伴
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有激活的伙伴诡兽"

    if not pet.is_transformed:
        return False, "宠物尚未化形，无法定制人设\n化形后（需Lv.50 + 好感度100）才能使用此功能"

    # 获取宠物配置
    beast = _pet_config.get_beast(pet.beast_id)
    if not beast:
        return False, "宠物配置异常"

    transform_name = _pet_config.get_transform_name(pet.beast_id, pet.transform_gender)

    # 调用AI生成人设
    try:
        personality_text = await generate_custom_personality(
            player_description=description,
            pet_nickname=pet.nickname,
            beast_name=beast.name,
            beast_description=beast.description,
            transform_gender=pet.transform_gender or "",
            transform_name=transform_name,
        )
    except ValueError as e:
        return False, f"人设生成失败：{e}"
    except Exception as e:
        logger.error(f"定制人设AI调用失败: {e}", exc_info=True)
        return False, "AI服务暂时不可用，请稍后重试"

    # 扣除诡烛并更新玩家数据
    player.gui_zhu -= CUSTOM_PERSONALITY_PRICE
    await uow.players.update(player)

    # 保存人设
    pet.custom_personality = personality_text
    await uow.pets.update(pet)

    return True, (
        f"✨ 人设定制成功！消耗 {CUSTOM_PERSONALITY_PRICE} 诡烛\n"
        f"━━━━━━━━━━━━━\n"
        f"🔮 {pet.nickname} 的新人设：\n"
        f"{personality_text}\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 如需恢复默认人设，发送【重置人设】（免费）\n"
        f"🔮 剩余诡烛：{player.gui_zhu}"
    )


async def reset_pet_personality(
    uow: UnitOfWork,
    player_id: str,
) -> tuple[bool, str]:
    """
    免费重置宠物人设为默认。

    Returns:
        (success, message)
    """
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有激活的伙伴诡兽"

    if not pet.custom_personality:
        return False, f"{pet.nickname} 当前使用的就是默认人设，无需重置"

    pet.custom_personality = None
    await uow.pets.update(pet)

    return True, f"✅ {pet.nickname} 的人设已恢复默认"
