# Service Architecture Reference

## 1. Core Summary

This document provides a comprehensive reference for the service architecture implementation in GuiXiuXian2's Clean Architecture refactoring. The architecture leverages dependency injection, service lifecycle management, and integration patterns to create a loosely coupled, highly maintainable system while preserving backward compatibility through an innovative bridge pattern.

## 2. Source of Truth

**Primary Code:**
- `infrastructure/dependency_injection.py` - Core DI container implementation
- `infrastructure/core_services.py` - Service registration and initialization
- `infrastructure/service_registry.py` - Service discovery and management
- `application/services/attribute_adapter.py` - Legacy-new system adapter
- `plugins/xiuxian_game/integration_bridge.py` - Integration bridge interface

**Configuration:**
- `config/config.yaml` - Service configuration and feature flags
- `infrastructure/config_manager.py` - Multi-source configuration management

**Related Architecture:**
- `/llmdoc/architecture/clean-architecture-overview.md` - High-level architecture overview
- `/llmdoc/guides/refactoring-implementation-guide.md` - Implementation patterns and strategies

## 3. Dependency Injection Container Implementation

### 3.1 ServiceContainer Architecture

The ServiceContainer provides comprehensive dependency injection with lifecycle management, health checks, and scoping capabilities.

**Core Components:**

```python
class ServiceLifetime(Enum):
    TRANSIENT = "transient"  # New instance per request
    SINGLETON = "singleton"  # Single instance globally
    SCOPED = "scoped"        # Instance per scope (e.g., request)

@dataclass
class ServiceDescriptor:
    service_type: Type
    implementation: Type
    lifetime: ServiceLifetime
    factory: Optional[Callable] = None
    dependencies: List[str] = field(default_factory=list)
    health_check: Optional[IHealthCheck] = None
    state: ServiceState = ServiceState.CREATED
```

**Service Lifecycle Management:**

```python
class ServiceContainer:
    def __init__(self):
        self._services: Dict[str, ServiceDescriptor] = {}
        self._singletons: Dict[str, Any] = {}
        self._scopes: Dict[str, ServiceScope] = {}
        self._health_registry = HealthCheckRegistry()
        self._lock = asyncio.Lock()

    async def get_service(self, service_type: Type) -> Any:
        """Get service instance with lifecycle management"""
        if not self._is_initialized:
            await self.initialize()

        return await self._get_service_instance(service_type)

    async def register_service(self, service_type: Type,
                             implementation: Type = None,
                             lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
                             factory: Callable = None):
        """Register service with DI container"""
        descriptor = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation,
            lifetime=lifetime,
            factory=factory
        )
        self._services[self._get_service_key(service_type)] = descriptor
```

**Health Check Integration:**

```python
class HealthCheckRegistry:
    def __init__(self):
        self._health_checks: Dict[str, IHealthCheck] = {}
        self._health_statuses: Dict[str, HealthStatus] = {}

    def register(self, service_name: str, health_check: IHealthCheck):
        """Register health check for service"""
        self._health_checks[service_name] = health_check

    async def check_all_health(self) -> Dict[str, HealthStatus]:
        """Check health of all registered services"""
        results = {}
        for service_name, health_check in self._health_checks.items():
            try:
                status = await health_check.check_health()
                results[service_name] = status
                self._health_statuses[service_name] = status
            except Exception as e:
                error_status = HealthStatus(
                    service_name=service_name,
                    is_healthy=False,
                    message=f"Health check failed: {str(e)}"
                )
                results[service_name] = error_status
        return results
```

### 3.2 Service Scoping

The container supports scoping for managing service lifetimes within specific contexts:

