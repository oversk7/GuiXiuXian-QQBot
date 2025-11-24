# Refactoring Implementation Guide

## 1. Step-by-Step Refactoring Methodology

### 1.1 Assessment and Planning

**Step 1: Codebase Analysis**
- Use static analysis tools to identify coupling issues
- Map out existing dependencies and circular references
- Identify critical business logic scattered across modules
- Assess testing requirements and existing test coverage

**Step 2: Architectural Design**
- Define layer boundaries and responsibilities
- Design interface contracts between layers
- Plan integration strategies for legacy components
- Create migration timeline with milestones

**Step 3: Risk Assessment**
- Identify high-risk components requiring careful migration
- Define rollback strategies for each component
- Plan for feature flag implementations
- Establish performance baselines for comparison

### 1.2 Implementation Strategy

**Step 4: Foundation Layer Implementation**
```python
# First, implement the dependency injection foundation
infrastructure/dependency_injection.py:
- Create ServiceContainer with lifecycle management
- Implement dependency resolution with type hints
- Add health check and monitoring capabilities
- Support for singleton, scoped, and transient services

# Register core services
infrastructure/core_services.py:
- Register ConfigManager, DatabaseAdapter, SessionManager
- Set up service health checks
- Configure feature flags and system options
```

**Step 5: Service Registry Setup**
```python
# Create service discovery mechanism
infrastructure/service_registry.py:
- Centralized service registration
- Dependency validation and conflict detection
- Service discovery and metadata management
- Health status aggregation and monitoring
```

**Step 6: Configuration Management**
```python
# Implement multi-source configuration
infrastructure/config_manager.py:
- Support for environment variables, JSON, YAML
- Configuration validation and schema enforcement
- Hot-reload capability for development
- Environment-specific configuration management
```

### 1.3 Domain Layer Refactoring

**Step 7: Attribute System Unification**
```python
# Replace scattered attribute calculation logic
domain/attributes/calculator.py:
- Create unified AttributeCalculator class
- Implement pluggable source pattern (Strategy Pattern)
- Add attribute breakdown and debugging capabilities
- Support for A/B testing and performance monitoring

# Create attribute sources
domain/attributes/sources/
- base_source.py - Base attribute calculation
- equipment_source.py - Equipment bonuses
- buff_source.py - Buff/debuff effects
- elixir_source.py - Elixir bonuses
```

**Step 8: Session Management Centralization**
```python
# Unify session types management
domain/ai_npcs/session_types.py:
- Define PlayerSession, StorySession, TemporarySession
- Implement session factory and lifecycle management
- Add session state management and locking

application/services/session_manager.py:
- Create unified session manager
- Implement caching and performance optimization
- Add session statistics and cleanup functionality
```

**Step 9: Effect System Standardization**
```python
# Create unified effect system
domain/effects/effect_interface.py:
- Define IEffect interface for all effects
- Implement trigger types and context system
- Add effect result and execution contracts

domain/effects/effect_registry.py:
- Centralized effect registration and discovery
- Support for multiple effect types (equipment, battle, buff)
- Effect lifecycle management and validation
```

### 1.4 Application Layer Implementation

**Step 10: Feature Flag System**
```python
# Implement feature management
application/services/feature_flags.py:
- Create FeatureFlagService with multiple strategies
- Support for percentage, user-based, and random rollout
- Feature usage tracking and analytics
- A/B testing and canary deployment support

application/api/feature_flags_api.py:
- RESTful API for feature management
- Configuration and monitoring interface
- Batch operations and export capabilities
```

**Step 11: Attribute Adapter Implementation**
```python
# Create system adapter for migration
application/services/attribute_adapter.py:
- Implement AttributeAdapter with multiple system support
- Support Legacy, Unified, Domain, and Hybrid modes
- Add A/B testing and performance monitoring
- Provide migration helper utilities
```

**Step 12: Service Integration**
```python
# Integrate all services
infrastructure/core_services.py:
- Register all core services with DI container
- Configure health checks and monitoring
- Set up feature flags and system options
- Validate dependencies and startup sequence
```

