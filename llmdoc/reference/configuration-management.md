# Configuration & Feature Management

## 1. Core Summary

GuiXiuXian2 implements a sophisticated configuration management system with YAML-based configuration files, environment variable support, and a comprehensive feature flag system. The configuration system supports hot-reloading, validation, and multiple configuration sources, while the feature flag system enables gradual rollout of new features with A/B testing capabilities.

## 2. Source of Truth

### Configuration System
- **Primary Code:** `infrastructure/config_manager.py` - Core configuration management with multi-source support
- **Configuration File:** `config/config.yaml` - Main application configuration
- **Database Config:** `plugins/xiuxian_game/config/database.yaml` - Database-specific configuration
- **Feature Flags:** `application/services/feature_flags.py` - Feature flag management and strategies

### Feature Flag System
- **Primary Code:** `application/services/feature_flags.py` - Feature flag service with release strategies
- **API Interface:** `application/api/feature_flags_api.py` - REST API for feature flag management
- **Integration:** `infrastructure/dependency_injection.py` - DI container integration for feature flags

### Related Architecture
- **Dependency Injection:** `/llmdoc/architecture/dependency-injection.md` - Service container integration
- **Database Architecture:** `/llmdoc/architecture/database-architecture.md` - Database configuration patterns
- **Attribute System:** `application/services/attribute_adapter.py` - Configuration-driven attribute calculation

## 3. Configuration System

### Configuration Sources

The configuration system supports multiple sources with priority-based merging:

1. **Default Values** - Built-in fallback values
2. **Environment Variables** - Runtime environment configuration
3. **Configuration Files** - YAML/JSON configuration files
4. **Database** - Dynamic configuration storage
5. **Remote Sources** - External configuration services (framework provided)

### Configuration File Structure

```yaml
# config/config.yaml
database:
  type: sqlite
  url: "sqlite:///data/guixiuxian.db"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
  pool_recycle: 3600
  echo: false
  future: true

cache:
  ttl: 3600
  max_size: 1000
  cleanup_interval: 300

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/app.log"
  max_size: 10485760  # 10MB
  backup_count: 5

feature_flags:
  new_attribute_system: true
  session_management: true
  auto_cleanup: true
  feature_flags_enabled: true
  hot_reload_config: true

app:
  name: "GuiXiuXian Bot"
  version: "2.0.0"
  environment: "development"
  debug: true
```

### Environment Variable Mapping

```bash
# Database Configuration
export DB_TYPE=sqlite
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=username
export DB_PASSWORD=password

# Logging Configuration
export LOG_LEVEL=INFO

# Cache Configuration
export CACHE_ENABLED=true
export CACHE_TTL=3600
```

### Configuration API Usage

```python
from infrastructure.config_manager import get_config, get_config_manager

# Get configuration values
db_type = get_config("database.type")
cache_ttl = get_config("cache.ttl", default=300)
full_config = get_config()

# Set configuration values
get_config_manager().set_config("database.pool_size", 15)

# Add validation rules
from infrastructure.config_manager import ConfigValidationRule

rule = ConfigValidationRule(
    field="database.pool_size",
    field_type=int,
    min_value=1,
    max_value=100
)
get_config_manager().add_validation_rule(rule)

# Watch for configuration changes
async def on_config_change(new_config):
    print(f"Configuration updated: {new_config}")

get_config_manager().add_change_callback(on_config_change)
```

## 4. Feature Flag System

### Feature Flag States

- **ENABLED**: Feature is available to all qualifying users
- **DISABLED**: Feature is completely unavailable
- **EXPERIMENTAL**: Feature is in testing phase with limited availability
- **DEPRECATED**: Feature is scheduled for removal

### Release Strategies

```python
from application.services.feature_flags import ReleaseStrategy

# Percentage-based rollout
await feature_flag_service.set_release_strategy(
    "new_combat_system",
    ReleaseStrategy.PERCENTAGE,
    0.5  # 50% of users
)

# User-specific rollout
await feature_flag_service.set_release_strategy(
    "beta_feature",
    ReleaseStrategy.USER_ID,
    user_ids={"user123", "user456"}
)

# Random rollout
await feature_flag_service.set_release_strategy(
    "experimental_feature",
    ReleaseStrategy.RANDOM,
    0.1  # 10% random users
)
```

### Feature Flag Usage

```python
from application.services.feature_flags import get_feature_flag_service

# Check if feature is enabled
feature_service = get_feature_flag_service()

if await feature_service.is_enabled("new_attribute_system"):
    # Use new attribute system
    await process_with_new_system()
else:
    # Fallback to legacy system
    await process_with_legacy_system()

# User-specific feature check
if await feature_service.is_enabled("premium_feature", user_id="user123"):
    # Grant premium access
    await grant_premium_features()
```

### Feature Flag Decorator