```python
class ServiceScope:
    def __init__(self, container: ServiceContainer):
        self.container = container
        self._services: Dict[str, Any] = {}
        self._created_services: Set[str] = set()
        self._is_disposed = False

    async def get_service(self, service_type: Type) -> Any:
        """Get service within scope context"""
        if self._is_disposed:
            raise RuntimeError("Service scope has been disposed")

        key = self._get_service_key(service_type)
        if key in self._services:
            return self._services[key]

        # Create and cache service within scope
        service = await self.container._get_service_instance(service_type, scope=self)
        self._services[key] = service
        self._created_services.add(key)
        return service

    async def dispose(self):
        """Dispose scope and cleanup services"""
        if self._is_disposed:
            return

        self._is_disposed = True
        for key in self._created_services:
            if key in self._services:
                await self.container._dispose_service(self._services[key])
        self._services.clear()
        self._created_services.clear()
```

**Usage Pattern:**

```python
# Create request scope
request_scope = container.create_scope()

# Use services within scope
async def handle_request():
    async with request_scope:
        session_manager = await request_scope.get_service(SessionManager)
        cache_service = await request_scope.get_service(CacheService)

        # Perform operations
        session = await session_manager.get_session("user123")
        await cache_service.set("session:data", session)

        # Resources automatically disposed when scope exits
```

### 3.3 Dependency Resolution

The container uses advanced dependency resolution with type hint support:

```python
async def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
    """Create service instance with dependency injection"""
    descriptor.state = ServiceState.INITIALIZING

    try:
        if descriptor.factory:
            instance = descriptor.factory()
        else:
            # Resolve constructor dependencies using type hints
            init_params = {}
            signature = inspect.signature(descriptor.implementation.__init__)

            for param_name, param in signature.parameters.items():
                if param_name == 'self':
                    continue

                # Inject dependencies based on type annotations
                if param.annotation != inspect.Parameter.empty:
                    dep_type = param.annotation
                    dep_key = self._get_service_key(dep_type)
                    if dep_key in self._services:
                        init_params[param_name] = await self._get_service_instance(dep_type)
                    elif dep_type == ServiceContainer:
                        init_params[param_name] = self

                # Use default values if no dependency found
                elif param.default != inspect.Parameter.empty:
                    init_params[param_name] = param.default

            instance = descriptor.implementation(**init_params)

        descriptor.instance = instance
        return instance

    except Exception as e:
        descriptor.state = ServiceState.ERROR
        logger.error(f"Failed to create instance for {descriptor.service_type.__name__}: {e}")
        raise
```

## 4. Service Lifecycle Management

### 4.1 Service States and Transitions

Services progress through defined states with proper lifecycle management:

```python
class ServiceState(Enum):
    CREATED = "created"          # Service registered but not initialized
    INITIALIZING = "initializing" # Being initialized
    INITIALIZED = "initialized"   # Ready to use
    DISPOSING = "disposing"      # Being disposed
    DISPOSED = "disposed"        # Fully disposed
    ERROR = "error"             # Failed to initialize or run

class ServiceDescriptor:
    # ... other fields ...
    state: ServiceState = ServiceState.CREATED
    initialization_callback: Optional[Callable] = None
    disposal_callback: Optional[Callable] = None

    async def _initialize_service(self, descriptor: ServiceDescriptor, instance: Any):
        """Initialize service with callbacks"""
        try:
            if descriptor.initialization_callback:
                if asyncio.iscoroutinefunction(descriptor.initialization_callback):
                    await descriptor.initialization_callback(instance)
                else:
                    descriptor.initialization_callback(instance)

            descriptor.state = ServiceState.INITIALIZED
            logger.debug(f"Service {descriptor.service_type.__name__} initialized")

        except Exception as e:
            descriptor.state = ServiceState.ERROR
            logger.error(f"Failed to initialize service {descriptor.service_type.__name__}: {e}")
            raise

    async def _dispose_service(self, instance: Any):
        """Dispose service with proper cleanup"""
        descriptor = self._find_descriptor(instance)

        if not descriptor:
            return

        try:
            descriptor.state = ServiceState.DISPOSING

            if descriptor.disposal_callback:
                if asyncio.iscoroutinefunction(descriptor.disposal_callback):
                    await descriptor.disposal_callback(instance)
                else:
                    descriptor.disposal_callback(instance)

            descriptor.state = ServiceState.DISPOSED
            logger.debug(f"Service {descriptor.service_type.__name__} disposed")

        except Exception as e:
            logger.error(f"Failed to dispose service {descriptor.service_type.__name__}: {e}")
```

