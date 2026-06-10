# 市场交易架构

## 1. 身份标识

- **定义**: 基于订单簿(Order Book)模式的玩家间P2P交易系统,支持物品和装备的自动撮合交易
- **目的**: 提供公平、透明、高效的玩家间资源交换平台,通过价格优先、时间优先原则实现自动成交

## 2. 核心组件

- `plugins/xiuxian_game/economy/market.py` (_try_auto_match, calculate_transaction_tax): 自动撮合引擎,执行买单/卖单匹配、物品转移、税收计算
- `plugins/xiuxian_game/economy/equipment_trade_service.py` (EquipmentTradeService): 装备交易服务,处理装备实例的冻结、转移、所有权变更
- `plugins/xiuxian_game/models/market_order.py` (MarketOrder, OrderSide): 统一订单模型,支持普通物品和装备实例交易
- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py` (ItemRepository): 物品仓储层,提供物品/装备的原子性转移操作
- `plugins/xiuxian_game/infrastructure/repositories/market_order_repository.py` (MarketOrderRepository): 订单仓储层,管理订单的CRUD操作

## 3. 执行流程 (LLM检索地图)

### 3.1 订单挂牌流程

- **1. 参数解析**: `plugins/xiuxian_game/economy/market.py:222-246` - 解析【挂牌 出售/收购 物品名 单价 数量】,验证价格≥10、数量>0
- **2. 物品验证**: `plugins/xiuxian_game/economy/market.py:249-260` - 查找物品配置,装备交易转入特殊流程,普通物品继续
- **3. 挂牌限制检查**: `plugins/xiuxian_game/economy/market.py:268-275` - 查询玩家当前活跃订单数,限制最多6个(MAX_LISTINGS)
- **4. 底价计算与吸附**: `plugins/xiuxian_game/economy/market.py:278-296` - 调用_compute_item_floor_price计算底价,卖单价格<底价时自动上调,价格>底价8倍时拒绝
- **5. 挂牌限制检查**: `plugins/xiuxian_game/economy/market.py:302-304` - 调用TradeRecord.can_list_item检查8小时内购买的商品不能挂牌
- **6. 资源冻结**: `plugins/xiuxian_game/economy/market.py:299-316` - 卖单调用ItemInstance.consume_item扣除物品,买单扣除相应金币
- **7. 订单创建**: `plugins/xiuxian_game/economy/market.py:319-327` - 创建MarketOrder记录,设置side(BUY/SELL)、item_id、price、quantity
- **8. 自动撮合**: `plugins/xiuxian_game/economy/market.py:332` - 调用_try_auto_match尝试立即成交
- **9. 结果反馈**: `plugins/xiuxian_game/economy/market.py:336-345` - 返回订单ID、成交信息、底价吸附提示

### 3.2 自动撮合流程

- **1. 对手订单查询**: `plugins/xiuxian_game/economy/market.py:893-910` - 买单查找价格≤买价的卖单(升序排列),卖单查找价格≥卖价的买单(降序排列)
- **2. 遍历撮合**: `plugins/xiuxian_game/economy/market.py:919-923` - 逐个处理对手订单,计算成交数量 = min(当前单剩余,对手单数量)
- **3. 成交价确定**: `plugins/xiuxian_game/economy/market.py:923` - 成交价 = 对手价(优先成交更有利的价格)
- **4. 物品转移**: `plugins/xiuxian_game/economy/market.py:933-953` - 装备交易调用EquipmentTradeService.transfer_equipment,普通物品调用ItemInstance.add_item(检查背包空间)
- **5. 税收计算**: `plugins/xiuxian_game/economy/market.py:956-957` - 调用calculate_transaction_tax计算阶梯税(0-20%)
- **6. 金币结算**: `plugins/xiuxian_game/economy/market.py:959-963` - 卖家获得(交易额 - 税收)金币,更新财富成就统计
- **7. 对手单更新**: `plugins/xiuxian_game/economy/market.py:966-968` - 对手单数量 -= 成交数量,完全成交后删除
- **8. 退款处理**: `plugins/xiuxian_game/economy/market.py:986-990` - 买单多冻结的金币退还给玩家
- **9. 中断处理**: `plugins/xiuxian_game/economy/market.py:949-953` - 买家背包空间不足时停止撮合,返回警告信息

### 3.3 订单撤牌流程

- **1. 订单查询**: `plugins/xiuxian_game/economy/market.py:544-546` - 根据订单ID查找MarketOrder,验证所有权(player_id匹配)
- **2. 卖单撤牌**: `plugins/xiuxian_game/economy/market.py:548-563` - 装备交易调用EquipmentTradeService.unfreeze_equipment解冻,普通物品调用ItemInstance.add_item退回背包
- **3. 买单撤牌**: `plugins/xiuxian_game/economy/market.py:565-567` - 退还冻结的金币(价格 × 数量)
- **4. 订单删除**: `plugins/xiuxian_game/economy/market.py:569` - 从数据库删除MarketOrder记录
- **5. 结果反馈**: `plugins/xiuxian_game/economy/market.py:572` - 返回撤牌成功消息

### 3.4 装备交易特殊流程

- **1. 装备选择**: `plugins/xiuxian_game/economy/market.py:348-400` - 玩家挂牌装备时,如果有多件同类装备,保存状态并让玩家选择具体实例
- **2. 装备冻结**: `plugins/xiuxian_game/economy/market.py:405-410` - 调用EquipmentTradeService.freeze_equipment,设置extra_attrs["_frozen_for_trade"]=True,防止装备/强化/镶嵌
- **3. 装备底价**: `plugins/xiuxian_game/economy/market.py:417-431` - 调用_compute_equipment_floor_price,基于装备价值范围(升阶加成、宝石价值、耐久度)计算底价
- **4. 订单创建**: `plugins/xiuxian_game/economy/market.py:434-443` - 创建装备订单,设置is_instance_trade=True、item_instance_id、equipment_summary
- **5. 装备转移**: `plugins/xiuxian_game/economy/market.py:933-942` - 成交时调用EquipmentTradeService.transfer_equipment,变更player_id,清除冻结标记
- **6. 摘要生成**: `plugins/xiuxian_game/economy/market.py:413` - 调用EquipmentTradeService.generate_equipment_summary生成装备显示文本(如: ⭐+5阶 [💎2/3] 耐久160/160)

## 4. 设计原理

**订单簿模式 vs 拍卖行**: 采用订单簿而非传统拍卖行,挂单即可能成交,无需等待拍卖结束。优势是流动性高、操作简单;劣势是急售困难(无快速成交选项),未来可考虑引入"市价单"机制。

**价格优先、时间优先**: 买单按价格降序排列(高价优先),卖单按价格升序排列(低价优先),同价格按创建时间升序排列(早挂单优先)。这确保了市场公平性和价格发现效率。

**底价自动吸附**: 卖单价格低于系统计算的底价时,自动上调到底价,防止玩家误挂低价或恶意压价。买单不设底价吸附,允许玩家高价求购(如急需材料)。

**装备冻结机制**: 装备挂牌时设置_frozen_for_trade标记,禁止装备、强化、镶嵌宝石、销毁操作,防止同时交易和使用的竞态条件。撤牌或成交后自动解冻。

**原子性事务保证**: 所有交易操作(物品转移、金币结算、订单更新)在单个数据库事务中完成,失败时自动回滚,确保交易一致性和安全性。

**背包空间检查**: 买入前检查买家背包空间,空间不足时停止撮合。这避免了物品丢失或交易卡死的问题。装备交易占用1个背包位,普通物品按数量占用。

**税收激励设计**: 阶梯税收(免税→5%→10%→15%→20%)鼓励小额交易,抑制大额交易。税收从卖家收入扣除,买家支付固定金额,简化了价格计算。
