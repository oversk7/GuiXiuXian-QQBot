# Core Game Systems Deep Dive

This guide provides detailed coverage of the four core game systems in GuiXiuXian2: Cultivation, Battle, Economy, and Guild.

## 1. Cultivation System

### System Overview
The cultivation system is the foundation of character progression, managing realm advancement, spiritual development, and core character growth.

### Key Components

#### Cultivation Core (`plugins/xiuxian_game/cultivate/core.py`)
- **Realm Progression**: Structured advancement through cultivation levels
- **Spiritual Roots**: Character attributes affecting cultivation potential
- **Breakthrough Mechanics**: Probabilistic advancement with failure accumulation
- **Cultivation Methods**: Techniques affecting cultivation efficiency

#### Realm Advancement
```python
# Realm progression follows exponential growth patterns
def calculate_realm_requirements(realm: int) -> dict:
    base_exp = 1000
    realm_multiplier = realm * 1.5

    return {
        'exp_required': base_exp * realm_multiplier,
        'breakthrough_chance': max(0.1, 1.0 - (realm * 0.1)),
        'spiritual_cost': realm * 100
    }
```

#### Spiritual Roots System
- **Root Quality**: Determines maximum potential and cultivation speed
- **Root Type**: Affects affinity for different cultivation methods
- **Root Development**: Can be enhanced through special items and techniques

#### Breakthrough Mechanics
- **Success Probability**: Decreases with higher realms
- **Failure Penalties**: Accumulated failures increase breakthrough costs
- **Mitigation Strategies**: Special items and techniques can improve success rates
- **Breakthrough Events**: Significant milestones with narrative and gameplay rewards

### Cultivation Workflow
1. **Choose Cultivation Method**: Select technique based on spiritual roots
2. **Accumulate Experience**: Gain through meditation, battles, and story events
3. **Attempt Breakthrough**: Probabilistic advancement with strategic elements
4. **Apply Bonuses**: Guild buildings, equipment, and temporary effects
5. **Continue Progression**: Repeat through higher realms

### Integration Points
- **Battle System**: Cultivation level affects combat power and skill effectiveness
- **Economy System**: Requires investment in cultivation resources and tools
- **Story System**: Cultivation progress unlocks narrative branches
- **Guild System**: Buildings provide cultivation bonuses and efficiency

## 2. Battle System

### System Overview
The battle system provides turn-based combat with advanced mechanics, attributes, and strategic depth.

### Key Components

#### Enhanced Battle Engine (`plugins/xiuxian_game/battle/enhanced_engine.py`)
- **Turn-Based Combat**: Strategic decision-making with multiple phases
- **Attribute System**: Comprehensive stats with special effects
- **Skill System**: Abilities with cooldowns and resource management
- **Effects System**: Buffs, debuffs, and special mechanics

#### Combat Attributes
```python
# Comprehensive battle attribute system
battle_attributes = {
    # Core combat stats
    'attack': 100,         # Base damage dealing capability
    'defense': 80,         # Damage reduction
    'agility': 60,         # Speed and dodge chance
    'luck': 50,            # Critical hit and loot quality

    # Advanced combat mechanics
    'critical_rate': 15,    # Chance to score critical hits
    'critical_power': 20,   # Critical hit damage multiplier
    'combo_rate': 10,      # Chance to perform combo attacks
    'counter_rate': 5,     # Chance to counter-attack
    'dodge_rate': 20,      # Chance to avoid attacks entirely
    'accuracy_rate': 85,   # Hit chance accuracy
    'skill_crit_rate': 8,  # Special ability critical rate

    # Damage type modifiers
    'penetration_rate': 12, # Armor piercing ability
    'lifesteal_rate': 5,    # HP steal on damage dealt
    'immobilize_rate': 3,   # Chance to freeze enemy
    'true_damage_rate': 2,  # Ignore defense damage
    'regen_rate': 10        # Health regeneration per turn
}
```

#### Combat Phases
1. **Preparation Phase**: Buff application and stance selection
2. **Action Phase**: Player and simultaneous enemy actions
3. **Resolution Phase**: Damage calculation and effect application
4. **Cleanup Phase**: Status updates and cooldown management

#### Skill System
- **Skill Types**: Attack, Defense, Support, and Special abilities
- **Resource Management**: MP/energy consumption for skill usage
- **Cooldown System**: Strategic planning for ability timing
- **Synergy Effects**: Skill combinations for enhanced damage

#### Effects System
```python
# Effect types and their applications
effect_types = {
    'BUFF': 'Enhances positive attributes',
    'DEBUFF': 'Reduces enemy capabilities',
    'DOT': 'Damage over time effects',
    'HOT': 'Healing over time',
    'CC': 'Crowd control abilities',
    'SPECIAL': 'Unique battle mechanics'
}
```

### Battle Integration
- **Cultivation System**: Realm level affects maximum power and skill access
- **Economy System**: Equipment purchasing and enhancement for combat strength
- **Guild System**: Training facilities provide combat bonuses
- **Social System**: Team battles and guild-vs-guild combat

## 3. Economy System

### System Overview
The economy system manages all monetary and item transactions, providing multiple ways for players to acquire and trade resources.

### Key Components

