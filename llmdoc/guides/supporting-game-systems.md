# Supporting Game Systems

This guide covers the four supporting systems that enhance the core gameplay experience in GuiXiuXian2: Social, World, Story, and Daily Activities.

## 1. Social System

### System Overview
The social system manages player relationships, community interactions, and social mechanics that add depth to the cultivation world.

### Key Components

#### Relationship Network
- **Marriage System**: Player partnerships with mutual benefits
- **Mentorship**: Senior-junior relationships with knowledge transfer
- **Friend System**: Social connections with collaborative features
- **Enemy/Rival System**: Conflict mechanics between players

#### Marriage Mechanics
```python
# Marriage system benefits and mechanics
marriage_system = {
    'requirements': {
        'level_min': 30,
        'relationship_level': 'Trusted',
        'mutual_consent': True
    },
    'benefits': {
        'cultivation_bonus': 1.1,      # 10% cultivation speed bonus
        'combat_synergy': 1.15,        # 15% combat effectiveness
        'economic_discount': 0.95,    # 5% discount on joint purchases
        'social_prestige': 100         # Social standing bonus
    },
    'mechanics': {
        'shared_inventory': True,      # Limited item sharing
        'teleport_together': True,    # Coordinated movement
        'special_quests': True,        # Exclusive content access
        'divorce_mechanic': True       # Relationship dissolution
    }
}
```

#### Mentorship System
- **Master Selection**: Experienced players can take apprentices
- **Knowledge Transfer**: Skills and techniques passed down
- **Guidance Bonuses**: Mentors receive rewards for successful mentoring
- **Legacy Building**: Masters build reputation through student achievements

#### Ranking Systems
- **Power Rankings**: Based on combat effectiveness and realm
- **Wealth Rankings**: Economic influence and resource control
- **Social Rankings**: Relationship networks and influence
- **Contribution Rankings**: Community involvement and helpfulness

### Social Integration
- **Guild System**: Social connections enhance guild functionality
- **Battle System**: Teams and alliances for cooperative combat
- **Economy System**: Joint ventures and trading partnerships
- **Story System**: Relationship choices affect narrative outcomes

## 2. World System

### System Overview
The world system provides the game environment, exploration mechanics, and NPC interactions that bring the cultivation world to life.

### Key Components

#### Dual Coordinate System
- **Real World Coordinates**: Large-scale navigation (-1000 to +1000 range)
- **Dungeon Coordinates**: Small-scale exploration (-5 to +5 range per level)
- **Seamless Transitions**: Moving between different coordinate systems
- **Navigation Mechanics**: Movement, teleportation, and exploration

#### Location System
```python
# World structure and exploration mechanics
world_structure = {
    'regions': {
        '大都会': {
            'type': 'main_city',
            'features': ['markets', 'guilds', 'npcs', 'training_areas'],
            'access_level': 1,
            'coordinates_range': (-1000, 1000)
        },
        '诡域': {
            'type': 'dungeon',
            'features': ['monsters', 'treasures', 'bosses', 'puzzles'],
            'access_level': 5,
            'coordinates_range': (-5, 5),
            'levels': 1  # Can be extended
        }
    },
    'navigation': {
        'movement_cost': 1,           # Energy per coordinate move
        'teleport_cost': 50,         # Energy for instant movement
        'exploration_bonus': 1.1,    # Extra rewards for discovering areas
        'coordinate_limits': (-1000, 1000)  # World boundaries
    }
}
```

#### NPC System (`plugins/xiuxian_game/models/npc.py`)
- **NPC Types**: Merchants, craftsmen, employers, ghosts, special vendors
- **Dynamic Generation**: Procedurally generated NPCs for variety
- **Interaction System**: Dialogue, quests, and services
- **Ecosystem**: NPCs respond to player actions and world events

#### Exploration Mechanics
- **Hidden Areas**: Unrevealed locations requiring exploration
- **Random Encounters**: Chance-based events during movement
- **Lore Discovery**: Story elements found through exploration
- **Resource Gathering**: Materials collected from specific locations

### World Integration
- **Cultivation System**: Different areas offer unique cultivation opportunities
- **Battle System**: Encounter monsters and bosses in various locations
- **Economy System**: Resources gathered from exploration have market value
- **Social System**: Locations become meeting points and social hubs

## 3. Story System

### System Overview
The story system provides dynamic narrative content with branching paths, player choices, and conditional outcomes that respond to player actions and attributes.

### Key Components

#### Story Engine (`plugins/xiuxian_game/story/engine.py`)
- **Node-Based Narratives**: Branching story structure with decision points
- **Conditional Branching**: Paths based on player attributes and choices
- **Dynamic Content**: Stories that adapt to player progression
- **Integration System**: Stories respond to and affect other game systems

