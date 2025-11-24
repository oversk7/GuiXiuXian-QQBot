# Database Architecture

## 1. Identity

**What it is:** A multi-database backend system using SQLAlchemy with async operations supporting SQLite and MySQL.

**Purpose:** Provides persistent data storage with type-safe database models, async operations, and flexible database switching capabilities.

## 2. Core Components

- `plugins/xiuxian_game/models/db.py` (`AsyncSessionLocal`, `engine`, `Base`, `get_session`, `safe_session`): Core database session management with async engine configuration.
- `plugins/xiuxian_game/models/player.py` (`Player`, `Gender`): Core player data model with complex coordinate system and attribute calculations.
- `plugins/xiuxian_game/models/` directory (`Guild`, `Inventory`, `Equipment`, etc.): Complete data model suite for all game entities.
- `plugins/xiuxian_game/config/database.yaml`: Database configuration with support for SQLite and MySQL.
- `infrastructure/integrations/database.py`: Integration layer between legacy and new database systems.

## 3. Execution Flow (LLM Retrieval Map)

### Database Initialization
- **1. Configuration Loading:** `plugins/xiuxian_game/models/db.py:26-48` loads database configuration from YAML.
- **2. Engine Creation:** `plugins/xiuxian_game/models/db.py:121-128` creates async engine with appropriate drivers (aiosqlite for SQLite, aiomysql for MySQL).
- **3. Schema Setup:** `plugins/xiuxian_game/models/db.py:167-172` creates all database tables using `Base.metadata.create_all`.

### Session Management Patterns
- **Standard Session:** `plugins/xiuxian_game/models/db.py:177-187` provides basic session management with automatic cleanup.
- **Safe Session:** `plugins/xiuxian_game/models/db.py:190-204` adds automatic commit and rollback safety.
- **Retry Session:** `plugins/xiuxian_game/models/db.py:207-241` handles database locking with retry logic.

### Data Model Usage
- **Player Operations:** `plugins/xiuxian_game/models/player.py:457-463` demonstrates query pattern using `get_player_by_uid`.
- **Attribute Calculation:** `plugins/xiuxian_game/models/player.py:212-270` shows complex attribute system integration.
- **Dual Coordinate System:** `plugins/xiuxian_game/models/player.py:82-183` implements coordinate management for overworld and dungeons.

### Migration Strategy
- **Bridge Pattern:** `plugins/xiuxian_game/integration_bridge.py:19-57` provides access to new system services from legacy code.
- **Attribute System Migration:** `application/services/attribute_adapter.py:413-460` supports migration between legacy and new attribute calculation systems.

## 4. Design Rationale

### Multi-Database Support
- **SQLite:** Default for development and small deployments with WAL mode enabled for better concurrency.
- **MySQL:** Production option with connection pooling and optimized settings for high traffic.

### Async Operations
- All database operations use async/await patterns to prevent blocking the main event loop.
- Connection pooling configured based on database type and deployment size.

### Session Management
- Multiple session managers provide different safety levels: basic, safe (auto-commit), and retry-based.
- Context managers ensure proper resource cleanup and error handling.

### Model Design
- SQLAlchemy ORM with mapped_column for type safety.
- Complex attribute system with caching and calculation breakdowns.
- Dual coordinate system supporting both overworld and dungeon locations.

### Integration Layer
- Bridge pattern allows legacy plugin system to access new architecture services.
- Seamless migration path for existing code while new features use modern patterns.

## 5. Database Configuration

### SQLite Configuration
```yaml
database:
  type: sqlite
  sqlite:
    path: data/game.db
    timeout: 30
    check_same_thread: false
```

### MySQL Configuration
```yaml
database:
  type: mysql
  mysql:
    host: localhost
    port: 3306
    user: username
    password: password
    database: game_db
    charset: utf8mb4
    pool_size: 20
    max_overflow: 10
```

## 6. Best Practices

- Use appropriate session manager for your use case (basic for reads, safe for writes, retry for high-contention scenarios).
- Implement proper error handling around database operations.
- Use the integration bridge when accessing new services from legacy code.
- Cache frequently accessed player attributes to reduce database load.
- Monitor database connection pool usage and adjust accordingly.