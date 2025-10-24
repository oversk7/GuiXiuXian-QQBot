# 诡修仙架构图集

> 本文档包含重构前后的架构对比图和详细的系统设计图

---

## 1. 当前架构 vs 新架构对比

### 1.1 当前架构 (重构前)

```mermaid
graph TB
    subgraph "当前架构 - 单体应用"
        A[Nonebot2命令处理]
        
        subgraph "业务逻辑层 (混合)"
            B1[玩家命令]
            B2[战斗命令]
            B3[装备命令]
            B4[公会命令]
        end
        
        subgraph "数据访问 (直接调用)"
            C1[SQLAlchemy ORM]
            C2[safe_session]
        end
        
        D[(SQLite数据库)]
        
        A --> B1
        A --> B2
        A --> B3
        A --> B4
        
        B1 --> C1
        B2 --> C1
        B3 --> C1
        B4 --> C1
        
        C1 --> C2
        C2 --> D
    end
    
    style D fill:#f99,stroke:#333,stroke-width:2px
    
    E[问题标注]
    E -.-> F[❌ 业务逻辑与命令处理混合]
    E -.-> G[❌ 直接依赖ORM，难以测试]
    E -.-> H[❌ SQLite性能瓶颈]
    E -.-> I[❌ 缺少缓存层]
```

### 1.2 新架构 (重构后)

```mermaid
graph TB
    subgraph "新架构 - 分层架构"
        subgraph "接入层"
            A1[Nonebot2路由]
            A2[参数验证]
        end
        
        subgraph "应用层 (Use Cases)"
            B1[玩家用例]
            B2[战斗用例]
            B3[装备用例]
            B4[NPC交互用例]
        end
        
        subgraph "领域层 (Domain)"
            C1[玩家领域]
            C2[战斗领域]
            C3[装备领域]
            C4[NPC领域]
            C5[领域服务]
        end
        
        subgraph "基础设施层"
            D1[MySQL仓储]
            D2[Redis缓存]
            D3[AI服务]
            D4[事件总线]
        end
        
        E[(MySQL数据库)]
        F[(Redis缓存)]
        G[AI API]
        
        A1 --> A2
        A2 --> B1
        A2 --> B2
        A2 --> B3
        A2 --> B4
        
        B1 --> C1
        B2 --> C2
        B3 --> C3
        B4 --> C4
        
        C1 --> C5
        C2 --> C5
        C3 --> C5
        C4 --> C5
        
        C5 --> D1
        C5 --> D2
        C4 --> D3
        
        D1 --> E
        D2 --> F
        D3 --> G
    end
    
    style E fill:#9f9,stroke:#333,stroke-width:2px
    style F fill:#9f9,stroke:#333,stroke-width:2px
    
    H[优势标注]
    H -.-> I[✅ 清晰的分层架构]
    H -.-> J[✅ 依赖倒置，易于测试]
    H -.-> K[✅ MySQL高性能]
    H -.-> L[✅ Redis缓存加速]
```

---

## 2. 核心系统详细设计

### 2.1 属性计算系统

```mermaid
graph LR
    A[玩家] --> B[AttributeCalculator]
    
    B --> C1[基础属性]
    B --> C2[装备加成]
    B --> C3[丹药加成]
    B --> C4[临时Buff]
    B --> C5[VIP加成]
    
    C1 --> D[最终属性]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    
    D --> E[属性明细]
    
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style D fill:#bfb,stroke:#333,stroke-width:2px
```

### 2.2 装备效果系统

```mermaid
graph TB
    A[装备实例] --> B[EquipmentEffectRegistry]
    
    B --> C{效果类型}
    
    C -->|属性加成| D1[AttributeBonus]
    C -->|战斗触发| D2[BattleTrigger]
    C -->|特殊效果| D3[SpecialEffect]
    
    D1 --> E[EffectContext]
    D2 --> E
    D3 --> E
    
    E --> F[EffectResult]
    
    F --> G[应用到玩家]
    
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style E fill:#fbb,stroke:#333,stroke-width:2px
```

### 2.3 NPC AI Agent系统

```mermaid
graph TB
    A[玩家消息] --> B[NPCAgent]
    
    B --> C1[加载记忆]
    B --> C2[意图识别]
    B --> C3[好感度检查]
    
    C1 --> D[VectorMemoryStore]
    C2 --> E[AI服务]
    C3 --> F[AffinitySystem]
    
    D --> G[生成响应]
    E --> G
    F --> G
    
    G --> H[行为决策]
    
    H --> I1[对话回复]
    H --> I2[执行指令]
    H --> I3[更新好感度]
    H --> I4[存储记忆]
    
    I1 --> J[返回给玩家]
    I2 --> J
    
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style E fill:#fbf,stroke:#333,stroke-width:2px
    style F fill:#ffb,stroke:#333,stroke-width:2px
```

---

## 3. 数据流图

### 3.1 玩家战斗流程