### 4.2 Initialization and Shutdown

**System Initialization:**

```python
async def initialize_system():
    """Complete system initialization sequence"""
    logger.info("Starting system initialization...")

    try:
        # 1. Initialize configuration manager
        logger.info("Initializing configuration manager...")
        config_manager = get_config_manager()
        await config_manager.initialize()

        # 2. Register core services
        logger.info("Registering core services...")
        registry = await register_core_services()
        container = registry.container

        # 3. Store global references
        global _global_container, _global_registry
        _global_container = container
        _global_registry = registry

        # 4. Initialize service container
        logger.info("Initializing service container...")
        await container.initialize()

        # 5. Perform health checks
        logger.info("Performing health checks...")
        health_status = await container.check_all_health()
        unhealthy_services = [name for name, status in health_status.items()
                            if not status.is_healthy]

        if unhealthy_services:
            logger.warning(f"Unhealthy services detected: {unhealthy_services}")
        else:
            logger.info("All services are healthy")

        # 6. Log system status
        system_info = container.get_service_info()
        logger.info(f"System status:")
        logger.info(f"  - Total services: {system_info['total_services']}")
        logger.info(f"  - Singleton services: {system_info['singleton_services']}")
        logger.info(f"  - Active scopes: {system_info['active_scopes']}")

        logger.info("System initialization completed successfully")
        return True

    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise
```

**Graceful Shutdown:**

```python
async def graceful_shutdown():
    """Perform graceful shutdown of all services"""
    logger.info("Starting graceful shutdown...")

    try:
        container = get_container()

        # 1. Dispose all scopes
        for scope_id in list(container._scopes.keys()):
            container.dispose_scope(container._scopes[scope_id])

        # 2. Shutdown resources in reverse order
        logger.info("Shutting down resources...")

        # 3. Log completion
        logger.info("System shutdown completed successfully")

    except Exception as e:
        logger.error(f"System shutdown failed: {e}")
        raise
```

### 4.3 Service Registration Patterns

**Basic Service Registration:**

```python
# Simple registration with default implementation
container.register_service(DatabaseService, lifetime=ServiceLifetime.SINGLETON)

# Registration with factory function
container.register_service(
    CacheService,
    lifetime=ServiceLifetime.SINGLETON,
    factory=lambda c: RedisCacheService(host="localhost", port=6379)
)

# Registration with dependencies
container.register_service(
    PlayerService,
    lifetime=ServiceLifetime.SINGLETON,
    dependencies=["DatabaseService", "CacheService"]
)
```

**Singleton Registration:**

```python
# Pre-created singleton instance
db_service = DatabaseService()
container.register_singleton(DatabaseService, db_service)

# Singleton with initialization
class ConfigSingleton:
    def __init__(self):
        self.config = self._load_config()

config_instance = ConfigSingleton()
container.register_singleton(ConfigManager, config_instance)
```

**Conditional Registration:**

```python
# Feature-based registration
if feature_flags.use_new_attribute_system:
    container.register_service(AttributeCalculator, DomainAttributeCalculator)
else:
    container.register_service(AttributeCalculator, LegacyAttributeCalculator)

# Environment-based registration
if os.getenv("ENVIRONMENT") == "production":
    container.register_service(DatabaseService, ProductionDatabaseService)
else:
    container.register_service(DatabaseService, DevelopmentDatabaseService)
```

## 5. Service Registry and Discovery

### 5.1 ServiceRegistry Implementation

The ServiceRegistry provides centralized service discovery and management:

