# Command System Reference

## 1. Core Summary

The GuiXiuXian bot uses a comprehensive command system built on Nonebot2 framework with cross-platform support, rate limiting, and unified player access. Commands are registered using decorators and processed through a multi-layered message guard system for optimal performance and user experience.

## 2. Source of Truth

- **Primary Code:** `plugins/xiuxian_game/platform_binding_commands.py` - Cross-platform account binding commands
- **Configuration:** `plugins/xiuxian_game/message_guard.py` - Command rate limiting and deduplication
- **Platform Utils:** `plugins/xiuxian_game/platform_utils.py` - Platform detection and unified player access
- **Command Patterns:** `plugins/xiuxian_game/player/info.py:41-45` - Command registration examples
- **Related Architecture:** `/llmdoc/architecture/bot-platform-architecture.md` - Platform architecture overview

## 3. Command Registration Patterns

### Basic Command Registration
```python
from nonebot import on_command

# Command with aliases
my_cmd = on_command(
    "command_name",
    aliases=["alias1", "alias2"],
    block=True,
    priority=5
)

# Handle command
@my_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # Command logic here
    pass
```

### Priority System
- **Priority 1-9**: Critical system commands (admin, binding)
- **Priority 10-19**: Core game commands (combat, movement)
- **Priority 20-29**: Utility commands (info, help)
- **Priority 30-39**: Entertainment commands (games, social)

## 4. Command Handler Implementation

### Standard Command Pattern
```python
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent

cmd = on_command("example", block=True, priority=15)

@cmd.handle()
async def handle_example(event: MessageEvent, args: Message = CommandArg()):
    """Example command handler"""
    # Extract arguments
    arg_text = args.extract_plain_text().strip()

    # Get unified player data
    from ..platform_utils import get_unified_player
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await cmd.finish("请先创建角色")

        # Command logic
        result = f"Command executed by {player.nickname}"
        await cmd.finish(result)
```

### Cross-Platform Command Pattern
```python
from ..platform_utils import is_guild_message, is_group_message, get_unified_player

@cmd.handle()
async def handle_cross_platform(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)

        # Platform-specific behavior
        if is_guild_message(event):
            result = f"🏛️ 频道模式: {player.nickname}"
        elif is_group_message(event):
            result = f"👥 群聊模式: {player.nickname}"
        else:
            result = f"💬 私聊模式: {player.nickname}"

        await cmd.finish(result)
```

## 5. Permission Systems and Access Control

### Command-Based Permissions
```python
# Admin-only commands
admin_cmd = on_command("admin_cmd", block=True, priority=5)

@admin_cmd.handle()
async def handle_admin(event: MessageEvent):
    from ..models.player import Player
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.is_admin:
            await admin_cmd.finish("❌ 没有权限")

        # Admin logic
        await admin_cmd.finish("✅ 管理员命令执行成功")
```

### Platform-Based Permissions
```python
# Guild-only commands
guild_cmd = on_command("guild_cmd", block=True, priority=10)

@guild_cmd.handle()
async def handle_guild(event: MessageEvent):
    if not is_guild_message(event):
        await guild_cmd.finish("❌ 此命令只能在频道中使用")

    # Guild logic
    await guild_cmd.finish("✅ 频道命令执行成功")
```

### Binding Requirements
```python
@cmd.handle()
async def handle_binding_required(event: MessageEvent):
    if is_guild_message(event):
        # Check if guild user has binding
        from ..platform_utils import get_unified_player
        async with safe_session() as session:
            player = await get_unified_player(session, event)
            if not player:
                await cmd.finish("❌ 请先在群聊创建角色并绑定账号")

        # Command logic
        await cmd.finish("✅ 命令执行成功")
```

## 6. Cross-Platform Command Compatibility

### Unified Commands
Most commands work seamlessly across platforms:
- `角色` (profile) - Works across all platforms
- `绑定状态` (binding status) - Works across all platforms
- `移动` (movement) - Works across all platforms

### Platform-Specific Commands
- `生成绑定密钥` - Only in private messages
- `绑定账号` - Only in guilds/channels
- `解除绑定` - Only in private messages

### Command Argument Handling
```python
@cmd.handle()
async def handle_args(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        # No arguments provided
        await cmd.finish("⛔ 请提供参数")

    # Parse arguments
    parts = arg_text.split()
    if len(parts) < 2:
        await cmd.finish("⛔ 参数格式错误")

    # Process arguments
    target_player_id = parts[0]
    action = parts[1]
    # ... rest of logic
```

## 7. Best Practices

### 1. Always Use Unified Player Access
```python
# Good
player = await get_unified_player(session, event)

# Bad - only checks current platform
player = await session.get(Player, event.get_user_id())
```

### 2. Handle Platform Differences
```python
# Always check platform requirements
if is_private_message(event):
    # Private chat logic
elif is_guild_message(event):
    # Guild logic
elif is_group_message(event):
    # Group logic
```

### 3. Use Rate Limiting Wisely
```python
# Configure appropriate rate limits for different commands
_RATE_LIMITS = {
    "explore": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "move": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "help": RateLimitConfig(max_requests=10, time_window=60.0, cooldown=5.0),  # Less restrictive
}
```

### 4. Provide Clear Error Messages
```python
# Platform-specific errors
if not player:
    if is_guild_message(event):
        await cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
    else:
        await cmd.finish("⛔ 你还没有创建角色")
```

### 5. Use Appropriate Priorities
- High priority (1-9): System-critical commands
- Medium priority (10-19): Core gameplay commands
- Low priority (20-39): Utility and entertainment commands

## 8. Error Handling and Validation

### Input Validation
```python
@cmd.handle()
async def handle_validation(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()

    # Validate numeric input
    try:
        target_uid = int(arg_text)
    except ValueError:
        await cmd.finish("⛔ UID必须为数字")

    # Validate range
    if target_uid < 1 or target_uid > 999999:
        await cmd.finish("⛔ UID超出有效范围")
```

### Database Error Handling
```python
async with safe_session() as session:
    try:
        # Database operations
        await session.commit()
    except Exception as e:
        await session.rollback()
        await cmd.finish(f"❌ 数据库操作失败: {str(e)}")
```

### Platform Validation
```python
# Check platform compatibility
if is_guild_message(event) and not feature_supported_in_guild:
    await cmd.finish("❌ 此功能在频道中暂不支持")
```