## 2. Design Patterns Used

### 2.1 Dependency Injection Pattern

**Implementation**:
```python
# Service descriptor for DI container
@dataclass
class ServiceDescriptor:
    service_type: Type
    implementation: Type
    lifetime: ServiceLifetime  # TRANSIENT, SINGLETON, SCOPED
    factory: Optional[Callable] = None
    dependencies: List[str] = field(default_factory=list)
    health_check: Optional[IHealthCheck] = None

# Usage in business logic
class PlayerService:
    def __init__(self, player_repo: IPlayerRepository, session_manager: ISessionManager):
        self.player_repo = player_repo
        self.session_manager = session_manager
```

**Benefits**:
- Loose coupling between components
- Easy testing with mock dependencies
- Centralized dependency management
- Lifecycle control for services

### 2.2 Repository Pattern

**Implementation**:
```python
# Domain interface
class IPlayerRepository(ABC):
    @abstractmethod
    async def get_by_id(self, player_id: str) -> Optional[Player]:
        pass

    @abstractmethod
    async def get_nearby_players(self, x: int, y: int, region: str, max_distance: int) -> List[Player]:
        pass

# Infrastructure implementation
class PlayerRepository(IPlayerRepository):
    def __init__(self, session: AsyncSession):
        self._session = session  # Injected, not created internally

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        stmt = select(Player).where(Player.id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

**Benefits**:
- Clear separation of data access logic
- Easy testing with mock repositories
- Support for different data storage implementations
- Transaction boundary management

### 2.3 Strategy Pattern

**Implementation**:
```python
# Strategy interface for attribute sources
class IAttributeSource(ABC):
    @abstractmethod
    async def calculate_bonus(self, context: AttributeSourceContext) -> List[AttributeBonus]:
        pass

    @abstractmethod
    def is_active(self, context: AttributeSourceContext) -> Tuple[bool, str]:
        pass

# Concrete strategies
class EquipmentAttributeSource(IAttributeSource):
    async def calculate_bonus(self, context: AttributeSourceContext) -> List[AttributeBonus]:
        equipment = await self._equipment_repo.get_equipped(context.player_id)
        return [AttributeBonus(attack=item.attack_bonus) for item in equipment]

class BuffAttributeSource(IAttributeSource):
    async def calculate_bonus(self, context: AttributeSourceContext) -> List[AttributeBonus]:
        buffs = await self._buff_repo.get_active(context.player_id)
        return [AttributeBonus(attack=buff.bonus) for buff in buffs]
```

**Benefits**:
- Easy to add new attribute sources
- Each source has single responsibility
- Algorithm can be changed at runtime
- Open/closed principle compliance

### 2.4 Observer Pattern

**Implementation**:
```python
# Event system for decoupled communication
class EventBus:
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[Callable]] = {}

    def subscribe(self, event_type: Type[DomainEvent], handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent):
        handlers = self._handlers.get(type(event), [])
        await asyncio.gather(*[handler(event) for handler in handlers])

# Usage with domain events
async def on_player_level_up(event: PlayerLevelUpEvent):
    # Send notifications, update achievements, etc.
    await notification_service.send_level_up_notification(event.player_id)
    await achievement_service.check_level_achievements(event.player_id, event.new_level)
```

**Benefits**:
- Decoupled component communication
- Multiple subscribers per event
- Easy to add new event handlers
- Supports cross-cutting concerns

### 2.5 Command Pattern

**Implementation**:
```python
# Command interface for NPC actions
class ICommand(ABC):
    @abstractmethod
    def can_execute(self, context: CommandContext) -> bool:
        pass

    @abstractmethod
    async def execute(self, context: CommandContext) -> CommandResult:
        pass

