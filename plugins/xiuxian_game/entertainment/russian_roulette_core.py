"""
恶魔轮盘赌游戏核心逻辑
"""
import json
import random
from typing import List, Dict, Tuple, Optional
from enum import Enum


class ItemType(Enum):
    """道具类型枚举"""
    KNIFE = "knife"              # 小刀 - 下次伤害翻倍
    HANDCUFFS = "handcuffs"      # 手铐 - 限制对手下回合
    CIGARETTE = "cigarette"      # 香烟 - 恢复1血量
    MAGNIFIER = "magnifier"      # 放大镜 - 查看当前弹药
    BEER = "beer"                # 饮料 - 退掉当前弹药
    ADRENALINE = "adrenaline"    # 肾上腺素 - 偷取对手道具
    EXPIRED_MEDICINE = "expired_medicine"  # 过期药物 - 40%恢复2血量，否则扣1血量
    INVERTER = "inverter"        # 逆转器 - 转换当前弹药类型
    PHONE = "phone"              # 电话 - 随机预知一发弹药


class RussianRouletteCore:
    """恶魔轮盘赌核心游戏逻辑"""
    
    # 道具配置
    ITEM_CONFIGS = {
        ItemType.KNIFE: {"name": "🔪小刀", "description": "下次射击伤害翻倍"},
        ItemType.HANDCUFFS: {"name": "⛓️手铐", "description": "限制对手下回合行动"},
        ItemType.CIGARETTE: {"name": "🚬香烟", "description": "恢复1点血量"},
        ItemType.MAGNIFIER: {"name": "🔍放大镜", "description": "查看当前弹药类型"},
        ItemType.BEER: {"name": "🍺饮料", "description": "退掉当前弹药"},
        ItemType.ADRENALINE: {"name": "💉肾上腺素", "description": "偷取对手一个道具"},
        ItemType.EXPIRED_MEDICINE: {"name": "💊过期药物", "description": "40%恢复2血量，否则扣1血量"},
        ItemType.INVERTER: {"name": "🔄逆转器", "description": "转换当前弹药类型"},
        ItemType.PHONE: {"name": "📞电话", "description": "随机预知一发弹药位置"}
    }
    
    @staticmethod
    def generate_bullets(live_count: int = None, blank_count: int = None) -> List[bool]:
        """生成随机弹药序列"""
        # 如果没有指定数量，则从预设配置中随机选择
        if live_count is None or blank_count is None:
            bullet_configs = [
                (2, 4),  # 2实弹 + 4空包弹
                (3, 3),  # 3实弹 + 3空包弹
                (4, 2),  # 4实弹 + 2空包弹
            ]
            live_count, blank_count = random.choice(bullet_configs)

        bullets = [True] * live_count + [False] * blank_count
        random.shuffle(bullets)
        return bullets
    
    @staticmethod
    def generate_items(count: int = 4) -> List[ItemType]:
        """生成随机道具"""
        available_items = list(ItemType)
        return random.choices(available_items, k=count)
    
    @staticmethod
    def use_knife(game_state: dict) -> Tuple[bool, str]:
        """使用小刀"""
        game_state["is_sawed_off"] = True
        return True, "🔪 小刀已使用！下次射击伤害翻倍"
    
    @staticmethod
    def use_handcuffs(game_state: dict, target_player_id: str) -> Tuple[bool, str]:
        """使用手铐"""
        game_state["handcuffed_player_id"] = target_player_id
        return True, f"⛓️ 手铐已使用！对手下回合将被限制行动"
    
    @staticmethod
    def use_cigarette(game_state: dict, player_id: str, max_hp: int = 3) -> Tuple[bool, str]:
        """使用香烟"""
        current_hp = game_state.get(f"{player_id}_hp", 0)
        if current_hp >= max_hp:
            return False, "🚬 血量已满，无法使用香烟"
        
        game_state[f"{player_id}_hp"] = min(max_hp, current_hp + 1)
        return True, f"🚬 香烟已使用！恢复1点血量"
    
    @staticmethod
    def use_magnifier(game_state: dict, player_id: str) -> Tuple[bool, str]:
        """使用放大镜"""
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]
        
        if current_index >= len(bullets):
            return False, "🔍 弹夹已空，无法使用放大镜"
        
        current_bullet = bullets[current_index]
        bullet_type = "实弹" if current_bullet else "空包弹"
        
        # 存储私密信息
        magnifier_info = {
            "player_id": player_id,
            "bullet_index": current_index,
            "bullet_type": bullet_type,
            "is_live": current_bullet
        }
        game_state["magnifier_info"] = json.dumps(magnifier_info)
        
        return True, f"🔍 放大镜已使用！请私聊机器人，发送【预知】查看结果"
    
    @staticmethod
    def use_beer(game_state: dict) -> Tuple[bool, str]:
        """使用饮料"""
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]
        
        if current_index >= len(bullets):
            return False, "🍺 弹夹已空，无法使用饮料"
        
        ejected_bullet = bullets[current_index]
        bullet_type = "实弹" if ejected_bullet else "空包弹"
        
        # 推进弹药索引
        game_state["current_bullet_index"] = current_index + 1
        
        return True, f"🍺 饮料已使用！退出了一发{bullet_type}"
    
    @staticmethod
    def use_adrenaline(game_state: dict, user_id: str, target_id: str, stolen_item: ItemType) -> Tuple[bool, str]:
        """使用肾上腺素"""
        user_items_key = f"{user_id}_items"
        target_items_key = f"{target_id}_items"
        
        user_items = json.loads(game_state.get(user_items_key, "[]"))
        target_items = json.loads(game_state.get(target_items_key, "[]"))
        
        # 检查目标是否有该道具
        stolen_item_str = stolen_item.value
        if stolen_item_str not in target_items:
            return False, f"💉 对手没有{RussianRouletteCore.ITEM_CONFIGS[stolen_item]['name']}"
        
        # 转移道具
        target_items.remove(stolen_item_str)
        user_items.append(stolen_item_str)
        
        game_state[user_items_key] = json.dumps(user_items)
        game_state[target_items_key] = json.dumps(target_items)
        
        item_name = RussianRouletteCore.ITEM_CONFIGS[stolen_item]['name']
        return True, f"💉 肾上腺素已使用！偷取了对手的{item_name}"
    
    @staticmethod
    def use_expired_medicine(game_state: dict, player_id: str, max_hp: int = 3) -> Tuple[bool, str]:
        """使用过期药物"""
        current_hp = game_state.get(f"{player_id}_hp", 0)
        
        # 40%概率成功
        if random.random() < 0.4:
            # 成功：恢复2血量
            new_hp = min(max_hp, current_hp + 2)
            game_state[f"{player_id}_hp"] = new_hp
            return True, f"💊 过期药物生效！恢复2点血量"
        else:
            # 失败：扣除1血量
            new_hp = max(0, current_hp - 1)
            game_state[f"{player_id}_hp"] = new_hp
            return True, f"💊 过期药物副作用！扣除1点血量"
    
    @staticmethod
    def use_inverter(game_state: dict) -> Tuple[bool, str]:
        """使用逆转器"""
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]

        if current_index >= len(bullets):
            return False, "🔄 弹夹已空，无法使用逆转器"

        # 转换当前弹药类型
        bullets[current_index] = not bullets[current_index]
        game_state["bullets"] = json.dumps(bullets)

        # 不透露转换后的结果，保持神秘感
        return True, f"🔄 逆转器已使用！当前弹药类型已转换"
    
    @staticmethod
    def use_phone(game_state: dict, player_id: str) -> Tuple[bool, str]:
        """使用电话"""
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]
        
        remaining_bullets = bullets[current_index:]
        if not remaining_bullets:
            return False, "📞 弹夹已空，无法使用电话"
        
        # 随机选择一发剩余弹药进行预知
        random_index = random.randint(0, len(remaining_bullets) - 1)
        actual_index = current_index + random_index
        bullet_type = "实弹" if bullets[actual_index] else "空包弹"
        
        # 存储私密信息
        phone_info = {
            "player_id": player_id,
            "bullet_position": random_index + 1,  # 显示相对位置
            "bullet_type": bullet_type,
            "is_live": bullets[actual_index]
        }
        game_state["phone_info"] = json.dumps(phone_info)
        
        return True, f"📞 电话已使用！请私聊机器人，发送【预知】查看结果"
    
    @staticmethod
    def shoot(game_state: dict, shooter_id: str, target_id: str) -> Tuple[bool, str, bool]:
        """
        执行射击
        返回: (是否命中, 消息, 是否游戏结束)
        """
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]

        if current_index >= len(bullets):
            return False, "弹夹已空，无法射击", False

        current_bullet = bullets[current_index]
        is_sawed_off = game_state.get("is_sawed_off", False)

        # 推进弹药
        game_state["current_bullet_index"] = current_index + 1

        if current_bullet:  # 实弹
            damage = 2 if is_sawed_off else 1
            current_hp = game_state.get(f"{target_id}_hp", 0)
            new_hp = max(0, current_hp - damage)
            game_state[f"{target_id}_hp"] = new_hp

            # 重置小刀状态
            game_state["is_sawed_off"] = False

            damage_msg = f"造成{damage}点伤害" if damage > 1 else "造成1点伤害"
            result_msg = f"💥 实弹命中！{damage_msg}"

            # 检查游戏是否结束
            game_over = new_hp <= 0

            return True, result_msg, game_over
        else:  # 空包弹
            # 重置小刀状态（即使是空包弹也会消耗小刀效果）
            game_state["is_sawed_off"] = False
            return False, "🔫 空包弹！没有造成伤害", False

    @staticmethod
    def check_and_reload(game_state: dict, player1_id: str, player2_id: str) -> Tuple[bool, str]:
        """
        检查是否需要重新装弹，如果需要则重新装弹并补满道具
        返回: (是否重新装弹, 消息)
        """
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]

        # 检查是否所有子弹都用完了
        if current_index >= len(bullets):
            # 检查是否有玩家死亡
            player1_hp = game_state.get(f"{player1_id}_hp", 0)
            player2_hp = game_state.get(f"{player2_id}_hp", 0)

            if player1_hp > 0 and player2_hp > 0:
                # 双方都还活着，重新装弹（随机选择弹药配置）
                new_bullets = RussianRouletteCore.generate_bullets()
                game_state["bullets"] = json.dumps(new_bullets)
                game_state["current_bullet_index"] = 0

                # 计算新弹药配置
                live_count = sum(1 for b in new_bullets if b)
                blank_count = sum(1 for b in new_bullets if not b)

                # 补满道具（每人4个）
                player1_items = RussianRouletteCore.generate_items(4)
                player2_items = RussianRouletteCore.generate_items(4)
                game_state[f"{player1_id}_items"] = json.dumps([item.value for item in player1_items])
                game_state[f"{player2_id}_items"] = json.dumps([item.value for item in player2_items])

                # 清除特殊状态
                game_state["is_sawed_off"] = False
                game_state["handcuffed_player_id"] = None
                game_state["magnifier_info"] = None
                game_state["phone_info"] = None

                return True, f"🔄 弹夹已空！重新装填弹药并补充道具\n💥 本轮配置：{live_count}发实弹 + {blank_count}发空包弹"

        return False, ""
    
    @staticmethod
    def get_game_display(game_state: dict, room_info: dict, player_names: dict = None) -> str:
        """获取游戏状态显示"""
        bullets = json.loads(game_state["bullets"])
        current_index = game_state["current_bullet_index"]

        # 计算剩余弹药总数（不显示具体的实弹和空包弹数量，防止逆转器漏洞）
        remaining = bullets[current_index:]
        total_remaining = len(remaining)

        # 计算已经打出的子弹统计
        fired_bullets = bullets[:current_index]
        fired_live_count = sum(1 for b in fired_bullets if b)
        fired_blank_count = sum(1 for b in fired_bullets if not b)

        # 获取玩家信息
        player1_id = room_info["player1_id"]
        player2_id = room_info["player2_id"]
        player1_hp = game_state.get(f"{player1_id}_hp", 3)
        player2_hp = game_state.get(f"{player2_id}_hp", 3)

        # 获取玩家名称
        if player_names:
            player1_name = player_names.get(player1_id, "玩家1")
            player2_name = player_names.get(player2_id, "玩家2")
        else:
            player1_name = "玩家1"
            player2_name = "玩家2"

        # 构建显示
        display = [
            "🎮 恶魔轮盘赌",
            "━━━━━━━━━━━━━",
            f"🔫 剩余弹药：{total_remaining}发",
        ]

        # 显示已打出子弹统计（如果有的话）
        if fired_live_count > 0 or fired_blank_count > 0:
            display.append(f"📊 已打出：{fired_live_count}发实弹 + {fired_blank_count}发空包弹")

        display.extend([
            f"❤️ 血量状态：",
            f"  {player1_name}: {'❤️' * player1_hp}{'🖤' * (3 - player1_hp)}",
            f"  {player2_name}: {'❤️' * player2_hp}{'🖤' * (3 - player2_hp)}",
        ])

        # 显示道具信息
        player1_items = json.loads(game_state.get(f"{player1_id}_items", "[]"))
        player2_items = json.loads(game_state.get(f"{player2_id}_items", "[]"))

        display.extend([
            "━━━━━━━━━━━━━",
            "🎒 道具状态：",
            f"  {player1_name}: {len(player1_items)}个道具",
            f"  {player2_name}: {len(player2_items)}个道具"
        ])

        # 特殊状态
        special_effects = []
        if game_state.get("is_sawed_off"):
            special_effects.append("🔪 小刀效果：下次射击伤害翻倍")

        handcuffed = game_state.get("handcuffed_player_id")
        if handcuffed:
            handcuffed_name = player_names.get(handcuffed, handcuffed) if player_names else handcuffed
            special_effects.append(f"⛓️ 手铐效果：{handcuffed_name} 下回合被限制")

        if special_effects:
            display.extend(["━━━━━━━━━━━━━"] + special_effects)

        return "\n".join(display)

    @staticmethod
    def get_recommended_commands(game_state: dict, current_player_id: str) -> str:
        """获取推荐指令"""
        # 获取当前玩家道具
        player_items = json.loads(game_state.get(f"{current_player_id}_items", "[]"))

        commands = []

        # 基础射击指令
        commands.extend([
            "【开枪 自己】",
            "【开枪 对手】"
        ])

        # 道具使用指令
        if player_items:
            # 统计道具
            from collections import Counter
            item_counts = Counter(player_items)

            # 推荐常用道具
            priority_items = ["magnifier", "cigarette", "knife", "beer", "phone"]
            for item_type in priority_items:
                if item_type in item_counts:
                    item_config = RussianRouletteCore.ITEM_CONFIGS.get(ItemType(item_type))
                    if item_config:
                        item_name = item_config["name"].replace("🔍", "").replace("🚬", "").replace("🔪", "").replace("🍺", "").replace("📞", "")
                        commands.append(f"【使用道具 {item_name.strip()}】")
                        break  # 只推荐一个道具，避免太多选择

        # 其他常用指令
        commands.extend([
            "【查看道具】",
            "【房间状态】"
        ])

        # 格式化输出
        result = ["━━━━━━━━━━━━━"]
        for cmd in commands[:4]:  # 最多显示4个推荐指令
            result.append(f"⬇️ {cmd}")

        return "\n".join(result)
