"""新手序章与未知指令兜底的注册/词表回归。"""
import difflib


def test_prologue_commands_registered():
    from plugins.xiuxian_game.player import prologue

    assert prologue.open_eyes is not None
    assert prologue.fight_back is not None
    assert prologue.play_dead is not None


def test_prologue_button_data_hits_commands():
    """按钮 data 会原样作为消息发出，必须能从消息开头命中已注册指令。"""
    from nonebot.rule import TrieRule
    from plugins.xiuxian_game.player import info, prologue

    for rows in (info.REGISTER_BUTTONS, prologue.OPEN_EYES_BUTTONS, prologue.FINISH_BUTTONS):
        for row in rows:
            for spec in row:
                label, data = (spec, spec) if isinstance(spec, str) else spec
                assert TrieRule.prefix.longest_prefix(data).key, \
                    f"按钮data未命中任何指令: {data!r} (label={label!r})"


def test_fallback_vocab_contains_player_commands():
    from plugins.xiuxian_game.player import help as help_mod

    vocab = help_mod._get_command_vocab()
    for name in ("修炼", "突破", "签到", "睁开眼", "反抗", "装死", "装备", "穿戴", "观察"):
        assert name in vocab, f"词表缺少玩家指令: {name}"


def test_fallback_vocab_excludes_superuser_commands():
    from plugins.xiuxian_game.player import help as help_mod

    vocab = help_mod._get_command_vocab()
    assert "生成经验表" not in vocab
    assert "删除称号图片" not in vocab


def test_fallback_suggestion_for_common_typos():
    from plugins.xiuxian_game.player import help as help_mod

    vocab = help_mod._get_command_vocab()
    assert help_mod._COMMAND_SYNONYMS["修练"] == "修炼"
    # 同义词表未覆盖的近似词由 difflib 兜底
    assert "签到" in difflib.get_close_matches("鉴到", vocab, n=3, cutoff=0.5)
