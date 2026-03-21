"""宠物AI对话服务 - 复用现有AIDialogueService"""
import random
from typing import Tuple
from nonebot import logger

from nonebot.exception import FinishedException, PausedException, RejectedException
from ..dialogue.ai_dialogue_service import AIDialogueService
from ..dialogue.npc_personality import PersonalityTemplate
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.pet_instance import PetInstance
from ..models.pet_dialogue_history import PetDialogueHistory
from .config import PetConfigManager


class PetDialogueService:
    """宠物AI对话服务"""

    def __init__(self):
        self.config = PetConfigManager()
        self.ai_service = AIDialogueService()

    async def chat(
        self, uow: UnitOfWork, player_id: str, message: str
    ) -> Tuple[bool, str]:
        """与当前伙伴对话"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

        beast = self.config.get_beast(pet.beast_id)

        # 未化形：使用固定语录回复，不调用AI
        if not pet.is_transformed:
            return await self._beast_form_reply(uow, pet, beast)

        player = await uow.players.get_by_id(player_id)

        # 获取人设
        personality_data = self.config.get_personality(pet.beast_id, pet.is_transformed, pet.transform_gender or "")
        if not personality_data:
            return False, "宠物人设配置异常"

        # 转换为 PersonalityTemplate（复用现有AI对话系统）
        personality = PersonalityTemplate(
            name=pet.nickname,
            role=personality_data.role,
            pronouns=personality_data.pronouns,
            speech_patterns=personality_data.speech_patterns,
            key_words=personality_data.key_words,
            background=self._build_pet_background(pet, beast, personality_data, player),
            behavioral_rules=personality_data.behavioral_rules,
        )

        # 获取最近对话历史（宠物需要更多记忆来维持感情连贯性）
        history_limit = self.config.settings.get("dialogue_history_rounds", 20)
        history_records = await uow.pet_dialogue_histories.get_recent(
            pet_id=pet.id, player_id=player_id, limit=history_limit
        )

        # 适配对话历史格式（AIDialogueService通过duck typing读取player_input/npc_response）
        class _HistoryAdapter:
            def __init__(self, record):
                self.player_input = record.player_input
                self.npc_response = record.pet_response

        adapted_history = [_HistoryAdapter(r) for r in reversed(history_records)]

        # 构建上下文
        context = {
            "player_name": player.nickname,
            "player_level": player.level,
            "location_name": "身边",
        }

        # 用duck typing模拟NPC对象
        class _PetAsNPC:
            def __init__(self, pet_inst, beast_cfg):
                self.id = f"pet_{pet_inst.id}"
                self.name = pet_inst.nickname
                self.description = beast_cfg.description
                self.extra_data = {}

        fake_npc = _PetAsNPC(pet, beast)

        try:
            response, tokens_used = await self.ai_service.generate_dialogue(
                npc=fake_npc,
                personality=personality,
                question=message,
                dialogue_history=adapted_history,
                favorability=pet.affection,
                context=context,
            )
        except (FinishedException, PausedException, RejectedException):
            raise
        except Exception as e:
            logger.error(f"宠物AI对话失败: {e}", exc_info=True)
            response = self._get_fallback_response(pet)
            tokens_used = 0

        # 互动增加好感和心情
        affection_gain = 1
        mood_gain = 2
        pet.affection = min(1000, pet.affection + affection_gain)
        pet.mood = min(100, pet.mood + mood_gain)
        await uow.pets.update(pet)

        # 保存对话历史
        history = PetDialogueHistory(
            pet_id=pet.id,
            player_id=player_id,
            player_input=message,
            pet_response=response,
            affection_change=affection_gain,
            mood_change=mood_gain,
            ai_tokens_used=tokens_used,
        )
        await uow.pet_dialogue_histories.add(history)

        display_name = beast.transform_name if pet.is_transformed else beast.name
        return True, f"{pet.nickname}({display_name})\n━━━━━━━━━━━━━\n{response}"

    def _build_pet_background(self, pet, beast, personality_data, player) -> str:
        """构建宠物背景上下文"""
        affection_name = self.config.get_affection_level_name(pet.affection)
        mood_desc = self._get_mood_desc(pet.mood)
        hunger_desc = "饥饿" if pet.hunger < 20 else ("微饿" if pet.hunger < 50 else "饱足")
        form = "人形" if pet.is_transformed else "兽形"

        bg = (
            f"{personality_data.background}\n\n"
            f"你的主人叫{player.nickname}，是一位{player.level}级的修仙者。"
            f"你和主人的关系是【{affection_name}】。"
            f"你现在的心情{mood_desc}，{hunger_desc}状态。"
            f"你目前是{form}态。"
        )

        if pet.is_guarding:
            bg += "你正在灵田守田值班。"

        if pet.accessories:
            acc_names = []
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    acc_names.append(acc.name)
            if acc_names:
                bg += f"你身上穿戴着{'、'.join(acc_names)}。"

        return bg

    def _get_mood_desc(self, mood: int) -> str:
        if mood >= 80:
            return "非常好"
        elif mood >= 60:
            return "还不错"
        elif mood >= 40:
            return "一般"
        elif mood >= 20:
            return "有点低落"
        else:
            return "很糟糕"

    async def _beast_form_reply(self, uow: UnitOfWork, pet: PetInstance, beast) -> Tuple[bool, str]:
        """未化形时使用固定动物叫声语录回复"""
        personality_data = self.config.get_personality(pet.beast_id, False, "")
        key_words = personality_data.key_words if personality_data else ["..."]

        # 根据心情选择不同的动作描述
        if pet.mood >= 60:
            actions = [
                "蹭了蹭你的手",
                "朝你摇了摇尾巴",
                "发出了愉快的声音",
                "亲昵地靠近了你",
            ]
        elif pet.mood >= 30:
            actions = [
                "看了你一眼",
                "懒洋洋地抬了抬头",
                "动了动耳朵",
            ]
        else:
            actions = [
                "无精打采地趴着",
                "转过头不想理你",
                "发出了低沉的声音",
            ]

        sound = random.choice(key_words)
        action = random.choice(actions)
        response = f"{sound}\n（{pet.nickname}{action}）"

        # 仍然给好感和心情
        affection_gain = 1
        mood_gain = 2
        pet.affection = min(1000, pet.affection + affection_gain)
        pet.mood = min(100, pet.mood + mood_gain)
        await uow.pets.update(pet)

        display_name = beast.name
        hint = f"\n💡 它似乎还无法用言语交流...化形后或许能听懂你的话（需要{self.config.settings['transform_level']}级 + {self.config.settings['transform_affection']}好感度）"
        return True, f"{pet.nickname}({display_name})\n━━━━━━━━━━━━━\n{response}{hint}"

    def _get_fallback_response(self, pet: PetInstance) -> str:
        """AI降级时的预设回复"""
        personality = self.config.get_personality(pet.beast_id, pet.is_transformed, pet.transform_gender or "")
        if personality and personality.key_words:
            return personality.key_words[0]
        if pet.is_transformed:
            return f"...（{pet.nickname}歪了歪头，似乎没听清你说什么）"
        return "..."