# Concrete command
class AttackCommand(ICommand):
    def __init__(self, battle_engine: IBattleEngine):
        self._battle_engine = battle_engine  # Injected dependency

    def can_execute(self, context: CommandContext) -> bool:
        return context.target is not None

    async def execute(self, context: CommandContext) -> CommandResult:
        result = await self._battle_engine.start_battle(
            attacker=context.executor,
            defender=context.target
        )
        return CommandResult(success=True, data={"battle_id": result.battle_id})
```

**Benefits**:
- Decoupled action execution
- Easy to add new commands
- Supports undo/redo functionality
- Command queuing and scheduling

## 3. Phase-Based Implementation Strategy

### 3.1 Phase 1: Foundation (Weeks 1-5)

**Objective**: Establish the architectural foundation and core infrastructure

**Week 1: Dependency Injection System**
- Implement ServiceContainer with lifecycle management
- Add dependency resolution with type hints
- Create health check framework
- Register core services (Config, Database, Logging)

**Week 2: Service Registry System**
- Create service discovery mechanism
- Implement dependency validation
- Add health status monitoring
- Configure feature flag system

**Week 3: Configuration Management**
- Implement multi-source configuration loading
- Add configuration validation and schema
- Create hot-reload capability
- Environment-specific configuration

**Week 4: Session Management**
- Unify session types (Player, Story, Temporary)
- Implement session caching and locking
- Add session lifecycle management
- Performance optimization

**Week 5: Attribute System**
- Create unified attribute calculator
- Implement source pattern for attributes
- Add A/B testing capabilities
- Performance monitoring and metrics

### 3.2 Phase 2: System Integration (Weeks 6-8)

**Objective**: Integrate new systems with existing functionality

**Week 6: Effect System**
- Standardize effect interfaces
- Create effect registry and management
- Migrate existing effects to new system
- Testing and validation

**Week 7: Domain Services**
- Extract domain services from application logic
- Implement domain events and handlers
- Add business rule validation
- Cross-cutting concerns implementation

**Week 8: Migration Tools**
- Create integration bridge components
- Implement migration helpers
- Add rollback mechanisms
- Performance optimization

### 3.3 Phase 3: Performance and Testing (Weeks 9-12)

**Objective**: Optimize performance and establish comprehensive testing

**Week 9: Performance Optimization**
- Implement caching strategies
- Optimize database queries
- Add monitoring and metrics
- Performance testing and tuning

**Week 10: Testing Infrastructure**
- Create test framework and fixtures
- Implement unit and integration tests
- Add performance and load testing
- Continuous integration setup

**Week 11: Documentation and Training**
- Create comprehensive documentation
- Developer training materials
- API documentation
- Usage examples and tutorials

**Week 12: Production Deployment**
- Create deployment scripts
- Implement monitoring and alerting
- Production validation
- Go-live strategy and rollback plan

## 4. Migration Patterns and Backward Compatibility

### 4.1 Feature Flag Pattern

**Implementation**:
```python
# Feature flag service for system switching
class FeatureFlagService:
    def __init__(self):
        self._features: Dict[str, FeatureFlag] = {}

    def is_enabled(self, feature_name: str, default: bool = False) -> bool:
        feature = self._features.get(feature_name)
        if not feature:
            return default
        return feature.evaluate()

    def register_feature(self, name: str, default: bool = False, strategy: str = "boolean"):
        flag = FeatureFlag(name, default, strategy)
        self._features[name] = flag

# Usage in business logic
from integration_bridge import is_new_attribute_system_enabled

async def calculate_player_attributes(player: Player) -> Dict[str, int]:
    if is_new_attribute_system_enabled():
        # Use new clean architecture system
        calculator = container.resolve(AttributeCalculator)
        breakdown = await calculator.calculate_final_attributes(player)
        return breakdown.total.__dict__
    else:
        # Use legacy system for backward compatibility
        return player.get_effective_attributes()
