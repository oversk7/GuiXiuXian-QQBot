"""宠物AI对话服务 - 复用现有AIDialogueService"""
import random
import re
from datetime import date
from typing import Tuple
from nonebot import logger

from nonebot.exception import FinishedException, PausedException, RejectedException
from ..dialogue.ai_dialogue_service import AIDialogueService
from ..dialogue.npc_personality import PersonalityTemplate
from ..dialogue.npc_gift_service import GIFT_WHITELIST
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.pet_instance import PetInstance
from ..models.pet_dialogue_history import PetDialogueHistory
from .config import PetConfigManager

_GIFT_PATTERN = re.compile(r'[\[（(]赠[:：](.+?)[:：](\d+)[\]）)]')
_MOOD_PATTERN = re.compile(r'\[情绪:([+-]\d+)\]')


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

        # 根据是否有定制人设选择不同的PersonalityTemplate构建路径
        if pet.custom_personality:
            # 自定义人设：用玩家定制内容替换background+role，保留状态上下文
            personality = PersonalityTemplate(
                name=pet.nickname,
                role="",
                pronouns=[],
                speech_patterns=[],
                key_words=personality_data.key_words,
                background=pet.custom_personality + "\n\n" + self._build_state_context(pet, player),
                behavioral_rules=[],
            )
        else:
            # 默认人设：使用种族配置
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
                favorability=self._map_affection_to_favorability(pet.affection),
                context=context,
            )
        except (FinishedException, PausedException, RejectedException):
            raise
        except Exception as e:
            logger.error(f"宠物AI对话失败: {e}", exc_info=True)
            response = self._get_fallback_response(pet)
            tokens_used = 0

        # 解析情绪标记（在其他处理前先提取，避免影响赠礼解析）
        mood_tag_match = _MOOD_PATTERN.search(response)
        response = _MOOD_PATTERN.sub("", response).strip()
        if mood_tag_match:
            sentiment = int(mood_tag_match.group(1))
        else:
            sentiment = 0

        # 根据情绪标记计算本次好感/心情变化
        if sentiment > 0:
            affection_gain = 2
            mood_gain = 4
        elif sentiment == -1:
            affection_gain = 0
            mood_gain = -3
        elif sentiment <= -2:
            affection_gain = -1
            mood_gain = -6
        else:
            affection_gain = 1
            mood_gain = 2

        # 解析并处理宠物赠礼
        gift_notice = ""
        match = _GIFT_PATTERN.search(response)
        response = _GIFT_PATTERN.sub("", response).strip()
        if match:
            item_name = match.group(1).strip()
            qty = int(match.group(2))
            today = str(date.today())

            if item_name not in GIFT_WHITELIST:
                logger.warning(f"宠物 {pet.nickname} 尝试赠送非白名单物品: {item_name!r}，已忽略")
            elif pet.gift_last_date == today:
                logger.info(f"宠物 {pet.nickname} 今日已赠过礼，冷却中")
            else:
                item_id, max_qty = GIFT_WHITELIST[item_name]
                qty = max(1, min(qty, max_qty))
                if item_id == "_gold":
                    player.gold += qty
                    gift_ok = True
                else:
                    from ..models.inventory import ItemInstance
                    gift_ok = await ItemInstance.add_item(uow.session, player_id, item_id, qty)

                if gift_ok:
                    pet.gift_last_date = today
                    gift_notice = f"\n━━━━━━━━━━━━━\n🎁 【系统】{pet.nickname} 赠予了你 {item_name}×{qty}，已存入背包"
                    logger.info(f"宠物 {pet.nickname} 赠送 {item_name}×{qty} 给玩家 {player_id}")
                else:
                    logger.warning(f"宠物 {pet.nickname} 赠送 {item_name}×{qty} 失败（背包已满？）")

        # 应用好感/心情变化（情绪标记已在上方解析）
        pet.affection = max(0, min(1000, pet.affection + affection_gain))
        pet.mood = max(0, min(100, pet.mood + mood_gain))
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

        display_name = self.config.get_transform_name(pet.beast_id, pet.transform_gender) if pet.is_transformed else beast.name
        return True, f"{pet.nickname}({display_name})\n━━━━━━━━━━━━━\n{response}{gift_notice}"

    @staticmethod
    def _map_affection_to_favorability(affection: int) -> int:
        """将宠物好感度(0-1000)映射到NPC亲密度(0-100)，让AI对话语气匹配关系阶段"""
        if affection >= 800:
            return 95
        elif affection >= 500:
            return 80
        elif affection >= 300:
            return 65
        elif affection >= 150:
            return 50
        elif affection >= 50:
            return 30
        else:
            return 15

    @staticmethod
    def _get_affection_behavior_hint(affection: int) -> str:
        """根据好感度返回AI行为引导，让对话风格与关系深度匹配"""
        if affection >= 800:
            return "你和主人心意相通，彼此之间毫无隔阂，会撒娇、吃醋、主动关心，像家人一样自然。"
        elif affection >= 500:
            return "你和主人关系非常亲密，说话亲昵不见外，会开玩笑、偶尔撒娇，非常信赖对方。"
        elif affection >= 300:
            return "你和主人关系亲密，说话比较随意自然，愿意分享心事，会主动关心主人。"
        elif affection >= 150:
            return "你信赖主人，说话友好但还有些矜持，偶尔会害羞，愿意配合主人的要求。"
        elif affection >= 50:
            return "你和主人刚刚熟悉，说话礼貌客气，有些拘谨，偶尔会好奇地观察主人。"
        else:
            return "你刚被驯化不久，对主人还很陌生，话不多，警惕而谨慎，需要时间建立信任。"

    def _build_state_context(self, pet, player) -> str:
        """构建宠物当前状态上下文（好感、心情、饥饿、形态、饰品等）"""
        affection_name = self.config.get_affection_level_name(pet.affection)
        mood_desc = self._get_mood_desc(pet.mood)
        hunger_desc = "饥饿" if pet.hunger < 20 else ("微饿" if pet.hunger < 50 else "饱足")
        form = "人形" if pet.is_transformed else "兽形"
        affection_hint = self._get_affection_behavior_hint(pet.affection)

        gender_desc = ""
        if pet.is_transformed and pet.transform_gender:
            transform_name = self.config.get_transform_name(pet.beast_id, pet.transform_gender)
            gender_cn = "男性" if pet.transform_gender == "male" else "女性"
            gender_desc = f"你的化形是{gender_cn}形态——{transform_name}。你必须严格按照{gender_cn}的身份说话和自称，不要使用其他性别的自称或语气。"

        ctx = (
            f"{gender_desc}"
            f"你的主人叫{player.nickname}，是一位{player.level}级的修仙者。"
            f"你和主人的关系是【{affection_name}】（好感度{pet.affection}）。"
            f"{affection_hint}"
            f"你现在的心情{mood_desc}，{hunger_desc}状态。"
            f"你目前是{form}态。"
        )

        if pet.is_guarding:
            ctx += "你正在灵田守田值班。"

        if pet.accessories:
            acc_names = []
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    acc_names.append(acc.name)
            if acc_names:
                ctx += f"你身上穿戴着{'、'.join(acc_names)}。"

        ctx += (
            "\n【情绪表达规则】对话结束时，根据这轮互动的感受，在回复末尾附加情绪标记："
            "被关心/称赞/温柔对待时加 [情绪:+1]；"
            "被冷漠/嫌弃/轻微冒犯时加 [情绪:-1]；"
            "被辱骂/严重伤害时加 [情绪:-2]；"
            "普通寒暄不加任何标记。标记仅供系统识别，不要对主人解释。"
        )

        return ctx

    def _build_pet_background(self, pet, beast, personality_data, player) -> str:
        """构建宠物背景上下文（默认人设路径）"""
        return f"{personality_data.background}\n\n{self._build_state_context(pet, player)}"

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
