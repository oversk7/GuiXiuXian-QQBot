# GuiXiuXian2 Technical Documentation

## Project Overview

### Essential Reading for New Developers

**Start Here:**
- [project-overview.md](./overview/project-overview.md) - Complete project identity and technical architecture
- [qq-bot-platform-overview.md](./overview/qq-bot-platform-overview.md) - QQ platform integration foundation
- [clean-architecture-overview.md](./architecture/clean-architecture-overview.md) - Modern architecture transformation

### Quick Start

**Key Technical Components:**
1. **Architecture Foundation**: Clean Architecture with DDD principles, dependency injection, and service registration
2. **QQ Platform Integration**: Multi-platform bot with OneBot V11, cross-platform account binding, and unified player access
3. **Game Systems**: Cultivation RPG with 8 interconnected systems (battle, economy, guilds, social, exploration, story, progression)
4. **Database Layer**: Async SQLAlchemy with SQLite/MySQL support, complex player models, and migration bridges

**Development Patterns:**
```python
# Database usage with async sessions
async with get_session() as session:
    player = await session.get(Player, player_id)
    # Perform database operations

# Dependency injection
service = await container.get_service(MyService)

# Cross-platform player access
player = await get_unified_player(session, event)
```

## Documentation Structure

### 📖 Overview
Project identity, technical foundations, and high-level architecture

- [project-overview.md](./overview/project-overview.md) - Complete project identity and technical architecture
- [qq-bot-platform-overview.md](./overview/qq-bot-platform-overview.md) - QQ platform integration foundation

### 🏗️ Architecture
System design, patterns, and structural implementation

- [clean-architecture-overview.md](./architecture/clean-architecture-overview.md) - Modern architecture transformation
- [bot-platform-architecture.md](./architecture/bot-platform-architecture.md) - Bot platform technical design
- [database-architecture.md](./architecture/database-architecture.md) - Database layer architecture
- [game-systems-overview.md](./architecture/game-systems-overview.md) - Comprehensive game systems architecture

### 🛠️ Implementation Guides
Step-by-step development and integration instructions

- [refactoring-implementation-guide.md](./guides/refactoring-implementation-guide.md) - Complete refactoring methodology
- [dependency-injection-guide.md](./guides/dependency-injection-guide.md) - Service container usage and lifecycle
- [core-game-systems.md](./guides/core-game-systems.md) - Core game systems deep dive
- [supporting-game-systems.md](./guides/supporting-game-systems.md) - Supporting game systems implementation
- [qq-platform-integration.md](./guides/qq-platform-integration.md) - QQ platform integration guide

### 📚 Reference
Technical specifications, code patterns, and factual information

- [command-system.md](./reference/command-system.md) - Bot command system patterns
- [configuration-management.md](./reference/configuration-management.md) - Configuration and feature flags
- [service-architecture.md](./reference/service-architecture.md) - Service architecture patterns

### 🔧 Development Resources
Coding standards and workflow practices

- [coding-conventions.md](../reference/coding-conventions.md) - Python coding standards
- [git-conventions.md](../reference/git-conventions.md) - Git workflow and conventions

## Key Architecture Concepts

### Clean Architecture Transformation
The project has evolved from monolithic plugins to layered Clean Architecture:
- **Domain Layer**: Core business logic, entities, and value objects
- **Application Layer**: Use cases and application services
- **Infrastructure Layer**: Technical implementations and integrations
- **Integration Layer**: Bridge between legacy and modern systems

### Hybrid Architecture Strategy
- **Legacy System**: Original plugin functionality remains operational
- **Modern System**: Clean Architecture components implemented alongside
- **Feature Flags**: Selective system switching via configuration
- **Integration Bridge**: Seamless communication between old and new systems

### QQ Platform Integration
- **Multi-Platform Support**: QQ groups, guilds (channels), and private messaging
- **Cross-Platform Binding**: Secure account linking across platforms
- **Unified Player System**: Single character progression across all platforms
- **Message Processing**: Three-tier deduplication and rate limiting

### Core Game Systems
1. **Cultivation System**: 12 realms, energy absorption, breakthrough mechanics
2. **Battle System**: Turn-based combat with 4 core attributes and skills
3. **Economy System**: Dual currency, equipment, marketplace, income sources
4. **Guild System**: Hierarchical structure, buildings, economy, activities
5. **Social System**: Marriage, communication, community features
6. **World Exploration**: Coordinate system, procedural generation, discovery
7. **Story System**: Node-based engine, player integration, content storage
8. **Progression System**: Attributes, leveling, stat reallocation

## Development Workflow

### Getting Started
1. **Read Overview**: Start with project-overview.md for context
2. **Understand Architecture**: Review clean-architecture-overview.md
3. **Setup Environment**: Follow qq-platform-integration.md for bot setup
4. **Learn Patterns**: Study refactoring-implementation-guide.md

### Architecture Patterns
- **Dependency Injection**: Service container with lifecycle management
- **Repository Pattern**: Data access abstraction with Unit of Work
- **Strategy Pattern**: Pluggable attribute calculation sources
- **Observer Pattern**: Domain events for decoupled communication
- **Command Pattern**: Decoupled NPC action execution

### Migration Strategy
The project uses a gradual migration approach:
- **Phase 1 Completed**: Foundation (DI, service registry, config)
- **Phase 2 Completed**: System integration (sessions, attributes, database)
- **Phase 3 In Progress**: Domain layer (effects, events, business logic)
- **Future Phases**: Performance optimization, testing, documentation

## Technical Implementation

### Database Architecture
- **Async SQLAlchemy**: Full async support throughout the codebase
- **SQLite/MySQL**: Flexible database support with migration paths
- **Complex Models**: Player data with coordinate systems and relationships
- **Session Management**: Unified session handling with caching

### Service Architecture
- **Service Container**: Lifecycle management with Singleton/Transient/Scoped
- **Health Monitoring**: Service discovery and health checks
- **Configuration Management**: Multi-source configuration with validation
- **Feature Flags**: Gradual rollout and A/B testing capabilities

### Integration Patterns
- **Facade Pattern**: Unified interface for legacy-new system communication
- **Adapter Pattern**: Multiple system type support
- **A/B Testing**: Continuous validation of system consistency
- **Performance Monitoring**: Metrics and optimization tracking

## Current Status

### Active Refactoring
- **Phase 2**: 100% test pass rate (4/4 modules)
- **Phase 3**: 62.5% core functionality (5/8 modules)
- **Quality Assurance**: Comprehensive error handling and monitoring

### Technology Stack
- **Framework**: Nonebot2 with OneBot V11 adapter
- **Database**: SQLAlchemy with async support
- **Architecture**: Clean Architecture with DDD principles
- **Platform**: Multi-platform QQ bot integration
- **Development**: Python with async/await patterns

---

*This documentation represents the comprehensive technical foundation of GuiXiuXian2, a sophisticated cultivation-themed MMORPG with modern architecture and deep QQ platform integration.*