```python
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class ServiceLifetime(Enum):
    TRANSIENT = "transient"
    SINGLETON = "singleton"
    SCOPED = "scoped"

@dataclass
class ServiceRegistration:
    name: str
    service_type: Type
    lifetime: ServiceLifetime
    dependencies: List[str] = field(default_factory=list)
    health_check: Optional[IHealthCheck] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class ServiceRegistry:
    def __init__(self, container: ServiceContainer):
        self.container = container
        self._registrations: Dict[str, ServiceRegistration] = {}
        self._service_index: Dict[str, str] = {}  # service_type -> registration_name

    def register_service(self, registration: ServiceRegistration):
        """Register service with metadata"""
        self._registrations[registration.name] = registration

        # Index by service type for discovery
        service_key = self.container._get_service_key(registration.service_type)
        self._service_index[service_key] = registration.name

        # Register with container if not already registered
        if service_key not in self.container._services:
            self.container.register_service(
                registration.service_type,
                lifetime=registration.lifetime,
                dependencies=registration.dependencies
            )

        # Register health check if provided
        if registration.health_check:
            self.container.register_health_check(
                registration.name,
                registration.health_check
            )

    def get_registration(self, name: str) -> Optional[ServiceRegistration]:
        """Get service registration by name"""
        return self._registrations.get(name)

    def get_service(self, service_type: Type) -> Optional[Any]:
        """Get service instance via registry"""
        service_key = self.container._get_service_key(service_type)
        registration_name = self._service_index.get(service_key)

        if not registration_name:
            return None

        return self.container.get_service(service_type)

    def get_all_registrations(self) -> Dict[str, ServiceRegistration]:
        """Get all service registrations"""
        return self._registrations.copy()

    def get_service_types(self) -> List[Type]:
        """Get all registered service types"""
        return [reg.service_type for reg in self._registrations.values()]

    def validate_dependencies(self) -> List[str]:
        """Validate dependency graph for circular references"""
        problems = []
        visited = set()
        recursion_stack = set()

        def visit(service_name: str):
            if service_name in recursion_stack:
                problems.append(f"Circular dependency detected: {service_name}")
                return

            if service_name in visited:
                return

            visited.add(service_name)
            recursion_stack.add(service_name)

            registration = self.get_registration(service_name)
            if registration:
                for dep_name in registration.dependencies:
                    visit(dep_name)

            recursion_stack.remove(service_name)

        for service_name in self._registrations:
            visit(service_name)

        return problems

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get service dependency graph"""
        graph = {}
        for name, registration in self._registrations.items():
            graph[name] = registration.dependencies
        return graph
```

### 5.2 Service Discovery and Metadata

**Service Discovery Patterns:**

```python
class ServiceDiscovery:
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry

    def find_services_by_interface(self, interface: Type) -> List[Any]:
        """Find all services implementing given interface"""
        services = []
        for registration in self.registry.get_all_registrations().values():
            if issubclass(registration.service_type, interface):
                service = self.registry.get_service(registration.service_type)
                if service:
                    services.append(service)
        return services

    def find_services_by_tag(self, tag: str) -> List[Any]:
        """Find services by metadata tag"""
        services = []
        for registration in self.registry.get_all_registrations().values():
            if registration.metadata.get('tags') and tag in registration.metadata['tags']:
                service = self.registry.get_service(registration.service_type)
                if service:
                    services.append(service)
        return services

    def get_service_health(self) -> Dict[str, HealthStatus]:
        """Get health status of all services"""
        health_status = {}
        container = self.registry.container

        async def check_service_health():
            results = await container.check_all_health()
            for name, status in results.items():
                health_status[name] = status

        # In real implementation, would be async
        return health_status
```

**Service Metadata and Annotations:**

```python
def service(name: str, lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
           dependencies: List[str] = None, tags: List[str] = None):
    """Decorator for service registration with metadata"""
    def decorator(cls):
        # Store metadata on class
        cls._service_metadata = {
            'name': name,
            'lifetime': lifetime,
            'dependencies': dependencies or [],
            'tags': tags or []
        }
        return cls
    return decorator

# Usage example
@service(
    name="PlayerService",
    lifetime=ServiceLifetime.SINGLETON,
    dependencies=["DatabaseService", "CacheService"],
    tags=["core", "player"]
)
class PlayerService:
    def __init__(self, db_service: DatabaseService, cache: CacheService):
        self.db = db_service
        self.cache = cache
```

## 6. Integration Bridge Patterns

### 6.1 Legacy-New System Integration