```

**Benefits**:
- Gradual system switching without code changes
- Risk-free testing in production environment
- A/B testing and canary deployment support
- Easy rollback if issues arise

### 4.2 Adapter Pattern

**Implementation**:
```python
# Legacy-new system adapter
class AttributeAdapter:
    def __init__(self):
        self.legacy_calculator = LegacyAttributeCalculator()
        self.unified_calculator = UnifiedAttributeCalculator()

    async def calculate_attributes(self, player_data: Dict, system: str = "unified"):
        if system == "legacy":
            return self.legacy_calculator.calculate(player_data)
        elif system == "unified":
            return await self.unified_calculator.calculate(player_data)
        elif system == "hybrid":
            # Critical paths use legacy, others use new
            return await self._calculate_hybrid(player_data)

# Integration bridge for legacy code
def integration_bridge.calculate_attributes(player_data):
    adapter = container.resolve(AttributeAdapter)
    return adapter.calculate_attributes(player_data, "hybrid")
```

**Benefits**:
- Legacy code can use new systems without modification
- Multiple system types supported simultaneously
- Gradual migration capability
- System isolation and independent testing

### 4.3 Integration Bridge Pattern

**Implementation**:
```python
# Bridge between legacy and new systems
class IntegrationBridge:
    def __init__(self, container: ServiceContainer):
        self.container = container

    async def get_new_service(self, service_name: str):
        """Get new system service through bridge"""
        try:
            # Map legacy service names to new services
            service_mapping = {
                'attribute_calculator': 'AttributeCalculator',
                'session_manager': 'SessionManager',
                'database': 'DatabaseAdapter'
            }

            new_service_name = service_mapping.get(service_name)
            if new_service_name:
                return await self.container.get_service(new_service_name)
            return None
        except Exception as e:
            logger.error(f"Integration bridge error: {e}")
            return None

# Legacy code usage
bridge = IntegrationBridge(container)
new_session_manager = await bridge.get_new_service('session_manager')
if new_session_manager:
    session = await new_session_manager.get_player_session(player_id)
```

**Benefits**:
- Clean separation between old and new systems
- Gradual migration capability
- Error isolation and fallback mechanisms
- Performance monitoring and metrics

### 4.4 A/B Testing Pattern

**Implementation**:
```python
# A/B testing for system validation
class ABTestRunner:
    def __init__(self, adapter: AttributeAdapter):
        self.adapter = adapter
        self.results: List[ABTestResult] = []

    async def run_ab_test(self, player_id: str, player_data: Dict) -> ABTestResult:
        # Test both systems
        legacy_result = await self.adapter.calculate_attributes(
            player_data, "legacy"
        )
        new_result = await self.adapter.calculate_attributes(
            player_data, "unified"
        )

        # Compare results
        comparison = self.adapter.compare_results(
            legacy_result.attributes, new_result.attributes
        )

        result = ABTestResult(
            player_id=player_id,
            legacy_attributes=legacy_result.attributes,
            new_attributes=new_result.attributes,
            comparison=comparison,
            legacy_time=legacy_result.calculation_time,
            new_time=new_result.calculation_time
        )

        self.results.append(result)
        return result

# Continuous validation during migration
async def validate_migration_results():
    ab_test = ABTestRunner(attribute_adapter)
    results = await ab_test.run_ab_test(player_id, player_data)

    if results.comparison.changed_attributes:
        logger.warning(f"Attribute calculation changed for {player_id}")
        # Potentially flag for manual review
    else:
        logger.info(f"Validation passed for {player_id}")
```

**Benefits**:
- Continuous validation of system consistency
- Early detection of calculation differences
- Performance comparison and optimization
- Confidence building during migration

## 5. Risk Management and Quality Assurance

### 5.1 Risk Mitigation Strategies

**High-Risk Component Mitigation**:
```python
# Isolation wrapper for high-risk components
class IsolatedService:
    def __init__(self, service: Any, fallback: Any):
        self.service = service
        self.fallback = fallback
        self.error_count = 0
        self.max_errors = 5

    async def execute(self, *args, **kwargs):
        try:
            if self.error_count >= self.max_errors:
                logger.warning(f"Switching to fallback for {self.service.__class__.__name__}")
                return await self.fallback.execute(*args, **kwargs)

            result = await self.service.execute(*args, **kwargs)
            self.error_count = 0  # Reset on success
            return result
        except Exception as e:
            self.error_count += 1
            logger.error(f"Service error {self.error_count}/{self.max_errors}: {e}")
            return await self.fallback.execute(*args, **kwargs)
