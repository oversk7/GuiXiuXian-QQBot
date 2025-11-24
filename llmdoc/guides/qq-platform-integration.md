# How to Integrate with QQ Platform

## 1. Platform Setup

**Step 1:** Configure bot adapter in `pyproject.toml`
```toml
[tool.nonebot]
adapters = [
    { name = "OneBot V11", module_name = "nonebot.adapters.qq" }
]
plugin_dirs = ["plugins"]
```

**Step 2:** Initialize bot framework in `bot.py`
```python
import nonebot
from nonebot.adapters.qq import Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")
```

**Step 3:** Add logging configuration (optional but recommended)
```python
from nonebot import logger
logger.add("logs/command_log.txt", level="INFO", rotation="12h", retention="3 days", encoding="utf-8")
```

## 2. Cross-Platform Account Binding

**Step 1:** Generate binding key in private chat
- Command: `生成绑定密钥`
- Reference: `plugins/xiuxian_game/platform_binding_commands.py:24-89`
- Generates unique binding key for linking accounts

**Step 2:** Use binding key in target platform
- Command: `绑定账号 {密钥} {UID}`
- Reference: `plugins/xiuxian_game/platform_binding_commands.py:95-174`
- Links primary account to guild/group account

**Step 3:** Verify binding status
- Command: `绑定状态`
- Reference: `plugins/xiuxian_game/platform_binding_commands.py:180-241`
- Shows current account binding information

## 3. Message Formatting Patterns

**Step 1:** Use platform-aware formatting utilities
```python
from ..platform_utils import format_platform_message

# Automatically adds platform prefix
content = format_platform_message("Your message here", event)
```

**Step 2:** Handle platform-specific features
```python
from ..platform_utils import is_guild_message, is_group_message, is_private_message

if is_guild_message(event):
    # Handle guild-specific logic
elif is_group_message(event):
    # Handle group-specific logic
elif is_private_message(event):
    # Handle private message logic
```

## 4. Command Implementation

**Step 1:** Create cross-platform command
```python
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..platform_utils import get_unified_player

my_cmd = on_command("mycommand", block=True, priority=5)

@my_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await my_cmd.finish("You need to create a character first")

        # Cross-platform logic here
        await my_cmd.finish(f"Hello {player.nickname}!")
```

**Step 2:** Handle platform-specific features
```python
@my_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)

        # Platform-specific features
        from ..platform_utils import get_player_platform_display
        platform_info = await get_player_platform_display(session, player)

        await my_cmd.finish(f"Hello {player.nickname}! {platform_info}")
```

## 5. Rate Limiting and Message Guard

**Step 1:** Configure rate limits for commands
```python
# In message_guard.py - modify _COMMAND_RATE_LIMITS
_RATE_LIMITS = {
    "explore": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "move": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    # Add your commands here
}
```

**Step 2:** Platform-specific rate limiting
```python
# Rate limits can be configured differently per platform
if is_guild_message(event):
    # Apply guild-specific rate limits
elif is_group_message(event):
    # Apply group-specific rate limits
```

## 6. Verify Integration

**Step 1:** Test bot startup
```bash
python bot.py
```

**Step 2:** Test basic commands in different platforms:
- Group chat: 注册, 角色
- Guild chat: After binding, same commands should work
- Private chat: 生成绑定密钥

**Step 3:** Check log files for errors:
```bash
logs/command_log.txt
```

**Final Step:** Verify cross-platform binding by:
1. Creating character in group
2. Generating binding key in private chat
3. Using binding key in guild
4. Testing character access from both platforms