The integration bridge provides seamless communication between legacy plugin systems and new clean architecture components:

```python
"""
Integration bridge for legacy-new system communication
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Global service cache for bridge access
_new_services = None

def get_new_services() -> Dict[str, Any]:
    """Get access to new system services through bridge"""
    global _new_services
    if _new_services is None:
        try:
            from infrastructure.core_services import get_container
            container = get_container()

            if container and hasattr(container, '_singletons'):
                services = {}
                for key, service in container._singletons.items():
                    service_name = service.__class__.__name__

                    # Map legacy service names to new services
                    if 'Adapter' in service_name:
                        services['attribute_adapter'] = service
                    elif 'Calculator' in service_name:
                        services['attribute_calculator'] = service
                    elif 'SessionManager' in service_name:
                        services['session_manager'] = service
                    elif 'Cache' in service_name:
                        services['cache_service'] = service
                    elif 'ConfigManager' in service_name:
                        services['config_manager'] = service
                    elif 'Database' in service_name or 'Adapter' in service_name:
                        services['database_adapter'] = service
                    elif 'Logging' in service_name:
                        services['logging_service'] = service
                    elif 'FeatureFlag' in service_name:
                        services['feature_flag_service'] = service

                _new_services = services
                print(f"Successfully accessed {len(services)} new system services")
            else:
                _new_services = {}
                print("Warning: Service container not found")

        except Exception as e:
            print(f"Error accessing new system services: {e}")
            _new_services = {}

    return _new_services
```

### 6.2 Feature Flag Integration

**Feature Flag System for System Switching:**

```python
def is_new_attribute_system_enabled() -> bool:
    """Check if new attribute system is enabled via feature flags"""
    try:
        services = get_new_services()
        feature_flag_service = services.get('feature_flag_service')

        if feature_flag_service:
            return feature_flag_service.is_enabled('new_attribute_system', False)
        else:
            # Default to enabled if service unavailable (backward compatibility)
            return True
    except Exception as e:
        print(f"Error checking feature flag: {e}")
        return True  # Fail-safe to enabled

async def calculate_attributes_with_new_system(player_data: Dict[str, Any],
                                            system_type: str = "hybrid") -> Optional[Dict[str, Any]]:
    """Calculate attributes using new system through bridge"""
    if not is_new_attribute_system_enabled():
        return None

    try:
        from application.services.attribute_adapter import AttributeAdapter, AttributeSystem

        adapter = AttributeAdapter()

        # Map system type string to enum
        system_map = {
            "legacy": AttributeSystem.LEGACY,
            "unified": AttributeSystem.UNIFIED,
            "domain": AttributeSystem.DOMAIN,
            "hybrid": AttributeSystem.HYBRID
        }

        system = system_map.get(system_type, AttributeSystem.HYBRID)

        # Use adapter to calculate attributes
        result = await adapter.calculate_attributes(
            player_id=player_data.get('user_id'),
            player_data=player_data,
            system=system
        )

        return result.attributes if result else None

    except Exception as e:
        print(f"New attribute system calculation failed: {e}")
        return None
```

### 6.3 Service Access Patterns

**Legacy Service Access:**

```python
def get_player_session_from_new_system(user_id: str) -> Optional[Any]:
    """Get player session from new system through bridge"""
    services = get_new_services()
    session_manager = services.get('session_manager')

    if session_manager:
        try:
            return session_manager.get_session(user_id, "player")
        except Exception:
            return None

    return None

def cache_player_attributes(user_id: str, attributes: Dict[str, Any], ttl: int = 3600) -> bool:
    """Cache player attributes using new cache service"""
    services = get_new_services()
    cache_service = services.get('cache_service')

    if cache_service:
        try:
            cache_key = f"player_attributes:{user_id}"
            cache_service.set(cache_key, attributes, ttl)
            return True
        except Exception as e:
            print(f"Error caching attributes: {e}")
            return False
    return False

def get_config_value(key: str, default=None) -> Any:
    """Get configuration value from new config manager"""
    services = get_new_services()
    config_manager = services.get('config_manager')

    if config_manager:
        try:
            return config_manager.get(key, default)
        except Exception as e:
            print(f"Error getting config: {e}")

    return default
```