```mermaid
sequenceDiagram
    participant P as 玩家
    participant C as 命令处理器
    participant U as 战斗用例
    participant D as 战斗领域
    participant R as 仓储
    participant DB as MySQL
    participant Cache as Redis
    
    P->>C: /战斗 目标
    C->>U: execute_battle(player_id, target_id)
    
    U->>Cache: 获取玩家数据
    alt 缓存命中
        Cache-->>U: 返回玩家数据
    else 缓存未命中
        U->>R: get_player(player_id)
        R->>DB: SELECT * FROM player
        DB-->>R: 玩家数据
        R-->>U: 玩家对象
        U->>Cache: 缓存玩家数据
    end
    
    U->>D: calculate_battle(attacker, defender)
    D->>D: 计算属性、应用效果
    D-->>U: 战斗结果
    
    U->>R: update_player(player)
    R->>DB: UPDATE player
    U->>Cache: 更新缓存
    
    U-->>C: 战斗结果
    C-->>P: 显示战斗结果
```

### 3.2 NPC对话流程

```mermaid
sequenceDiagram
    participant P as 玩家
    participant C as 命令处理器
    participant N as NPCAgent
    participant M as MemoryStore
    participant AI as AI服务
    participant A as AffinitySystem
    
    P->>C: 对NPC说话
    C->>N: process_interaction(player, message)
    
    N->>M: get_memory(npc_id, player_id)
    M-->>N: 历史记忆
    
    N->>AI: recognize_intent(message)
    AI-->>N: 意图识别结果
    
    N->>A: get_affinity(npc_id, player_id)
    A-->>N: 好感度分数
    
    N->>AI: generate_response(context)
    AI-->>N: NPC回复
    
    N->>N: decide_actions(intent, affinity)
    
    N->>M: store_memory(interaction)
    N->>A: update_affinity(change)
    
    N-->>C: NPCResponse
    C-->>P: 显示NPC回复
```

---

## 4. 数据库设计

### 4.1 核心表关系图

```mermaid
erDiagram
    PLAYER ||--o{ ITEM_INSTANCE : owns
    PLAYER ||--o{ TEMPORARY_BUFF : has
    PLAYER }o--|| GUILD : belongs_to
    PLAYER ||--o{ STOCK_HOLDING : holds
    PLAYER ||--o{ MARKET_ORDER : creates
    
    GUILD ||--o{ GUILD_MEMBER : has
    GUILD ||--o{ GUILD_BUILDING : owns
    
    NPC ||--|| LOCATION : located_at
    NPC ||--o{ NPC_AFFINITY : has
    
    LOCATION ||--o{ WORLD_TILE : contains
    
    PLAYER {
        string id PK
        int uid UK
        string nickname
        int level
        int exp
        string region
        int x
        int y
    }
    
    ITEM_INSTANCE {
        bigint id PK
        string player_id FK
        string item_id
        int quantity
        bool equipped
        json extra_attrs
    }
    
    NPC {
        int id PK
        string npc_id UK
        string name
        enum npc_type
        int location_id FK
        enum status
    }
    
    NPC_AFFINITY {
        int id PK
        string npc_id FK
        string player_id FK
        int score
        datetime updated_at
    }
```

### 4.2 索引策略

```mermaid
graph TB
    A[索引策略] --> B[单列索引]
    A --> C[复合索引]
    A --> D[全文索引]
    
    B --> B1[player.level]
    B --> B2[npc.status]
    
    C --> C1[player: region, x, y]
    C --> C2[item_instance: player_id, equipped]
    C --> C3[npc: location_id, status]
    
    D --> D1[player.nickname]
    
    style A fill:#bbf,stroke:#333,stroke-width:2px
```

---

## 5. 部署架构

### 5.1 单机部署 (初期)

```mermaid
graph TB
    subgraph "服务器"
        A[Nonebot2应用]
        B[(MySQL)]
        C[(Redis)]
    end
    
    D[QQ群] --> A
    A --> B
    A --> C
    A --> E[OpenAI API]
    
    style A fill:#9f9,stroke:#333,stroke-width:2px
```

### 5.2 分布式部署 (后期)

```mermaid
graph TB
    subgraph "负载均衡层"
        LB[Nginx]
    end
    
    subgraph "应用层"
        A1[Nonebot2实例1]
        A2[Nonebot2实例2]
        A3[Nonebot2实例3]
    end
    
    subgraph "数据层"
        B1[(MySQL主)]
        B2[(MySQL从1)]
        B3[(MySQL从2)]
        C[(Redis集群)]
    end
    
    D[QQ群] --> LB
    LB --> A1
    LB --> A2
    LB --> A3
    
    A1 --> B1
    A2 --> B1
    A3 --> B1
    
    B1 --> B2
    B1 --> B3
    
    A1 --> C
    A2 --> C
    A3 --> C
    
    A1 --> E[AI服务]
    A2 --> E
    A3 --> E
    
    style LB fill:#bbf,stroke:#333,stroke-width:2px
    style B1 fill:#f99,stroke:#333,stroke-width:2px
```

---

## 6. 监控架构

```mermaid
graph TB
    subgraph "应用层"
        A[Nonebot2应用]
    end
    
    subgraph "监控层"
        B[Prometheus]
        C[Grafana]
        D[AlertManager]
    end
    
    subgraph "日志层"
        E[日志收集]
        F[日志存储]
    end
    
    A -->|指标| B
    A -->|日志| E
    
    B --> C
    B --> D
    
    E --> F
    
    D -->|告警| G[通知渠道]
    
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style C fill:#bfb,stroke:#333,stroke-width:2px
```

---

**文档结束**

