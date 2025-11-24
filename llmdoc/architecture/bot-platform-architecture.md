# Bot Platform Architecture

## 1. Identity

- **What it is:** A Nonebot2-based multi-platform QQ bot framework with OneBot V11 adapter support, designed for GuiXiuXian text-based role-playing game.
- **Purpose:** Provides unified bot platform integration across QQ group chats, guilds (channels), and private messaging with cross-platform account binding and message processing capabilities.

## 2. Core Components

- `bot.py` (nonebot initialization, adapter registration): Main entry point that initializes Nonebot2 framework and registers OneBot V11 adapter for QQ platform integration.
- `pyproject.toml` (plugin configuration, adapter specification): Configuration file defining project dependencies and Nonebot2 plugin setup including adapter specification and plugin directories.
- `plugins/xiuxian_game/__init__.py` (plugin lifecycle, startup hooks): Main plugin initialization with database setup, unified player system integration, and startup procedures.
- `plugins/xiuxian_game/platform_binding_commands.py` (cross-platform binding logic): Handles account binding between QQ groups and guilds, providing unified player access across platforms.
- `plugins/xiuxian_game/platform_utils.py` (platform detection, unified access): Utility functions for platform type detection, user identification, and unified player data access.
- `plugins/xiuxian_game/message_guard.py` (event deduplication, rate limiting): Three-tier protection system including event-level deduplication, message-level deduplication, and command rate limiting.

## 3. Execution Flow (LLM Retrieval Map)

- **1. Framework Initialization:** `bot.py:1-16` - Initializes Nonebot2 framework and registers QQ adapter.
- **2. Plugin Loading:** `bot.py:13` - Loads plugins from `pyproject.toml` configuration.
- **3. Database Setup:** `plugins/xiuxian_game/__init__.py:41-44` - Initializes database connection and schema.
- **4. Platform Detection:** `plugins/xiuxian_game/platform_utils.py:20-41` - Determines platform type (group/guild/friend) from event session ID.
- **5. Event Processing:** `plugins/xiuxian_game/message_guard.py:238-271` - Applies deduplication and rate limiting before command processing.
- **6. Unified Player Access:** `plugins/xiuxian_game/platform_utils.py:62-110` - Retrieves player data with cross-platform binding support.
- **7. Command Routing:** Individual command modules process platform-specific and unified commands.

## 4. Design Rationale

The platform architecture emphasizes cross-platform compatibility and unified user experience. Key design decisions include:

- **Cross-platform Account Binding:** Players can bind their QQ group account to guild accounts using secure binding keys, enabling seamless character progression across platforms.
- **Unified Event Processing:** Three-tier deduplication system handles both event-level and message-level duplicates to prevent spam and ensure consistent behavior.
- **Platform-Specific Formatting:** Messages are automatically formatted with platform-specific prefixes (🏛️ for guilds, 💬 for private chats) for better user experience.
- **Rate Limiting:** Command-specific rate limits prevent abuse while maintaining responsiveness for legitimate usage patterns.
- **Modular Plugin System:** Each game system is implemented as a separate module with clear interfaces, supporting independent development and maintenance.