**Domain Layer Integration:**

```python
def get_domain_services() -> Dict[str, Any]:
    """Access domain layer services through bridge"""
    try:
        # Import domain layer services
        from domain.effects.builtin import create_builtin_effects
        from domain.effects.effect_registry import effect_registry

        # Create and return domain services
        builtin_effects = create_builtin_effects()

        services = {
            'builtin_effects': builtin_effects,
            'effect_registry': effect_registry,
        }

        print(f"Successfully accessed domain services: {list(services.keys())}")
        return services

    except Exception as e:
        print(f"Error accessing domain services: {e}")
        return {}

def calculate_player_effects(player_id: str, trigger_type: str = None, context_data: dict = None) -> List[Any]:
    """Calculate player effects using new domain system"""
    try:
        services = get_domain_services()
        effect_registry = services.get('effect_registry')
        builtin_effects = services.get('builtin_effects')

        if not effect_registry or not builtin_effects:
            return []

        # Get and trigger player effects
        effects = effect_registry.get_by_trigger(trigger_type) if trigger_type else []
        active_effects = []

        for effect in effects:
            if effect.can_trigger(context_data or {}):
                active_effects.append(effect)

        return active_effects

    except Exception as e:
        print(f"Error calculating player effects: {e}")
        return []
```

### 6.4 Performance Monitoring

**Bridge Performance Metrics:**

```python
class BridgeMetrics:
    def __init__(self):
        self.metrics = {
            'new_system_calls': 0,
            'legacy_fallbacks': 0,
            'errors': 0,
            'response_times': [],
            'system_usage': {}
        }

    def record_new_system_call(self, service_name: str, duration: float):
        """Record new system usage metrics"""
        self.metrics['new_system_calls'] += 1

        if service_name not in self.metrics['system_usage']:
            self.metrics['system_usage'][service_name] = 0
        self.metrics['system_usage'][service_name] += 1

        self.metrics['response_times'].append(duration)

        # Keep only last 1000 measurements
        if len(self.metrics['response_times']) > 1000:
            self.metrics['response_times'] = self.metrics['response_times'][-1000:]

    def record_legacy_fallback(self):
        """Record legacy system usage"""
        self.metrics['legacy_fallbacks'] += 1

    def record_error(self, error_type: str):
        """Record error occurrence"""
        self.metrics['errors'] += 1

    def get_average_response_time(self) -> float:
        """Get average response time for new system calls"""
        if not self.metrics['response_times']:
            return 0.0
        return sum(self.metrics['response_times']) / len(self.metrics['response_times'])

    def get_success_rate(self) -> float:
        """Calculate success rate of new system calls"""
        total_calls = self.metrics['new_system_calls'] + self.metrics['legacy_fallbacks']
        if total_calls == 0:
            return 1.0
        return self.metrics['new_system_calls'] / total_calls

# Global metrics instance
bridge_metrics = BridgeMetrics()
```

**Enhanced Bridge with Metrics:**

```python
async def calculate_attributes_with_monitoring(player_data: Dict[str, Any],
                                            system_type: str = "hybrid") -> Optional[Dict[str, Any]]:
    """Calculate attributes with performance monitoring"""
    start_time = time.time()

    try:
        result = await calculate_attributes_with_new_system(player_data, system_type)

        duration = time.time() - start_time
        bridge_metrics.record_new_system_call("attribute_calculator", duration)

        return result

    except Exception as e:
        duration = time.time() - start_time
        bridge_metrics.record_error("attribute_calculation")
        bridge_metrics.record_legacy_fallback()

        # Fallback to legacy system
        try:
            legacy_result = calculate_legacy_attributes(player_data)
            bridge_metrics.record_new_system_call("legacy_fallback", duration)
            return legacy_result
        except:
            return None
```

This comprehensive service architecture reference provides the technical details for implementing and maintaining the Clean Architecture in GuiXiuXian2, including dependency injection, service lifecycle management, integration patterns, and performance monitoring.