#### Market System (`plugins/xiuxian_game/economy/market.py`)
- **Dual Currency**: Gold and points system with different purposes
- **Marketplace**: Player-to-player trading platform
- **NPC Merchants**: Vendor interactions with special offers
- **Stock Market**: Dynamic trading with price fluctuations

#### Currency System
```python
# Multi-layered economy structure
economy_structure = {
    'primary_currency': {
        'name': 'Gold',
        'symbol': '💰',
        'use_cases': ['Equipment', 'Items', 'Services']
    },
    'secondary_currency': {
        'name': 'Points',
        'symbol': '💎',
        'use_cases': ['Premium Items', 'Special Services', 'Guild Contributions']
    },
    'special_currency': {
        'name': 'Tokens',
        'symbol': '🪙',
        'use_cases': ['Limited Events', 'Exclusive Items']
    }
}
```

#### Trading Mechanics
- **Order System**: Buy/sell orders with price discovery
- **Transaction Fees**: Market takes percentage on trades
- **Price Limits**: Maximum and minimum price controls
- **Stock Management**: Limited supply items with restocking

#### Part-Time Job System
- **Job Types**: Various activities offering different rewards
- **Skill Requirements**: Certain jobs require specific player attributes
- **Time Investment**: Effort-based reward scaling
- **Career Progression**: Better jobs unlock at higher levels

#### Equipment Economy
- **Equipment Classes**: Weapons, armor, accessories with different rarities
- **Enhancement System**: Improving equipment power through upgrades
- **Repair Mechanics**: Durability management system
- **Socket System**: Gem customization for stat customization

### Economic Integration
- **Cultivation**: Requires investment in cultivation pills and resources
- **Battle**: Equipment acquisition and enhancement for combat power
- **Guild**: Funding construction and activities through donations
- **Social**: Prestige items and social status symbols

## 4. Guild System

### System Overview
The guild system provides social organization, collective benefits, and large-scale content for players to experience together.

### Key Components

#### Guild Management (`plugins/xiuxian_game/guild/guild.py`)
- **Hierarchical Structure**: President, Vice-President, Core Members, Regular Members
- **Territory System**: Guild bases with defensive and utility buildings
- **Collective Progression**: Guild leveling and member cooperation
- **Management Tools**: Administrative controls for large organizations

#### Guild Buildings
```python
# Building types and their effects
building_types = {
    'EXPERIENCE_SHRINE': {
        'effect': 'Experience gain multiplier',
        'max_level': 10,
        'benefit': 'Increases all experience gains'
    },
    'TREASURY_VAULT': {
        'effect': 'Gold storage capacity',
        'max_level': 15,
        'benefit': 'Larger guild treasury'
    },
    'TRAINING_GROUND': {
        'effect': 'Cultivation bonus',
        'max_level': 8,
        'benefit': 'Member cultivation efficiency'
    },
    'TELEPORT_ARRAY': {
        'effect': 'Transportation network',
        'max_level': 5,
        'benefit': 'Guild member teleportation'
    },
    'ALCHEMY_ROOM': {
        'effect': 'Potion production',
        'max_level': 10,
        'benefit': 'Generates consumables'
    },
    'GUILD_WAREHOUSE': {
        'effect': 'Shared storage',
        'max_level': 20,
        'benefit': 'Item sharing between members'
    }
}
```

#### Territory System
- **Base Placement**: Guilds establish bases in the world
- **Territory Range**: Influence area around the base
- **Defense Mechanics**: Territory protection and conflicts
- **Resource Generation**: Territories provide ongoing benefits

#### Guild Economy
- **Treasury Management**: Collective funds and contribution tracking
- **Building Costs**: Resource investment for upgrades
- **Donation System**: Members contribute for collective benefits
- **Reward Distribution**: Bonuses based on contribution levels

#### Social Features
- **Member Management**: Recruitment, promotion, and discipline tools
- **Communication**: Announcement system and internal messaging
- **Event Organization**: Guild-wide activities and competitions
- **Alliance System**: Inter-guild cooperation and diplomacy

### Guild Integration
- **Cultivation**: Buildings provide cultivation efficiency bonuses
- **Battle**: Training facilities improve combat capabilities
- **Economy**: Collective purchasing power and shared resources
- **Social**: Prestige, relationships, and community features

## System Interactions

### Core Synergy Flow
```
Player Activity → System Choice → Resource Investment → Progression → Benefits
       ↓             ↓            ↓               ↓           ↓
Cultivation ← Battle ← Economy ← Guild ← Social ← World
```

### Cross-System Dependencies
- **Attribute Calculation**: Integration bridge unifies all stat sources
- **Effect Application**: Battle system processes buffs from multiple sources
- **Resource Sharing**: Economy system manages currency flow across activities
- **Progression Gates**: Higher levels in one system unlock content in others

### Balance Considerations
- **Power Scaling**: Each system contributes to overall power curve
- **Resource Allocation**: Players must prioritize which systems to invest in
- **Collaboration vs Competition**: Guild system enables cooperative advantages
- **Time Investment**: Different systems offer varying time/reward ratios

This core game systems architecture provides a comprehensive framework for deep and engaging gameplay experiences across all major activities in GuiXiuXian2.