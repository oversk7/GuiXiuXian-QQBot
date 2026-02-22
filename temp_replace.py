import sys

path = r"D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\battle\integration_helper.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_line = None
for i, line in enumerate(lines):
    if 'round_actions = []' in line and '紧凑模式' in line:
        start_line = i
        break

if start_line is None:
    print("ERROR: 找不到 round_actions = [] 行")
    sys.exit(1)

end_line = None
for i in range(start_line, len(lines)):
    if '将回合动作合并为一行' in lines[i]:
        for j in range(i, min(i+20, len(lines))):
            if 'player2_hp_bar}' in lines[j] and 'battle_log.append' in lines[j]:
                end_line = j
                break
        break

if end_line is None:
    print("ERROR: 找不到结束行")
    sys.exit(1)

print(f"找到替换范围: 行 {start_line+1} 到 {end_line+1} (共 {end_line - start_line + 1} 行)")

new_block = """            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

            # 处理回合开始效果（regen等）
            # 玩家1 regen
            _, player1_hp_restored = engine._process_turn_start(player1.id, player1)
            if player1_hp_restored > 0:
                player1_hp = min(player1.max_hp, player1_hp + player1_hp_restored)
                battle_log.append(f"💚 {player1.nickname}回复{player1_hp_restored}HP")

            # 玩家2 regen
            _, player2_hp_restored = engine._process_turn_start(player2.id, player2)
            if player2_hp_restored > 0:
                player2_hp = min(player2.max_hp, player2_hp + player2_hp_restored)
                battle_log.append(f"💚 {player2.nickname}回复{player2_hp_restored}HP")

            # 根据先后手判定执行攻击顺序
            if player1_first:
                # 玩家1先手
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)
                        # 斩杀判定
                        exec_thr = _get_exec_thr(player1.id)
                        if exec_thr > 0 and player2_hp > 0:
                            if player2_hp < int(player2.max_hp * exec_thr / 100):
                                player2_hp = 0
                                battle_log.append(f"⚰️ {player1.nickname}发动处决，{player2.nickname}被弑灭！")
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player2_hp > 0:
                            player2_hp = min(player2.max_hp, player2_hp + heal_def)
                            battle_log.append(f"💚 {player2.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost1 = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player1._cached_attack - _pre_boost1
                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player1.nickname} 攻击 {player2.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player2.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player2_hp <= 0:
                            kill_result = engine.trigger_on_kill(player1, player2)
                            if kill_result.get("hp_restored", 0) > 0:
                                player1_hp = min(player1.max_hp, player1_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player1.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player1.nickname}攻击被闪避")

                # 玩家2反击（如果存活）
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player1_hp > 0:
                            player1_hp = min(player1.max_hp, player1_hp + heal_def)
                            battle_log.append(f"💚 {player1.nickname}回复{heal_def}HP")

                        # 处决判定（玩家2对玩家1）
                        _thr = _get_exec_thr(player2.id)
                        if _thr > 0 and player1_hp > 0:
                            if player1_hp < int(player1.max_hp * _thr / 100):
                                player1_hp = 0
                                battle_log.append(f"⚰️ {player2.nickname}发动处决，{player1.nickname}被弑灭！")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost2 = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player2._cached_attack - _pre_boost2
                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player2.nickname} 攻击 {player1.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player1.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player1_hp <= 0:
                            kill_result = engine.trigger_on_kill(player2, player1)
                            if kill_result.get("hp_restored", 0) > 0:
                                player2_hp = min(player2.max_hp, player2_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player2.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player2.nickname}攻击被闪避")
            else:
                # 玩家2先手
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player1_hp > 0:
                            player1_hp = min(player1.max_hp, player1_hp + heal_def)
                            battle_log.append(f"💚 {player1.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost2b = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player2._cached_attack - _pre_boost2b

                        # 处决判定（玩家2对玩家1）
                        _thr = _get_exec_thr(player2.id)
                        if _thr > 0 and player1_hp > 0:
                            if player1_hp < int(player1.max_hp * _thr / 100):
                                player1_hp = 0
                                battle_log.append(f"⚰️ {player2.nickname}发动处决，{player1.nickname}被弑灭！")

                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player2.nickname} 攻击 {player1.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player1.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player1_hp <= 0:
                            kill_result = engine.trigger_on_kill(player2, player1)
                            if kill_result.get("hp_restored", 0) > 0:
                                player2_hp = min(player2.max_hp, player2_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player2.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player2.nickname}攻击被闪避")

                # 玩家1反击（如果存活）
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)

                        # 处决判定（玩家1对玩家2）
                        _thr2 = _get_exec_thr(player1.id)
                        if _thr2 > 0 and player2_hp > 0:
                            if player2_hp < int(player2.max_hp * _thr2 / 100):
                                player2_hp = 0
                                battle_log.append(f"⚰️ {player1.nickname}发动处决，{player2.nickname}被弑灭！")
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player2_hp > 0:
                            player2_hp = min(player2.max_hp, player2_hp + heal_def)
                            battle_log.append(f"💚 {player2.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost1b = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player1._cached_attack - _pre_boost1b

                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player1.nickname} 攻击 {player2.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player2.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player2_hp <= 0:
                            kill_result = engine.trigger_on_kill(player1, player2)
                            if kill_result.get("hp_restored", 0) > 0:
                                player1_hp = min(player1.max_hp, player1_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player1.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player1.nickname}攻击被闪避")

            # 每回合结束后显示双方血量（只显示百分比）
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=False)
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=False)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")
"""

new_lines = lines[:start_line] + [new_block + '\n'] + lines[end_line+1:]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"✅ 替换成功！")
print(f"   - 删除了 {end_line - start_line + 1} 行旧代码")
print(f"   - 插入了新的循环体代码")
print(f"   - 文件已保存到: {path}")
