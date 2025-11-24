# QQ Bot Integration & Platform

## 1. Identity

- **What it is:** A multi-platform QQ bot framework designed for the GuiXiuXian text-based role-playing game, supporting seamless integration across QQ group chats, guilds (channels), and private messaging.
- **Purpose:** Provides unified bot access, cross-platform account binding, and consistent gameplay experience across different QQ platforms.

## 2. High-Level Description

The GuiXiuXian bot platform represents a sophisticated multi-platform messaging integration built on the Nonebot2 framework with OneBot V11 adapter support. It enables players to access their game characters and progress across multiple QQ platforms while maintaining a unified user experience.

Key architectural highlights include:

**Cross-Platform Account System**: Players can bind their primary QQ group account to guild accounts using secure binding keys, enabling seamless character progression across platforms. This allows users to start playing in a group and continue their journey in channels without losing progress.

**Unified Message Processing**: The platform implements a three-tier message processing system including event-level deduplication, message-level deduplication, and intelligent rate limiting. This ensures consistent behavior across all platforms while preventing spam and abuse.

**Platform-Specific Features**: The bot automatically detects and adapts to different platform contexts, providing appropriate visual indicators (🏛️ for guilds, 💬 for private chats) and leveraging platform-specific capabilities where available.

**Modular Plugin Architecture**: Each game system is implemented as a self-contained module with clean interfaces, supporting independent development, testing, and maintenance while maintaining platform consistency.

The platform serves as the foundation for GuiXiuXian's social and gameplay features, enabling thousands of players to simultaneously interact with the game world across different QQ platforms while maintaining data consistency and performance reliability.