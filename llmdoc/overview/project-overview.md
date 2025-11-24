# GuiXiuXian2 Project Overview

## 1. Identity

**What it is:** GuiXiuXian2 is a sophisticated QQ bot-based cultivation/xiuxian themed game built on the Nonebot2 framework.

**Purpose:** To provide an immersive cultivation RPG experience with interconnected game systems, modern architecture, and deep QQ platform integration.

## 2. High-Level Description

GuiXiuXian2 represents a mature cultivation-themed MMORPG game designed specifically for the QQ platform. The project showcases a sophisticated hybrid architecture combining traditional plugin-based design with modern Domain-Driven Design (DDD) principles and enterprise-grade patterns.

At its core, the project delivers eight major interconnected game systems including cultivation progression, turn-based combat, dynamic economy, guild management, social relationships, world exploration, quest/story content, and player progression mechanics. The game uses a realm-based cultivation system with 12 major realms from Qi Condensation to True Immortal, complemented by complex attribute calculations and battle mechanics.

The technical architecture demonstrates significant evolution from traditional monolithic design to a layered approach with dependency injection, service registration, and feature flag systems. This modernization enables better maintainability, testability, and scalability while preserving existing functionality through integration bridge patterns.

## 3. Technology Stack

### Core Framework
- **Nonebot2**: Primary bot framework providing QQ platform integration
- **OneBot V11**: QQ message adapter for seamless platform communication
- **FastAPI**: Modern web framework for API services and internal tools

### Data & Storage
- **SQLAlchemy**: ORM for database operations with async support
- **SQLite**: Primary database for development and production
- **MySQL**: Target database for future scaling and multi-instance deployment

### Architecture Patterns
- **Domain-Driven Design (DDD)**: Clean architecture with domain, application, and infrastructure layers
- **Dependency Injection Container**: Service lifecycle management with Singleton, Transient, and Scoped services
- **Repository Pattern**: Data access abstraction with Unit of Work
- **Feature Flag System**: Gradual rollout and A/B testing capabilities

### Technical Infrastructure
- **Async/Await**: Full async support throughout the codebase
- **YAML Configuration**: Environment-specific configuration management
- **Local Caching**: Memory-based caching with TTL management
- **Unified Session Management**: Centralized session handling for different contexts
- **Event-Driven Architecture**: Domain events for decoupled system communication

## 4. Architecture Overview

### Hybrid Architecture Approach

The project employs a sophisticated hybrid architecture that bridges traditional plugin design with modern enterprise patterns:

**Traditional Layer (Plugins)**
- Located in `/plugins/xiuxian_game/`
- Contains battle-tested game systems and business logic
- Maintains backward compatibility during migration

**Modern Layer (Clean Architecture)**
- **Domain Layer** (`/domain/`): Core business logic and entities
- **Application Layer** (`/application/`): Use cases and application services
- **Infrastructure Layer** (`/infrastructure/`): Technical implementations and integrations

### Key Architectural Patterns

1. **Integration Bridge Pattern**: Enables communication between legacy and modern systems
2. **Service Registry**: Centralized service discovery and dependency management
3. **Attribute Calculation System**: Unified calculation engine with pluggable sources
4. **Session Management**: Handles player, story, and temporary sessions with caching
5. **Configuration Management**: Multi-source configuration with validation and hot-reload support

### Current Refactoring Status

The project is in Phase 3 of a comprehensive modernization effort:

- ✅ **Phase 2 Completed**: Unified session management and attribute calculation systems (100% test pass rate)
- 🔄 **Phase 3 In Progress**: Service registration, configuration management, and feature flag systems (62.5% core functionality complete)
- 📋 **Future Phases**: Performance optimization, testing infrastructure, and documentation

## 5. Key Game Systems

### Cultivation System
- **Realm Progression**: 12 major realms from Qi Condensation to True Immortal
- **Cultivation Mechanics**: Energy absorption, breakthrough success rates, realm bonuses
- **Spiritual Roots**: Five elements (金木水火土) affecting cultivation potential
- **Techniques**: Cultivation methods with different paths and effects

### Battle System
- **Turn-Based Combat**: Strategic combat with 4 core attributes (Attack, Defense, Agility, HP)
- **Skill System**: Skills with cooldowns and special abilities
- **Effect Mechanics**: Critical hits, healing, buffs/debuffs, and status effects
- **Integration**: Cultivation realm directly impacts battle stats and damage calculations