#### Story Structure
```python
# Story node and branching mechanics
story_architecture = {
    'story_types': {
        'main_quest': 'Core narrative progression',
        'side_quest': 'Optional character development',
        'cultivation_story': 'Realm advancement narratives',
        'social_story': 'Relationship development',
        'world_story': 'Location-specific lore'
    },
    'node_types': {
        'narrative': 'Story advancement and dialogue',
        'choice': 'Decision points with consequences',
        'challenge': 'Skill-based story challenges',
        'reward': 'Story completion rewards'
    },
    'branching_logic': {
        'attribute_requirements': 'Minimum stats for certain paths',
        'relationship_dependent': 'Affected by social connections',
        'choice_consequences': 'Permanent story impact',
        'random_elements': 'Probability-based outcomes'
    }
}
```

#### Content Generation
- **Static Stories**: Pre-written narrative content
- **Dynamic Stories**: Procedurally generated content based on player state
- **Modular Design**: Story components can be combined in various ways
- **Player Integration**: Player history and choices affect narrative flow

#### Variable System
- **State Variables**: Track story progress and player choices
- **Conditional Logic**: Complex branching based on multiple factors
- **Effect Application**: Stories modify player attributes and capabilities
- **Persistence**: Story state saved and restored across sessions

### Story Integration
- **Cultivation System**: Stories provide realm advancement opportunities
- **Battle System**: Combat challenges within narrative contexts
- **Social System**: Relationship development through story choices
- **Economy System**: Story rewards include valuable resources and items

## 4. Daily Activities System

### System Overview
The daily activities system provides regular engagement opportunities, time-limited events, and consistent progression paths for players.

### Key Components

#### Activity Categories
- **Resource Gathering**: Fishing, mining, herb collection
- **Entertainment**: Mini-games and recreational activities
- **Daily Tasks**: Structured quests and objectives
- **Time-Limited Events**: Special activities with restricted access

#### Fishing System
```python
# Fishing mechanics and progression
fishing_system = {
    'requirements': {
        'level_min': 5,
        'equipment_needed': 'fishing_rod',
        'location_requirements': ['water_areas']
    },
    'progression': {
        'skill_levels': ['Novice', 'Skilled', 'Expert', 'Master'],
        'unlockable_areas': ['ponds', 'lakes', 'oceans', 'abyss'],
        'rarity_chances': {
            'common': 60,
            'uncommon': 25,
            'rare': 10,
            'legendary': 5
        }
    },
    'rewards': {
        'fish_variety': ['carp', 'salmon', 'tuna', 'dragon_fish'],
        'equipment_upgrades': ['better_rods', 'special_bait'],
        'rare_catches': ['legendary_creatures', 'ancient_artifacts']
    }
}
```

#### Part-Time Jobs
- **Job Variety**: Different activities offering unique rewards
- **Skill Requirements**: Certain jobs require specific attributes or levels
- **Time Investment**: Flexible time commitment with appropriate rewards
- **Career Progression**: Better jobs unlock with experience and reputation

#### Daily Tasks System
- **Quest Categories**: Combat, cultivation, social, and economic tasks
- **Daily Refresh**: New objectives available each day
- **Progress Tracking**: Task completion and reward distribution
- **Difficulty Scaling**: Tasks adjust based on player capabilities

#### Event System
- **Scheduled Events**: Regularly occurring special activities
- **Seasonal Content**: Time-limited events with unique rewards
- **World Events**: Server-wide activities affecting all players
- **Personal Events**: Milestone celebrations and achievement rewards

### Daily Integration
- **Cultivation System**: Daily activities provide cultivation resources
- **Battle System**: Combat challenges and equipment acquisition
- **Economy System**: Resource gathering and trading opportunities
- **Social System**: Cooperative activities and community events

## System Synergies

### Supporting System Flow
```
Daily Activities → Resource Generation → Progression → System Access
        ↓              ↓                ↓            ↓
      World → Social → Story → Core Systems → Enhanced Experience
```

### Cross-System Enhancement
- **Social Benefits**: Relationships improve daily activity efficiency
- **World Exploration**: Better locations provide superior daily rewards
- **Story Context**: Daily activities contribute to narrative development
- **Core System Integration**: Supporting systems feed into core progression

### Engagement Strategy
- **Consistent Content**: Daily activities provide regular engagement
- **Progressive Complexity**: Systems become more intricate as players advance
- **Social Integration**: Cooperative elements encourage community building
- **Long-term Goals**: Supporting systems contribute to overarching objectives

The supporting systems work together to create a rich, immersive world that responds to player actions, provides consistent engagement opportunities, and enhances the core gameplay experience through meaningful interactions and contextual content.