```python
from application.services.feature_flags import feature_flag

@feature_flag("new_combat_system")
async def combat_v2(player_id: str, enemy_data: dict):
    # This function only executes if feature is enabled
    return await process_new_combat(player_id, enemy_data)

@feature_flag("beta_feature")
def sync_function(data: dict):
    # Synchronous function with feature flag
    return process_beta_data(data)
```

### Feature Tracking and Metrics

```python
# Start feature usage tracking
await feature_service.start_feature_tracking(
    "new_combat_system",
    user_id="player123",
    context={"mode": "pvp"}
)

# End tracking (usually when feature usage completes)
await feature_service.end_feature_tracking(
    "new_combat_system",
    user_id="player123"
)

# Get feature metrics
metrics = await feature_service.get_feature_metrics(
    "new_combat_system",
    days=7
)
print(f"Feature used by {metrics['unique_users']} users")

# Export configuration
await feature_service.export_feature_flags("feature_flags_backup.json")
```

### Configuration-Driven Feature Registration

```python
# Register features from configuration
config = get_config("feature_flags")
feature_service.register_features_from_config(config)

# Access feature information
feature_info = feature_service.get_feature_info("new_attribute_system")
print(f"Feature state: {feature_info['state']}")
print(f"Release strategy: {feature_info['release_strategy']}")
```

## 5. Configuration Validation

### Built-in Validation Rules

The system includes automatic validation for common configuration patterns:

```python
# Database configuration validation
get_config_manager().add_validation_rule(
    ConfigValidationRule(
        field="database.type",
        field_type=str,
        allowed_values=["sqlite", "mysql", "postgresql"]
    )
)

# Numeric range validation
get_config_manager().add_validation_rule(
    ConfigValidationRule(
        field="cache.ttl",
        field_type=int,
        min_value=60,
        max_value=86400
    )
)
```

### Custom Validation

```python
def validate_database_url(value):
    """Custom database URL validation"""
    if not value.startswith(('sqlite://', 'mysql://', 'postgresql://')):
        return False, "Invalid database URL format"
    return True, ""

get_config_manager().add_validation_rule(
    ConfigValidationRule(
        field="database.url",
        field_type=str,
        custom_validator=validate_database_url
    )
)
```

## 6. Configuration Migration

### Version-Based Migration

```python
class ConfigMigration:
    @staticmethod
    async def migrate_from_v1_to_v2():
        """Migrate configuration from version 1 to 2"""
        old_config = get_config_manager().get_config()

        # Transform configuration
        new_config = {
            "database": old_config.get("db", {}),
            "cache": old_config.get("cache", {}),
            "feature_flags": old_config.get("features", {})
        }

        # Apply new configuration
        get_config_manager().set_config("migrated_version", "2")
```

### Hot Reload Configuration

```python
# Enable configuration hot reloading
get_config_manager().add_change_callback(
    async def on_config_change(new_config):
        print("Configuration reloaded")
        # Restart services if needed
        await restart_services_if_necessary()
)

# Watch specific configuration file
await get_config_manager().watch_config_file(
    "config/config.yaml",
    on_config_change
)
```

## 7. Best Practices

### Configuration Management

1. **Environment Separation**: Use different configuration files for development, staging, and production
2. **Sensitive Data**: Store sensitive information in environment variables, not configuration files
3. **Validation**: Always validate configuration values on startup
4. **Documentation**: Document all configuration options and their purposes
5. **Versioning**: Maintain configuration versioning for complex migrations

### Feature Flag Management

1. **Naming Conventions**: Use clear, descriptive names for feature flags
2. **Cleanup**: Remove deprecated feature flags promptly
3. **Monitoring**: Monitor feature usage and performance metrics
4. **Rollback Strategy**: Plan feature rollbacks in case of issues
5. **Documentation**: Document feature flag purpose and expected behavior

### Security Considerations

1. **Access Control**: Restrict access to sensitive configuration endpoints
2. **Encryption**: Encrypt sensitive configuration values at rest
3. **Audit Logging**: Log configuration changes for compliance
4. **Least Privilege**: Configure services with minimal required permissions

## 8. Development Workflow

### Local Development

```bash
# Copy configuration template
cp config/config.yaml.example config/config.yaml

# Set development environment variables
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG

# Start application with hot reload
python -m app.main --hot-reload
```

### Production Deployment

```bash
# Production configuration
export ENVIRONMENT=production
export LOG_LEVEL=INFO
export DB_HOST=production-db

# Validate configuration before deployment
python -c "from infrastructure.config_manager import initialize_config; asyncio.run(initialize_config())"

# Start with configuration validation
python -m app.main --validate-config
```

### Monitoring and Maintenance

```python
# Check configuration health
async def check_configuration_health():
    config_manager = get_config_manager()
    errors = config_manager.validate_config()

    if errors:
        logger.error(f"Configuration validation errors: {errors}")
        return False

    # Check feature flag health
    feature_service = get_feature_flag_service()
    metrics = await feature_service.get_all_features()

    return True

# Regular configuration backup
async def backup_configuration():
    await get_config_manager().export_config(
        f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    )
```