### Economy System
- **Dual Currency**: Gold and Gold2 currencies for different economic activities
- **Equipment System**: 5-tier rarity system with upgrade mechanics and durability
- **Marketplace**: Comprehensive trading system for items and equipment
- **Income Sources**: Fishing rewards, guild donations, quest rewards, and daily activities

### Guild System
- **Hierarchical Structure**: President, Vice President, Core Member, Member roles
- **Guild Buildings**: Teleportation, warehouse, and alchemy facilities
- **Economy**: Guild donations, treasury management, and member benefits
- **Activities**: Guild-exclusive content and collaborative features

### Social System
- **Relationships**: Marriage system with in-game benefits
- **Communication**: Guild chat, private messaging, and social activities
- **Community**: Multi-server player interactions and events

### World Exploration
- **Dual Coordinate System**: X/Y positioning with regional boundaries
- **Procedural Generation**: Dynamic content based on location and player level
- **Discovery**: Hidden areas, resources, and events scattered throughout the world

### Story/Quest System
- **Node-Based Engine**: Conditional branching and dynamic content
- **Player Integration**: Stories adapt based on player attributes and progression
- **Content Storage**: JSON-based story files with variable substitution
- **Progress Tracking**: Session management and quest completion tracking

### Player Progression
- **Attribute System**: 8 core attributes (EXP, HP, MP, Attack, Defense, Agility, Stamina, Luck)
- **Stat Reallocation**: Players can redistribute earned attribute points
- **Level Advancement**: Experience-based leveling with milestone rewards
- **Integration**: All progression tied to cultivation, battle, and economic activities

## 6. Current State

### Active Refactoring Efforts

The project is undergoing significant architectural modernization following a design-pattern driven approach:

**Completed Achievements:**
- Dependency injection container with lifecycle management
- Unified session management system with caching
- Centralized attribute calculation engine
- Service registration and discovery system
- Configuration management with multi-source support
- Feature flag system with gradual rollout capabilities

**Ongoing Work:**
- Domain layer implementation refinement
- Application layer service development
- Infrastructure layer optimizations
- Integration bridge pattern enhancements

**Quality Assurance:**
- Phase 2 implementation: 100% test pass rate (4/4 modules)
- Phase 3 implementation: 62.5% core functionality (5/8 modules)
- Comprehensive error handling and graceful degradation
- Performance monitoring and health checks

### Integration Strategy

The refactoring employs a parallel operation strategy:
- Legacy systems remain fully operational
- New systems are implemented with integration bridges
- Feature flags enable controlled migration
- A/B testing validates consistency between old and new implementations

## 7. Platform Integration

### Deep QQ Platform Integration

GuiXiuXian2 is deeply integrated with the QQ platform ecosystem:

**OneBot V11 Adapter**
- Native QQ protocol support
- Rich message handling (text, images, files)
- Event-driven message processing
- Multi-instance deployment support

**Cross-Platform Compatibility**
- Web interface for administrative control
- Mobile-friendly interaction patterns
- API endpoints for external integration
- Consistent user experience across platforms

**Community Features**
- Multi-server player interaction
- Cross-guild communication
- Shared leaderboards and achievements
- Platform-specific events and promotions

### Technical Integration

**Database Architecture**
- SQLite for single-instance deployment
- MySQL for multi-instance scalability
- Connection pooling and async operations
- Data migration and backup capabilities

**Performance Optimization**
- Local caching with TTL management
- Query optimization and indexing
- Background task processing
- Resource monitoring and management

**Security & Compliance**
- User authentication and authorization
- Data validation and sanitization
- Privacy protection features
- Compliance with platform requirements

## 8. Future Development Directions

### Technical Roadmap
- **Phase 4**: Performance optimization with Redis and MySQL migration
- **Phase 5**: Testing infrastructure and documentation completion
- **Phase 6**: Advanced features (WebSocket, GraphQL, microservices)

### Game Feature Expansion
- Additional cultivation paths and techniques
- New battle systems and PvP mechanics
- Expanded world exploration content
- Enhanced social and community features

### Platform Evolution
- Enhanced mobile experience
- Web-based admin interface
- Third-party integrations
- Advanced analytics and reporting

---

*This overview represents the current state of GuiXiuXian2 as of Phase 3 implementation. The project continues to evolve with active development and architectural improvements.*