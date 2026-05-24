import importlib.util
import asyncio
import random
import sys
import types
from pathlib import Path


def _load_service_module():
    nonebot_mod = types.ModuleType("nonebot")
    nonebot_mod.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)

    aiohttp_mod = types.ModuleType("aiohttp")
    aiohttp_mod.ClientError = RuntimeError

    ai_guide_mod = types.ModuleType("plugins.xiuxian_game.ai_guide")

    async def _call_ai_with_fallback(_messages):
        if "只输出一个词：CONTINUE 或 NO_REPLY" in _messages[0]["content"]:
            return {"choices": [{"message": {"content": "CONTINUE"}}]}
        return {"choices": [{"message": {"content": "嗯，这个说法有点东西"}}]}

    ai_guide_mod.call_ai_with_fallback = _call_ai_with_fallback

    config_mod = types.ModuleType("plugins.xiuxian_game.config")
    config_mod.config = types.SimpleNamespace(game_config={})

    package_mod = types.ModuleType("plugins")
    xiuxian_mod = types.ModuleType("plugins.xiuxian_game")
    group_mod = types.ModuleType("plugins.xiuxian_game.group_persona")
    group_mod.__path__ = []

    stubs = {
        "aiohttp": aiohttp_mod,
        "nonebot": nonebot_mod,
        "plugins": package_mod,
        "plugins.xiuxian_game": xiuxian_mod,
        "plugins.xiuxian_game.ai_guide": ai_guide_mod,
        "plugins.xiuxian_game.config": config_mod,
        "plugins.xiuxian_game.group_persona": group_mod,
    }
    created_stubs = []
    replaced = {}
    for name, module in stubs.items():
        if name in sys.modules:
            replaced[name] = sys.modules[name]
        else:
            created_stubs.append(name)
        sys.modules[name] = module

    base_path = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game" / "group_persona"
    config_spec = importlib.util.spec_from_file_location(
        "plugins.xiuxian_game.group_persona.config",
        base_path / "config.py",
    )
    assert config_spec and config_spec.loader
    config_module = importlib.util.module_from_spec(config_spec)
    sys.modules["plugins.xiuxian_game.group_persona.config"] = config_module
    config_spec.loader.exec_module(config_module)

    service_spec = importlib.util.spec_from_file_location(
        "plugins.xiuxian_game.group_persona.service",
        base_path / "service.py",
    )
    assert service_spec and service_spec.loader
    service_module = importlib.util.module_from_spec(service_spec)
    sys.modules["plugins.xiuxian_game.group_persona.service"] = service_module
    service_spec.loader.exec_module(service_module)

    for name in created_stubs:
        sys.modules.pop(name, None)
    for name, module in replaced.items():
        sys.modules[name] = module
    sys.modules.pop("plugins.xiuxian_game.group_persona.config", None)
    sys.modules.pop("plugins.xiuxian_game.group_persona.service", None)
    return service_module


service = _load_service_module()


def _cfg(**overrides):
    data = {
        "enabled": True,
        "group_whitelist": frozenset({"g1"}),
        "persona_name": "阿诡",
        "aliases": ("阿诡",),
        "reply_probability": 0.0,
        "mention_reply_probability": 1.0,
        "min_interval_seconds": 90.0,
        "max_history_messages": 30,
        "max_response_length": 120,
        "ignore_commands": True,
        "timing_gate_enabled": True,
    }
    data.update(overrides)
    return service.GroupPersonaConfig(**data)


def _message(text, *, group_id="g1", to_me=False):
    return service.PersonaIncomingMessage(
        group_id=group_id,
        user_id="u1",
        username="群友A",
        text=text,
        to_me=to_me,
    )


def test_group_persona_requires_whitelisted_group():
    svc = service.GroupPersonaService()

    assert svc.is_enabled_for_group("g1", _cfg(enabled=False)) is False
    assert svc.is_enabled_for_group("g2", _cfg()) is False
    assert svc.is_enabled_for_group("g1", _cfg()) is True


def test_group_persona_ignores_commands_and_empty_text():
    svc = service.GroupPersonaService()
    cfg = _cfg()

    assert svc.should_ignore_text("", cfg) is True
    assert svc.should_ignore_text("帮助", cfg) is True
    assert svc.should_ignore_text("注册 男", cfg) is True
    assert svc.should_ignore_text("今天好像挺热闹", cfg) is False


def test_group_persona_mention_triggers_when_probability_allows():
    svc = service.GroupPersonaService()
    decision = svc.decide_trigger(
        _message("阿诡你怎么看"),
        _cfg(),
        now=1000.0,
        rng=random.Random(1),
    )

    assert decision.should_reply is True
    assert decision.reason == "mention"


def test_group_persona_ambient_waits_for_enough_messages():
    svc = service.GroupPersonaService()
    cfg = _cfg(reply_probability=0.25)
    msg = _message("今天群里挺热闹")
    svc.record_message(msg, cfg)
    first_decision = svc.decide_trigger(msg, cfg, now=1000.0, rng=random.Random(1))

    for _ in range(3):
        svc.record_message(msg, cfg)
    second_decision = svc.decide_trigger(msg, cfg, now=1000.0, rng=random.Random(1))

    assert first_decision.should_reply is False
    assert first_decision.reason == "wait_more_messages"
    assert second_decision.should_reply is True
    assert second_decision.reason == "ambient"


def test_group_persona_cooldown_blocks_reply():
    svc = service.GroupPersonaService()
    svc._last_reply_at["g1"] = 990.0

    decision = svc.decide_trigger(
        _message("阿诡你怎么看"),
        _cfg(),
        now=1000.0,
        rng=random.Random(1),
    )

    assert decision.should_reply is False
    assert decision.reason == "cooldown"


def test_sanitize_reply_removes_role_prefix_and_limits_length():
    result = service.sanitize_reply("阿诡：<think>secret</think>这事确实有点怪\n不过也合理", 8)

    assert result == "这事确实有点怪"


def test_sanitize_reply_allows_model_to_stay_silent():
    assert service.sanitize_reply("NO_REPLY", 120) == ""


def test_parse_timing_gate_decision_is_conservative():
    assert service.parse_timing_gate_decision("CONTINUE") == "CONTINUE"
    assert service.parse_timing_gate_decision("我觉得 NO_REPLY") == "NO_REPLY"
    assert service.parse_timing_gate_decision("随便解释一下") == "NO_REPLY"


def test_generate_reply_uses_timing_gate_for_ambient_messages():
    async def run_case():
        svc = service.GroupPersonaService()
        cfg = _cfg(timing_gate_enabled=True)
        svc.record_message(_message("今天群里挺热闹"), cfg)

        return await svc._generate_reply("g1", cfg, "ambient")

    assert asyncio.run(run_case()) == "嗯，这个说法有点东西"
