# 数据访问层架构概览

## 1. Identity

- **What it is**: 基于 DDD (领域驱动设计) 的多层数据访问架构，采用 Repository + Unit of Work 模式
- **Purpose**: 解耦业务逻辑与数据库操作，提供清晰的事务边界管理，支持渐进式迁移传统代码到新架构

## 2. High-Level Description

数据访问层是 GuiXiuXian2 项目的核心基础设施，负责管理所有数据库操作。该架构采用四层设计：Domain Models (领域模型) → Repository (仓储) → Unit of Work (工作单元) → Service Layer (服务层)。

核心特性包括：
- **63 个 Repository 实现**：覆盖所有领域实体（玩家、公会、物品、股票等），提供统一的数据访问接口
- **自动迁移系统**：`auto_migrate.py` 实现零停机数据库结构升级，自动添加缺失字段、索引和修复 ENUM 类型
- **两档事务管理**：命令处理器默认使用 `safe_session()`；跨多表事务使用 Unit of Work，确保多 Repository 操作的事务一致性，解决传统代码的连接泄漏问题
- **渐进式迁移**：新旧架构并存，通过适配器模式实现平滑过渡

该架构使用 SQLAlchemy 2.0 异步 ORM，支持 SQLite（默认）和 MySQL 数据库，通过 `auto_migrate.py` 替代传统的 Alembic 迁移，大幅简化数据库版本管理。
