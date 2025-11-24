# How to Use Dependency Injection

## 1. Getting Started

This guide covers how to use the dependency injection system in GuiXiuXian2. The DI container provides service lifecycle management, dependency resolution, and health monitoring capabilities.

**Prerequisites:** Basic understanding of async/await patterns and Python classes.

## 2. Step 1: Understanding Service Lifetimes

The DI container supports three service lifetimes:

1. **TRANSIENT**: New instance created each time requested
2. **SINGLETON**: Single instance shared across the application
3. **SCOPED**: Instance unique to a service scope (e.g., request scope)

```python
from infrastructure.dependency_injection import ServiceLifetime

# Register a singleton database service
container.register_service(
    DatabaseService,
    lifetime=ServiceLifetime.SINGLETON
)

# Register a transient logging service
container.register_service(
    LoggingService,
    lifetime=ServiceLifetime.TRANSIENT
)

# Register a scoped session service
container.register_service(
    SessionService,
    lifetime=ServiceLifetime.SCOPED
)
```

## 3. Step 2: Registering Services

Basic service registration with automatic dependency injection:

```python
from infrastructure.dependency_injection import get_container

container = get_container()

# Register service with explicit implementation
container.register_service(
    ICacheService,  # Interface
    RedisCacheService,  # Implementation
    lifetime=ServiceLifetime.SINGLETON
)

# Register service with factory function
container.register_service(
    IDatabaseService,
    lifetime=ServiceLifetime.SINGLETON,
    factory=create_database_service
)

# Register existing instance
container.register_singleton(
    ConfigManager,
    existing_config_manager_instance
)
```

## 4. Step 3: Dependency Resolution

The container automatically resolves constructor dependencies:

```python
class PlayerService:
    def __init__(self, database_service: IDatabaseService,
                 cache_service: ICacheService, config: ConfigManager):
        self.db = database_service
        self.cache = cache_service
        self.config = config

# Dependencies are automatically injected
player_service = await container.get_service(PlayerService)
```

## 5. Step 4: Using Service Scopes

Create scopes for scoped services (e.g., request lifecycle):

```python
# Create a new scope
with container.create_scope() as scope:
    # Scoped services will be unique to this scope
    session_service = await scope.get_service(SessionService)
    player_service = await scope.get_service(PlayerService)

    # Services used within scope share the same instance
    session1 = await scope.get_service(UserSession)
    session2 = await scope.get_service(UserSession)
    assert session1 is session2  # Same instance within scope

# Scope is automatically disposed when context exits
```

## 6. Step 5: Service Initialization and Disposal

Add initialization and disposal callbacks:

```python
async def initialize_service(service_instance):
    """Service initialization logic"""
    await service_instance.setup()
    print("Service initialized")

def dispose_service(service_instance):
    """Service cleanup logic"""
    service_instance.cleanup()
    print("Service disposed")

container.register_service(
    AnalyticsService,
    lifetime=ServiceLifetime.SINGLETON,
    initialization_callback=initialize_service,
    disposal_callback=dispose_service
)
```

## 7. Step 6: Health Checks

Register health checks for service monitoring:

```python
from infrastructure.dependency_injection import IHealthCheck, HealthStatus

class DatabaseHealthCheck(IHealthCheck):
    async def check_health(self) -> HealthStatus:
        try:
            # Check database connectivity
            await self.db.ping()
            return HealthStatus("Database", True, "Connection healthy")
        except Exception as e:
            return HealthStatus("Database", False, f"Connection failed: {e}")

# Register health check
container.register_health_check("database", DatabaseHealthCheck())

# Check all services health
health_status = await container.check_all_health()
```

## 8. Step 7: Integration with Legacy Plugin System

The bridge pattern allows legacy code to use new DI services:

```python
from plugins.xiuxian_game.integration_bridge import get_new_services

def legacy_function():
    # Get new system services
    services = get_new_services()

    # Use feature flags
    feature_flag_service = services.get('feature_flag_service')
    if feature_flag_service and feature_flag_service.is_enabled('new_feature'):
        # Use new feature
        pass

    # Use cache service
    cache_service = services.get('cache_service')
    cached_data = cache_service.get("player:123")
```

## 9. Step 8: Using Service Injection Decorator

Inject services into functions automatically:

```python
from infrastructure.dependency_injection import inject_service

@inject_service()
async def process_player_action(player_id: str,
                               database_service: IDatabaseService,
                               cache_service: ICacheService):
    # Services are automatically injected
    player = await database_service.get_player(player_id)
    cached_stats = await cache_service.get(f"stats:{player_id}")

    # Process action
    return await process_action(player, cached_stats)
```

## 10. Step 9: Advanced Features

### Conditional Registration
```python
def conditionally_register_services():
    config = get_config()
    if config.database.type == "postgresql":
        container.register_service(PostgresService, lifetime=ServiceLifetime.SINGLETON)
    else:
        container.register_service(SqliteService, lifetime=ServiceLifetime.SINGLETON)
```

### Service Interception
```python
class LoggingInterceptor:
    def __init__(self, service):
        self.service = service

    async def method_name(self, *args, **kwargs):
        print(f"Calling method_name with args: {args}")
        result = await self.service.method_name(*args, **kwargs)
        print(f"method_name returned: {result}")
        return result

# Register intercepted service
container.register_service(
    OriginalService,
    lifetime=ServiceLifetime.SINGLETON,
    factory=lambda: LoggingInterceptor(OriginalService())
)
```

## 11. Step 10: Best Practices

1. **Use Interfaces**: Define interfaces for better testability and flexibility
2. **Choose Appropriate Lifetimes**: Singletons for stateless services, scoped for request-specific state
3. **Proper Disposal**: Always register disposal callbacks for resource cleanup
4. **Health Monitoring**: Implement health checks for critical services
5. **Graceful Degradation**: Handle service unavailability gracefully
6. **Circular Dependencies**: Avoid circular dependencies in service design

## 12. Step 11: Common Patterns

### Repository Pattern with DI
```python
class PlayerRepository:
    def __init__(self, database_service: IDatabaseService):
        self.db = database_service

    async def get_by_id(self, player_id: str):
        return await self.db.get_player(player_id)

container.register_service(IPlayerRepository, PlayerRepository)
```

### Service Composition
```python
class PlayerService:
    def __init__(self,
                 player_repo: IPlayerRepository,
                 cache_service: ICacheService,
                 feature_flags: FeatureFlagService):
        self.repo = player_repo
        self.cache = cache_service
        self.features = feature_flags
```

### Configuration-Driven Services
```python
class DatabaseConfig:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager.get("database")

container.register_service(DatabaseConfig)
```

## 13. Verification

To verify your dependency injection setup is working:

1. Check that all services are registered correctly:
```python
service_info = container.get_service_info()
print(f"Registered {service_info['total_services']} services")
```

2. Test service resolution:
```python
service = await container.get_service(YourService)
assert service is not None
```

3. Verify health checks:
```python
health_status = await container.check_all_health()
assert all(status.is_healthy for status in health_status.values())
```

4. Test scoped services:
```python
with container.create_scope() as scope:
    service1 = await scope.get_service(ScopedService)
    service2 = await scope.get_service(ScopedService)
    assert service1 is service2  # Should be same instance
```