```

**Performance Monitoring**:
```python
# Performance monitoring for critical paths
class PerformanceMonitor:
    def __init__(self, threshold_ms: float = 100.0):
        self.threshold_ms = threshold_ms
        self.metrics: Dict[str, List[float]] = {}

    def monitor(self, operation_name: str):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration = (time.time() - start_time) * 1000  # Convert to ms
                    self.record_metric(operation_name, duration)

                    if duration > self.threshold_ms:
                        logger.warning(f"Slow operation: {operation_name} took {duration:.2f}ms")
            return wrapper
        return decorator

    def record_metric(self, operation: str, duration: float):
        if operation not in self.metrics:
            self.metrics[operation] = []
        self.metrics[operation].append(duration)
```

### 5.2 Testing Strategy

**Unit Testing Framework**:
```python
# Mock dependencies for testing
class MockPlayerRepository(IPlayerRepository):
    def __init__(self, players: List[Player]):
        self.players = {p.id: p for p in players}

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    async def get_nearby_players(self, x: int, y: int, region: str, max_distance: int) -> List[Player]:
        return [p for p in self.players.values()
                if p.region == region and self._distance(x, y, p.x, p.y) <= max_distance]

# Example unit test
@pytest.mark.asyncio
async def test_attribute_calculator():
    # Arrange
    mock_repo = MockPlayerRepository([test_player])
    calculator = AttributeCalculator()
    calculator.add_source(EquipmentAttributeSource(mock_repo))

    # Act
    breakdown = await calculator.calculate_final_attributes(test_player)

    # Assert
    assert breakdown.total.attack == 60  # Base + Equipment
    assert breakdown.equipment.attack == 10
```

**Integration Testing**:
```python
# Integration test with full container
@pytest.fixture
async def test_container():
    container = ServiceContainer()
    # Register all test services
    await container.initialize()
    return container

@pytest.mark.asyncio
async def test_player_service_integration(test_container):
    # Arrange
    player_service = await test_container.get_service(PlayerService)

    # Act
    player = await player_service.create_player("test_user", "Test Player")

    # Assert
    assert player.id is not None
    assert player.nickname == "Test Player"

    # Clean up
    await player_service.delete_player(player.id)
```

### 5.3 Monitoring and Alerting

**Health Check System**:
```python
# Comprehensive health monitoring
class HealthCheckManager:
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.alert_thresholds = {
            'error_rate': 0.05,  # 5% error rate
            'response_time': 1000,  # 1 second
            'memory_usage': 0.8,  # 80% memory
        }

    async def perform_health_check(self) -> HealthReport:
        # Service health checks
        service_health = await self.container.check_all_health()

        # Performance metrics
        performance_metrics = self.get_performance_metrics()

        # Database connectivity
        db_health = await self.check_database_health()

        # Alert if thresholds exceeded
        alerts = self.check_thresholds(performance_metrics)

        return HealthReport(
            timestamp=datetime.now(),
            services=service_health,
            performance=performance_metrics,
            database=db_health,
            alerts=alerts
        )

    def check_thresholds(self, metrics: Dict[str, float]) -> List[Alert]:
        alerts = []
        for metric, value in metrics.items():
            threshold = self.alert_thresholds.get(metric)
            if threshold and value > threshold:
                alerts.append(Alert(
                    level="warning",
                    metric=metric,
                    value=value,
                    threshold=threshold,
                    message=f"{metric} exceeded threshold: {value} > {threshold}"
                ))
        return alerts
```

This comprehensive implementation guide provides the roadmap, patterns, and strategies for successfully implementing the Clean Architecture Refactoring while maintaining system stability and enabling gradual migration.