from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageKeyboard,MessageArk
from nonebot.adapters.qq.models import MessageArkKv, MessageArk, MessageArkObj, MessageArkObjKv
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
import os
from ..models import Player
from ..models.inventory import ItemInstance, ItemType
from ..models.db import safe_session
from ..config import config
from ..utils import bypass_urls

# 生成经验表
generate_exp_table_cmd = on_command("生成经验表", priority=4, block=True, permission=SUPERUSER)
@generate_exp_table_cmd.handle()
async def handle_generate_exp_table(event: MessageEvent, args: Message = CommandArg()):
    from ..utils import generate_exp_table
    await generate_exp_table_cmd.finish(await generate_exp_table())


# 帮助
help_cmd = on_command("帮助", aliases={"help","菜单"}, priority=5, block=True)
@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版帮助菜单 - 展示所有游戏系统
    """
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "━━━━━━━━━━━━━\n"
        "📚 发送系统名查看详细帮助\n"
        "\n"
        "🎮 核心玩法系统：\n"
        "【修炼系统】 修炼、闭关、突破、加点\n"
        "【玩家系统】 面板、排行榜、成就\n"
        "【战斗系统】 切磋、攻击、世界BOSS\n"
        "【装备系统】 穿戴、锻造、升阶、镶嵌\n"
        "\n"
        "🎒 物品管理：\n"
        "【背包系统】 物品管理、使用道具\n"
        "【炼丹系统】 炼制丹药、提升属性\n"
        "【钓鱼系统】 钓鱼玩法、鱼栏管理\n"
        "\n"
        "🗺️ 探索冒险：\n"
        "【探索系统】 地图导航、NPC交互\n"
        "【副本系统】 无限诡域、材料获取\n"
        "【阴宅系统】 购买阴宅、修炼加成\n"
        "\n"
        "💰 经济交易：\n"
        "【经济系统】 跑商、银行、理财\n"
        "【交易系统】 玩家交易、挂牌市场\n"
        "【投资系统】 气运投资、高风险收益\n"
        "【打工系统】 打工赚钱、新手友好\n"
        "\n"
        "👥 社交互动：\n"
        "【社交系统】 送礼、结婚、结义、师徒\n"
        "【公会系统】 创建公会、建筑加成\n"
        "【委托系统】 每日委托、缉邪任务\n"
        "\n"
        "🎲 娱乐休闲：\n"
        "【娱乐系统】 签到、小游戏、互动剧情\n"
        "【抽奖系统】 参与抽奖、获得奖励\n"
        "\n"
        "💳 其他功能：\n"
        "【赞助】 查看月卡权益\n"
        "【账号管理】 多账号切换\n"
        "【完整帮助】 查看所有系统\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "💡 发送【问 你的问题】询问机器人\n"
        "💡 发送/邀请码 邀请好友获得奖励\n"
        "💡 不会玩加频道：https://Pd.qq.Com/s/d0g9cvds4\n"
        "💡 教程：https://Tutorials.Bossjlb.Top\n"
        "💡 官群：962494679"
    )
    await help_cmd.finish(Message(msg))

# 经济系统（整合跑商、银行）
economy_cmd = on_command("经济系统",aliases={"经济帮助","跑商系统","跑商帮助","银行系统","银行帮助"}, block=True, priority=5)
@economy_cmd.handle()
async def handle_economy(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版经济系统帮助
    """
    msg = (
        "✨ 经济系统 ✨\n"
        "管理金币、跑商赚钱、银行理财\n"
        "━━━━━━━━━━━━━\n"
        "💰 银行系统：\n"
        "【存 金额】 存入冥行（不产生利息）\n"
        "【取 金额】 取出存款\n"
        "【余额】 查询存款余额\n"
        "【转账 UID 金额】 银行转账（手续费3%）\n"
        "━━━━━━━━━━━━━\n"
        "🏪 跑商系统：\n"
        "【市集】 查看当前市场商品和价格\n"
        "【购买 物品名 数量】 购买商品\n"
        "【出售 物品名 数量】 出售商品\n"
        "【跑商推荐】 查看盈利路线推荐\n"
        "【市集列表】 查看所有市集坐标\n"
        "【黑市】 查看黑市特殊商品\n"
        "━━━━━━━━━━━━━\n"
        "💎 理财产品：\n"
        "【理财产品】 查看可购买的理财产品\n"
        "【我的理财】 查看持有的理财产品\n"
        "━━━━━━━━━━━━━\n"
        "💡 新手快速赚钱方式：\n"
        "  1. 打工系统 - 稳定收入（60-180金币/次）\n"
        "  2. 跑商系统 - 低买高卖赚差价\n"
        "  3. 副本探索 - 获得材料出售\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 跑商限制：同一地点4小时内只能交易一次\n"
        "💡 跑商推荐会根据市场行情推荐最优路线"
    )
    await economy_cmd.finish(Message(msg))

# 投资系统（独立详细教程）
investment_cmd = on_command("投资系统", aliases={"气运投资", "投资帮助"}, block=True, priority=5)
@investment_cmd.handle()
async def handle_investment(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 气运投资系统 ✨\n"
        "修仙界的气运交易，高风险高收益\n"
        "━━━━━━━━━━━━━\n"
        "📋 基本命令：\n"
        "【投资行情】 查看所有可投资的气运及灵力指数\n"
        "【投资刷新时间】 查看气运价格刷新时间\n"
        "【投资气运 <代码> <数量> [银行]】 投资气运\n"
        "【出售气运 <代码> <数量> [银行]】 出售气运\n"
        "【我的投资】 查看投资情况和灵力预警\n"
        "【投资记录】 查看投资记录\n"
        "【气运事件】 查看市场黑天鹅事件（重大崩盘）\n"
        "━━━━━━━━━━━━━\n"
        "🎮 新手快速入门（3步）：\n"
        "1️⃣ 【投资行情】 看看哪个气运有绿光🟢（灵力充沛）\n"
        "2️⃣ 【投资气运 代码 10】 买10份试试水（建议100金币以内）\n"
        "3️⃣ 等1小时后价格涨了，就【出售气运 代码 10】卖掉赚钱\n"
        "   如果跌了也别慌，可以等等看会不会涨回来\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 重要风险（必看！）：\n"
        "• ⚡ 灵力指数系统：气运消耗过度会\"灵力枯竭\"\n"
        "  - 🟢 绿光（70-100）= 灵力充沛，可投资\n"
        "  - 🟡 黄光（30-69）= 灵力不稳，需谨慎\n"
        "  - 🔴 红光（0-29）= 濒临枯竭，快出手！再跌就完蛋了\n"
        "  - 💀 灵力归零 = 气运消散，你的钱全没了！\n"
        "\n"
        "• 💸 每天要交保管费：每天扣0.1%（1000金币扣1金币）\n"
        "  持有时间越长，扣的钱越多，所以别放太久\n"
        "\n"
        "• 💰 买卖要手续费：买+卖总共1%（100金币扣1金币）\n"
        "\n"
        "• 🌪 黑天鹅事件：每周有15%概率发生突发崩盘\n"
        "  会导致气运暴跌40-50%，健康度-60，无法预测！\n"
        "  发送【气运事件】查看最近发生的重大事件\n"
        "\n"
        "• 🎲 气运变化完全随机：涨跌全看天意，没有\"必赚\"的方法\n"
        "  就像抛硬币，涨和跌的概率差不多\n"
        "━━━━━━━━━━━━━\n"
        "💡 新手防坑指南：\n"
        "• ❌ 别把所有钱投进去！只用你愿意输掉的钱\n"
        "• ❌ 别all in一种气运！多买几种分散风险\n"
        "• ✅ 看到红光🔴（灵力<30）赶紧出手，别心疼\n"
        "• ✅ 赚了就跑，别贪心想赚更多\n"
        "• ✅ 短期玩玩（1-2周）比长期拿着好，避免保管费\n"
        "• ⚠️ 这是高风险玩法，可能血本无归！新手建议先打工赚钱\n"
        "━━━━━━━━━━━━━\n"
        "📖 举个例子：\n"
        "小明有1000金币，投资了10份甲气运（每份10金币）\n"
        "• 情况1：涨到15金币/份，卖掉赚50金币（150-100-手续费）✅\n"
        "• 情况2：跌到5金币/份，灵力变红🔴，赶紧止损\n"
        "  如果不卖继续跌，灵力归零，气运消散，100金币全没了💀\n"
        "━━━━━━━━━━━━━\n"
        "💡 想了解银行存款和跑商赚钱？发送【经济系统】查看"
    )
    await investment_cmd.finish(Message(msg))

# 钓鱼系统
fishing_cmd = on_command("钓鱼系统", aliases={"钓鱼帮助"}, block=True, priority=5)

@fishing_cmd.handle()
async def handle_fishing(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 钓鱼系统帮助 ✨\n"
        "随时随地享受钓鱼乐趣，获得各种珍贵鱼类\n"
        "━━━━━━━━━━━━━\n"
        "🎣 钓鱼操作：\n"
        "【钓鱼】 开始钓鱼（冷却5分钟）\n"
        "【钓鱼状态】 查看当前钓鱼状态和统计\n"
        "【钓鱼记录】 查看个人钓鱼记录\n"
        "【钓鱼概率】 查看各品阶鱼类的钓到概率\n"
        "【钓鱼排行】 查看钓鱼排行榜\n"
        "【钓鱼图鉴】 查看详细钓鱼说明\n"
        "【鱼栏 [页码]】 查看鱼类存量（不占背包）\n"
        "【吃鱼 鱼类名称 数量】 品尝鱼类美味（仅娱乐）\n"
        "【丢弃 鱼类名称 数量】 放生鱼类，获得功德\n"
        "━━━━━━━━━━━━━\n"
        "🐟 鱼类稀有度：\n"
        "⚪ 普通（55%）- 鲤鱼、鲫鱼、草鱼等\n"
        "🟢 优良（28%）- 鲈鱼、桂鱼、黄花鱼等\n"
        "🔵 精品（14%）- 三文鱼、金枪鱼、石斑鱼等\n"
        "🟣 稀有（2.5%）- 中华鲟、龙鱼等\n"
        "🟠 传说（0.5%）- 金龙鱼、凤凰鱼等\n"
        "━━━━━━━━━━━━━\n"
        "📖 图鉴功能：\n"
        "【图鉴 物品名称】 查看物品详细信息\n"
        "【提交物品图片 物品名 图片URL】 为物品提供图片（等级>50）\n"
        "• 玩家可以为没有图片的物品提供图片，共同完善图鉴\n"
        "━━━━━━━━━━━━━\n"
        "💰 鱼类交易：\n"
        "• 可在海洋城市舟山(200,-200)出售给商人\n"
        "• 稀有鱼类价值更高，传说鱼类价值连城\n"
        "• 运气值影响稀有鱼概率和数量\n"
        "• 使用【钓鱼概率】查看你的实际钓到概率\n"
        "━━━━━━━━━━━━━\n"
        "🎒 鱼栏系统：\n"
        "• 鱼类存入专属鱼栏，不占背包空间\n"
        "• 使用【鱼栏】查看所有鱼类存量和总估值\n"
        "• 鱼栏容量无限制，可以尽情钓鱼\n"
        "━━━━━━━━━━━━━\n"
        "⏰ 限制说明：\n"
        "• 每次钓鱼冷却5分钟\n"
        "• 每日钓鱼次数限制50次\n"
        "💡 钓鱼不受地点限制，新手友好"
    )
    await fishing_cmd.finish(Message(msg))

# 炼丹系统
alchemy_cmd = on_command("炼丹系统",aliases={"炼丹帮助"}, priority=4, block=True)

@alchemy_cmd.handle()
async def handle_alchemy(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 炼丹系统帮助 ✨\n"
        "消耗材料，获得丹药，炼丹炉可通过升阶提升成功率\n"
        "炼丹失败时会返还50%材料，自动使用最高阶炼丹炉\n"
        "━━━━━━━━━━━━━\n"
        "【丹方 [页数|关键词]】 查看或搜索炼丹配方\n"
        "【炼丹状态】 查看炼丹状态\n"
        "【炼丹 <丹方序号|名称> <数量>】 自动选择最高阶炼丹炉进行炼丹\n"
        "【收获丹药】 收获炼制完成的丹药\n"
        "━━━━━━━━━━━━━\n"
        "💊 丹药类型说明：\n"
        "• 经验丹：效果随等级提升（基础+等级加成）\n"
        "• 治疗丹：百分比恢复，全程有效\n"
        "• 战斗丹：百分比临时增益，强而短（15-30分钟）\n"
        "• 永久丹：固定值永久提升，每日限量\n"
        "• 洗髓丹：转换3%属性为可分配点数\n"
        "━━━━━━━━━━━━━\n"
        "🔄 洗髓系统：\n"
        "• 洗髓丹可将3%的指定属性转为可分配点\n"
        "• 例：攻击100时，洗髓·力丹转换3点攻击\n"
        "• 转换后使用【加点】指令重新分配\n"
        "• 适合调整属性分配，优化战斗流派\n"
        "━━━━━━━━━━━━━\n"
        "🔥 炼丹炉升阶效果：\n"
        "• +0阶：成功率×1.0，耐久消耗5\n"
        "• +1阶：成功率×1.1，耐久消耗5\n"
        "• +2阶：成功率×1.2，耐久消耗4\n"
        "• +5阶：成功率×1.5，耐久消耗3\n"
        "• +8阶：成功率×1.8，耐久消耗2\n"
        "• +10阶：成功率×2.0，耐久消耗2（满级）\n"
        "💡 炼丹炉可通过【升阶】系统提升等级"
    )
    await alchemy_cmd.finish(Message(msg))

# 战斗系统
battle_cmd = on_command("战斗系统",aliases={"战斗帮助","PVP系统"}, priority=4, block=True)
@battle_cmd.handle()
async def handle_battle(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版战斗系统帮助
    """
    msg = (
        "✨ 战斗系统 ✨\n"
        "玩家对战、NPC战斗、世界BOSS挑战\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 玩家对战：\n"
        "【切磋 UID】 友好切磋，无损失\n"
        "【攻击 UID/NPC】 攻击目标\n"
        "  • 城镇安全区：只能友好切磋\n"
        "  • 荒野/诡域：真实死斗，死亡掉落\n"
        "━━━━━━━━━━━━━\n"
        "🌟 世界BOSS：\n"
        "【世界BOSS】 查看BOSS信息和血量\n"
        "【讨伐BOSS】 攻击BOSS（每日3次）\n"
        "【BOSS排行】 查看伤害排行榜\n"
        "  • 每日重置挑战次数\n"
        "  • 击杀BOSS全服玩家获得奖励\n"
        "  • 根据伤害排名获得额外奖励\n"
        "━━━━━━━━━━━━━\n"
        "📊 战力相关：\n"
        "【战力】 查看自身完整属性\n"
        "【战力说明】 查看各项战斗属性的作用\n"
        "【死斗日志】 查看真实战斗记录\n"
        "【加点帮助】 查看基本属性加点指南\n"
        "━━━━━━━━━━━━━\n"
        "💡 战斗属性说明：\n"
        "  • 攻击/防御：基础伤害和减伤\n"
        "  • 暴击率/暴击力：暴击概率和伤害倍率\n"
        "  • 连击率：触发连击（2-4次）的概率\n"
        "  • 反击率：受到攻击时反击的概率\n"
        "  • 闪避率：躲避攻击的概率\n"
        "  • 命中率：命中敌人的概率\n"
        "  • 敏捷：影响先手顺序\n"
        "━━━━━━━━━━━━━\n"
        "💡 敏捷高的玩家更容易先手\n"
        "💡 装备效果和战斗丹药可大幅提升战力"
    )
    await battle_cmd.finish(Message(msg))

# 打工系统
part_time_job_cmd = on_command("打工系统", aliases={"打工帮助"}, priority=4, block=True)
@part_time_job_cmd.handle()
async def handle_part_time_job(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 打工系统帮助 ✨\n"
        "新手赚钱玩法，快节奏高回报\n"
        "━━━━━━━━━━━━━\n"
        "📍 基本流程：\n"
        "1. 前往工作地点坐标\n"
        "2. 【打工】查看可用工作\n"
        "3. 【打工 工作名称】开始工作\n"
        "4. 【收工】获得奖励\n"
        "━━━━━━━━━━━━━\n"
        "🏢 工作地点：\n"
        "• 上京商业中心 (0,0) - 服务业\n"
        "• 荔湾镇工业区 (120,200) - 体力工作\n"
        "• 郸城娱乐街区 (120,120) - 轻松工作\n"
        "• 东郊物流中心 (390,50) - 物流工作\n"
        "━━━━━━━━━━━━━\n"
        "📋 相关命令：\n"
        "【打工】 查看当前位置工作\n"
        "【打工 <工作名>】 开始工作\n"
        "【收工】 完成工作获得奖励\n"
        "【工作状态】 查看当前工作状态\n"
        "【工作地点】 查看所有工作地点\n"
        "【打工记录】 查看打工历史\n"
        "【打工统计】 查看打工数据\n"
        "━━━━━━━━━━━━━\n"
        "💰 工作时长：2-3分钟\n"
        "💰 工资：60-180金币/次 + 特殊事件奖励\n"
        "⏰ 限制：每小时最多10次，每次间隔1分钟\n"
        "💡 连续打工可获得额外奖励，运气值影响收入"
    )
    await part_time_job_cmd.finish(Message(msg))

# 玩家系统
player_cmd = on_command("玩家系统", priority=4, block=True)
@player_cmd.handle()
async def handle_player(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 玩家系统帮助 ✨\n"
        "查看玩家信息、排行榜，注册角色和改名\n"
        "━━━━━━━━━━━━━\n"
        "【面板 [UID]】 查看指定玩家面板\n"
        "【完整面板 [UID]】 查看完整面板（含战力+注册时间）\n"
        "【排行榜】 查看所有排行榜总览\n"
        "【财富榜】 查看财富榜（含现金+存款+投资）\n"
        "【修为榜】 查看修为榜\n"
        "【幸运榜】 查看幸运榜\n"
        "【探索榜】 查看探索榜\n"
        "【敏捷榜】 查看敏捷榜\n"
        "【小游戏榜】 查看小游戏积分排行\n"
        "【魅力榜】 查看魅力值排行(通过收礼获得)\n"
        "【战力】 查看自身完整属性\n"
        "【战力说明】 查看各项战斗属性的作用\n"
        "【加点帮助】 查看基本属性加点指南\n"
        "━━━━━━━━━━━━━\n"
        "🏆 成就系统：\n"
        "【成就】或【成就列表】 查看所有成就（第1页）\n"
        "【成就 <页码>】 查看指定页成就（每页15个）\n"
        "【成就 <成就名>】 查看成就详情\n"
        "━━━━━━━━━━━━━\n"
        "🎯 成就类型：\n"
        "• 基础成就：修炼、战斗、探索等新手引导成就\n"
        "• 高难度成就：百战不殆、千人斩、财富自由等挑战性成就\n"
        "• 特殊成就：周年纪念、终身成就等限定成就\n"
        "━━━━━━━━━━━━━\n"
        "📊 成就分类：\n"
        "• 修炼系列：修炼次数相关成就\n"
        "• 成长系列：等级提升相关成就\n"
        "• 战斗系列：战斗胜利和击杀数相关成就\n"
        "• 装备系列：装备获取和强化相关成就\n"
        "• 财富系列：金币累计相关成就\n"
        "• 探索系列：地点探索相关成就\n"
        "• 忠诚系列：登录天数相关成就\n"
        "━━━━━━━━━━━━━\n"
        "💰 成就奖励：\n"
        "• 金币：直接获得金币奖励\n"
        "• 怨炁：获得大量经验值\n"
        "• 属性点：自由分配的属性点\n"
        "• 奖励随成就难度递增，高难度成就奖励丰厚\n"
        "━━━━━━━━━━━━━\n"
        "✨ 自动触发：\n"
        "• 修炼、战斗、探索等行为自动记录统计\n"
        "• 达成条件后自动解锁并发放奖励\n"
        "• 在诡域击杀怪物也会计入成就统计\n"
        "• 🎂 老玩家专属周年成就等你解锁！\n"
        "━━━━━━━━━━━━━\n"
        "【注册】 注册角色\n"
        "【改名 <新名字>】 改名\n"
        "【改性别 <男/女>】 修改角色性别\n"
        "【邀请码】 查看我的邀请码和分级奖励说明\n"
        "【绑定邀请码 <邀请码>】 绑定好友邀请码获得奖励\n"
        "【邀请状态】 查看邀请奖励发放状态\n"
        "━━━━━━━━━━━━━\n"
        "💡 新手注册：发送【注册】，系统会引导你输入昵称\n"
        "💡 快速注册：发送【注册 昵称】，如：注册 道爷\n"
        "💡 不知道怎么加点？发送【加点帮助】查看详细指南"
    )
    await player_cmd.finish(Message(msg))

# 装备系统
equip_cmd = on_command("装备系统", aliases={"装备帮助"}, priority=4, block=True, force_whitespace=True)
@equip_cmd.handle()
async def handle_equip(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 装备系统帮助 ✨\n"
        "穿戴装备提升属性，锻造、升阶、镶嵌强化装备\n"
        "━━━━━━━━━━━━━\n"
        "🎽 基础功能：\n"
        "【装备栏 [页码]】 查看装备（显示编号）\n"
        "【装备详情 <编号/名称>】 查看详细信息\n"
        "【装备 <编号/名称>】 穿戴装备\n"
        "【卸下 <编号/名称>】 卸下装备\n"
        "【一键卸下】 卸下全部装备\n"
        "【修理 <编号/名称> [金币:怨念]】 修理装备\n"
        "━━━━━━━━━━━━━\n"
        "🛠️ 耐久与损坏：\n"
        "• 装备耐久降至0时会自动卸下且无法穿戴，需修理后恢复\n"
        "• 战斗/副本/扫荡均会消耗耐久\n"
        "━━━━━━━━━━━━━\n"
        "⚒️ 锻造系统：\n"
        "【锻造列表】 查看全部装备及可锻造城镇\n"
        "【配方 <装备名>】 查看锻造配方\n"
        "【锻造 <装备名>】 锻造装备（需在工坊≤3格）\n"
        "💡 诡域中无法锻造，需返回现实世界\n"
        "━━━━━━━━━━━━━\n"
        "⭐ 升阶系统：\n"
        "【升阶信息 <编号/名称>】 查看升阶需求和成功率\n"
        "【升阶 <编号/名称>】 装备合成升阶\n"
        "【升阶 <编号/名称> 稳定水晶】 提升成功率\n"
        "【升阶列表】 查看可升阶装备\n"
        "💡 1-3阶成功率95%-85%，7-10阶60%-25%\n"
        "━━━━━━━━━━━━━\n"
        "💎 镶嵌系统：\n"
        "【孔位 <编号/名称>】 查看孔位信息\n"
        "【镶嵌 <编号/名称> <孔位> <镶嵌物>】 镶嵌宝石/符文\n"
        "【拆卸 <编号/名称> <孔位>】 拆卸镶嵌物（有风险）\n"
        "【镶嵌物品】 查看可镶嵌物品列表\n"
        "【镶嵌物升级 <镶嵌物名>】 查看镶嵌物升级信息\n"
        "【合成镶嵌物 <镶嵌物名>】 升级合成镶嵌物\n"
        "【可升级镶嵌物】 查看所有可升级的镶嵌物\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 总部商店：\n"
        "【总部商店】北极风雪镇(-5,390)\n"
        "【总部兑换 <物品> [数量]】 用积分兑换材料\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 最多穿戴4件装备，不能重复穿戴"
    )
    await equip_cmd.finish(Message(msg))

# 修炼系统
xiu_lian_cmd = on_command("修炼系统", aliases={"修炼帮助"}, priority=4, block=True)

@xiu_lian_cmd.handle()
async def handle_xiu_lian(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版修炼系统帮助
    """
    msg = (
        "✨ 修炼系统 ✨\n"
        "突破境界获得属性点，献祭材料获取怨念保驾护航\n"
        "━━━━━━━━━━━━━\n"
        "🧘 修炼相关：\n"
        "【修炼】 获取经验，冷却5分钟\n"
        "【闭关】 挂机升级，效率减半\n"
        "  • 基础闭关：9小时\n"
        "  • 高级月卡：12小时\n"
        "【出关】 出关后可继续修炼\n"
        "━━━━━━━━━━━━━\n"
        "⚡ 突破系统：\n"
        "【突破】 突破境界，提升等级上限\n"
        "  • 30级前：100%成功\n"
        "  • 30级后：成功率递减（最低10%）\n"
        "  • 失败保留70-80%修为\n"
        "【突破 怨念】 消耗怨念确保突破成功\n"
        "【突破 棺材钉】 使用棺材钉确保成功\n"
        "━━━━━━━━━━━━━\n"
        "📊 属性加点：\n"
        "【加点 属性 点数】 分配属性点\n"
        "  可选属性：力量、体质、敏捷、智力、幸运\n"
        "【加点帮助】 查看详细加点指南\n"
        "━━━━━━━━━━━━━\n"
        "💀 怨念系统：\n"
        "【献祭 材料名 数量】 献祭材料获取怨念值\n"
        "  • 白色材料：10怨念/个\n"
        "  • 绿色材料：50怨念/个\n"
        "  • 蓝色材料：200怨念/个\n"
        "  • 紫色材料：800怨念/个\n"
        "  • 橙色材料：3200怨念/个\n"
        "━━━━━━━━━━━━━\n"
        "📈 查询相关：\n"
        "【面板】 查看角色面板信息\n"
        "【战力】 查看完整战斗属性\n"
        "━━━━━━━━━━━━━\n"
        "💡 提示：\n"
        "  • 突破失败会损失部分修为\n"
        "  • 使用怨念或棺材钉可确保成功\n"
        "  • 阴宅、月卡、公会建筑可提升修炼效率\n"
        "  • 发送【加点帮助】查看详细指南"
    )
    await xiu_lian_cmd.finish(Message(msg))


# 阴宅系统
mansion_cmd = on_command("阴宅系统", aliases={"阴宅帮助"}, priority=4, block=True)

@mansion_cmd.handle()
async def handle_mansion(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 阴宅系统帮助 ✨\n"
        "拥有阴宅可大幅提升修炼效率，支持其他玩家付费使用\n"
        "━━━━━━━━━━━━━\n"
        "【阴宅】 查看阴宅状态和位置信息\n"
        "【购买阴宅】 在当前位置花费1000万金币购买1级阴宅\n"
        "【升级阴宅】 在阴宅位置消耗金币升级等级\n"
        "【迁移阴宅】 将阴宅迁移到当前位置\n"
        "【设置阴宅费用 <金币数>】 设置其他玩家使用费用\n"
        "【切换阴宅权限】 允许/禁止其他玩家使用\n"
        "【切换阴宅付费意愿】 设置是否愿意付费使用他人阴宅\n"
        "━━━━━━━━━━━━━\n"
        "💡 阴宅等级效率加成：\n"
        "   每级+9%效率，最高30级\n"
        "   1级：+20%  5级：+56%  10级：+101%\n"
        "   20级：+191%  30级：+281%\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 不能在城镇市集20格半径范围内建造\n"
        "💡 阴宅可以通过迁移功能移动到新位置\n"
        "💡 在阴宅位置修炼/闭关可享受加成效果\n"
        "💡 其他玩家可付费使用你的阴宅获得加成\n"
        "💡 使用费用根据阴宅等级设定最低要求\n"
        "💡 升级阴宅必须在阴宅位置进行\n"
        "💡 使用【观察】命令可查看当前位置的阴宅信息\n"
        "━━━━━━━━━━━━━\n"
        "⚙️ 阴宅付费意愿设置：\n"
        "   • 默认愿意：在他人阴宅修炼会自动支付费用\n"
        "   • 设为不愿意：在他人阴宅修炼不会扣费，但无法享受加成\n"
        "━━━━━━━━━━━━━\n"
        "🚚 阴宅迁移功能：\n"
        "   • 迁移费用：当前等级升级费用的50%\n"
        "   • 使用方法：移动到目标位置后使用【迁移阴宅】命令\n"
    )
    await mansion_cmd.finish(Message(msg))


# 娱乐系统
entertainment_cmd = on_command("娱乐系统", aliases={"娱乐帮助"}, priority=4, block=True)

@entertainment_cmd.handle()
async def handle_entertainment(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 娱乐系统 ✨\n"
        "签到、小游戏、互动剧情等休闲玩法\n"
        "━━━━━━━━━━━━━\n"
        "🎯 日常活动：\n"
        "【签到】 每日签到，获取奖励\n"
        "【月卡】 查看月卡状态和权益\n"
        "【抽签 [你的问题]】 中国传统诸葛灵签，显示卦象、签诗、解签\n"
        "【摸鱼日历】 获取今日摸鱼日历和日报图片\n"
        "【每日一言】 获取励志名言警句\n"
        "【今天吃什么】 获取随机食谱推荐，含食材和制作步骤\n"
        "━━━━━━━━━━━━━\n"
        "🎮 小游戏：\n"
        "【恶魔轮盘帮助】 PVP对战赌博游戏（3%税收）\n"
        "【试炼列表】 查看可用的互动剧情\n"
        "━━━━━━━━━━━━━\n"
        "💳 月卡权益：\n"
        "• 修炼闭关效率提升\n"
        "• 闭关时长增加\n"
        "• 背包扩容\n"
        "• 签到获得月卡宝箱\n"
        "• 一键献祭、一键修复等便捷功能\n"
        "━━━━━━━━━━━━━\n"
        "📱 发送【赞助】查看月卡购买方式"
    )
    await entertainment_cmd.finish(Message(msg))

# 背包系统
bag_cmd = on_command("背包系统", aliases={"背包帮助"}, priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版背包系统帮助
    """
    msg = (
        "✨ 背包系统 ✨\n"
        "管理物品，使用道具，查看图鉴\n"
        "━━━━━━━━━━━━━\n"
        "🎒 背包管理：\n"
        "【背包】 查看所有物品\n"
        "【背包 类别】 查看指定类别物品\n"
        "  可选类别：消耗品、材料、商品、丹药、装备、宝石、礼物\n"
        "【整理背包】 自动整理背包空间\n"
        "━━━━━━━━━━━━━\n"
        "💊 物品使用：\n"
        "【使用 物品名 数量】 使用消耗品/丹药\n"
        "  示例：使用 回春散 1\n"
        "【一键嗑药】 自动使用治疗药品至满血满蓝\n"
        "【耐药性】 查看丹药每日使用限制\n"
        "━━━━━━━━━━━━━\n"
        "📖 图鉴系统：\n"
        "【图鉴】 查看已收集的物品图鉴\n"
        "【图鉴 物品名】 查看物品详细信息\n"
        "【提交物品图片 物品名 图片URL】 提交物品图片（需等级>50）\n"
        "  • 玩家可以为物品提供图片，共同完善图鉴\n"
        "━━━━━━━━━━━━━\n"
        "📦 背包容量：\n"
        "  • 基础容量：100格\n"
        "  • 基础月卡：+5格\n"
        "  • 高级月卡：+20格\n"
        "  • 永久扩容：每次+5格（可重复购买）\n"
        "━━━━━━━━━━━━━\n"
        "💡 装备不占用背包容量\n"
        "💡 鱼类存入专属鱼栏，不占背包\n"
        "💡 商品类物品仅用于跑商交易\n"
        "💡 部分丹药有耐药性限制，请注意"
    )
    await bag_cmd.finish(Message(msg))

# 探索系统
explore_cmd = on_command("探索系统", aliases={"世界系统","世界帮助","探索帮助"}, priority=4, block=True)
@explore_cmd.handle()
async def handle_explore(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 探索系统帮助 ✨\n"
        "依赖敏捷进行坐标移动，探索世界，与NPC交互\n"
        "━━━━━━━━━━━━━\n"
        "🗺️ 地图导航：\n"
        "【地图】 查看所有重要地点坐标\n"
        "【可视化地图】 生成地图图片\n"
        "【附近地点】 查看附近100格内的地点和阴宅\n"
        "【导航 <地点名>】 快速导航到指定地点\n"
        "【导航 [x] [y]】 坐标导航\n"
        "【查找 <NPC名>】 查询NPC位置\n"
        "【中断导航】 取消当前导航\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 地点和NPC：\n"
        "【观察】 查看当前位置信息（NPC、玩家、阴宅）\n"
        "【地点详情】 查看当前地点的详细信息\n"
        "【交互 <NPC名称>】 与NPC交互（支持关键词）\n"
        "【NPC列表】 查看当前位置的所有NPC\n"
        "━━━━━━━━━━━━━\n"
        "⚒️ 工坊锻造：\n"
        "【锻造列表】 查看全部装备及可锻造城镇\n"
        "【配方 <装备名>】 查看锻造配方\n"
        "【锻造 <装备名>】 在工坊附近锻造（≤3格）\n"
        "【工匠配方一览 <城市名>】 远程查看城市配方\n"
        "━━━━━━━━━━━━━\n"
        "👥 社交功能：\n"
        "【最近活动 <UID>】 查看指定玩家的最近上线时间\n"
        "【附近玩家】 查看附近玩家\n"
        "【留言 <内容>】 在世界留言板发布信息\n"
        "【私信 UID 内容】 给指定修士发送私信\n"
        "【留言板 [世界/私信] [页码]】 查看留言或私信\n"
        "━━━━━━━━━━━━━\n"
        "� 其他：\n"
        "【本周主题】 查看本周都市怪谈主题\n"
        "【更新】 查看最近更新公告\n"
        "━━━━━━━━━━━━━\n"
        "💡 敏捷属性影响移动速度和导航效率"
    )
    await explore_cmd.finish(Message(msg))

# 副本系统
fan_ben_cmd = on_command("副本系统", aliases={"副本帮助"}, priority=4, block=True)
@fan_ben_cmd.handle()
async def handle_fan_ben(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 无限诡域探索系统帮助 ✨\n"
        "探索无限重叠的诡域，每重都是独立的10x10空间\n"
        "━━━━━━━━━━━━━\n"
        "🌀 诡域机制：\n"
        "• 无限重叠：支持无限重扩展，适应任何等级\n"
        "• 逐重解锁：击败当前重诡异解锁更深诡域\n"
        "• 诡异等级：深度×5（±2波动）\n"
        "• 理智消耗：每10重+1点\n"
        "━━━━━━━━━━━━━\n"
        "🚪 基础操作：\n"
        "【进入 N层诡域】 进入指定深度（需逐重解锁）\n"
        "【诡域】 查看探索进度和可访问深度\n"
        "【上|下|左|右】 在诡域内移动\n"
        "【上一层|下一层】 快速切换层级\n"
        "【返回】 穿越回表世界并满状态\n"
        "【探索】 探索当前格子的事件\n"
        "━━━━━━━━━━━━━\n"
        "🎯 诡域特色：\n"
        "• 🔓 逐重解锁：只能进入已探索深度+1\n"
        "• 🎲 材料分层：不同深度掉落不同品质材料\n"
        "• 🔥 特殊属性：200级后诡异拥有暴击、连击、反击、抗暴\n"
        "• 🎁 宝箱奖励：每10、20、30...层可领取宝箱\n"
        "━━━━━━━━━━━━━\n"
        "🔍 其他功能：\n"
        "【俯瞰 N层诡域】 查看诡域完整小地图\n"
        "【使用 扫荡令】 扫荡当前诡域获得经验和材料\n"
        "【探索宝箱】 查看可领取的宝箱\n"
        "【领取宝箱】 一键领取所有宝箱\n"
        "━━━━━━━━━━━━━\n"
        "💡 从第1重开始，逐重击败诡异解锁更深诡域"
    )
    await fan_ben_cmd.finish(Message(msg))

# 交易系统
trade_cmd = on_command("交易系统", aliases={"交易帮助"}, priority=4, block=True)
@trade_cmd.handle()
async def handle_trade(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 交易系统帮助 ✨\n"
        "玩家间自由交易平台，支持物品、装备交易和金币转账\n"
        "━━━━━━━━━━━━━\n"
        "💰 金币转账：\n"
        "【转账 <UID> <金额>】 向其他玩家转账（收取3%手续费）\n"
        "━━━━━━━━━━━━━\n"
        "🎽 物品交易：\n"
        "【交易清单 [页数]】 查看所有在售与求购物品\n"
        "【查牌 <物品名> [页数]】 查看物品买卖价格\n"
        "【挂牌 <出售/收购> <物品名> <单价> [数量]】 挂牌交易\n"
        "【我的挂牌 [页数]】 查看自己的挂牌订单\n"
        "【撤牌 <挂牌ID>】 撤回挂牌\n"
        "【税率】 查看当前阶梯交易税率\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 装备交易：\n"
        "【估价 <编号/名称>】 查看装备价值评估\n"
        "【挂牌 出售 <编号/名称> <价格>】 出售装备实例\n"
        "━━━━━━━━━━━━━\n"
        "🔄 撮合原理：\n"
        "• 买单匹配价格≤买价的卖单，按价格升序成交\n"
        "• 卖单匹配价格≥卖价的买单，按价格降序成交\n"
        "• 成交价格采用对手方价格（价格优先）\n"
        "• 相同价格按时间先后顺序成交\n"
        "━━━━━━━━━━━━━\n"
        "💰 交易税收：\n"
        "• 5000以下：免税\n"
        "• 5001-50000：超出部分3%\n"
        "• 50001-200000：超出部分5%\n"
        "• 200000以上：超出部分8%\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 限制：最多挂6个订单，8小时内购买的物品不能出售\n"
        "💡 转账可用于玩家间金币交易，手续费3%"
    )
    await trade_cmd.finish(Message(msg))

# 公会系统
guild_help_cmd = on_command("公会系统", aliases={"公会帮助"}, priority=4, block=True)

@guild_help_cmd.handle()
async def handle_guild_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 公会系统帮助 ✨\n"
        "加入公会可以获得公会建筑福利\n"
        "━━━━━━━━━━━━━\n"
        "🏰 基础功能：\n"
        "【创建公会 <公会名>】 创建公会（消耗会长委任书）\n"
        "【我的公会】 查看公会信息\n"
        "【公会列表 [页码]】 查看所有公会及其会长信息\n"
        "【公会成员 [页码]】 查看成员列表\n"
        "【加入公会 <公会ID>】 加入公会\n"
        "【退会】 退出公会（清空积分和贡献）\n"
        "━━━━━━━━━━━━━\n"
        "👑 管理功能：\n"
        "【申请列表】 查看待处理申请\n"
        "【[同意/拒绝]入会 <UID>】 审核入会\n"
        "【设置职位 <UID> <职位名>】 设置成员职位\n"
        "【踢出公会 <UID>】 踢出成员\n"
        "【设置基地】 设立公会基地（会长，3级+）\n"
        "【转让会长 <UID>】 转让会长职位\n"
        "【解散公会】 解散公会（会长）\n"
        "━━━━━━━━━━━━━\n"
        "💰 经济系统：\n"
        "【捐献金币 <金额>】 捐献获得积分\n"
        "【公会升级】 升级公会（会长）\n"
        "━━━━━━━━━━━━━\n"
        "🏗️ 建筑系统：\n"
        "【公会建筑】 查看建筑列表和加成\n"
        "【建造 <建筑名>】 建造或升级建筑（会长）\n"
        "【公会传送】 传送到公会基地\n"
        "【公会传送 x y】 在基地时传送到势力范围内坐标\n"
        "━━━━━━━━━━━━━\n"
        "🧪 丹房系统：\n"
        "【公会丹房】 查看丹房产出\n"
        "【兑换丹药 <丹药名称> <数量>】 用积分兑换丹药\n"
        "💡 存储上限=日产量×3,请及时兑换\n"
        "━━━━━━━━━━━━━\n"
        "📋 任务系统：\n"
        "【公会任务】 查看任务列表和进度\n"
        "【完成公会任务】 领取任务奖励\n"
        "【公会任务统计】 查看任务统计\n"
        "━━━━━━━━━━━━━\n"
        "💡 职位体系：会长>副会长>核心成员>普通成员"
    )
    await guild_help_cmd.finish(Message(msg))

# 社交系统
social_help_cmd = on_command("社交系统", aliases={"社交帮助"}, priority=4, block=True)

@social_help_cmd.handle()
async def handle_social_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 社交系统帮助 ✨\n"
        "送礼传情，结伴江湖，建立深厚的羁绊\n"
        "━━━━━━━━━━━━━\n"
        "🎁 礼物系统：\n"
        "【礼物商店】 查看可购买的礼物列表和剩余购买次数\n"
        "【买礼物 <礼物名> [数量]】 购买好感度礼物\n"
        "  示例: 买礼物 红玫瑰 10\n"
        "  • 礼物有不同品质,价格和好感度加成不同\n"
        "  • 白色品质便宜(日限20),红色品质效果最强(日限1)\n"
        "  • 每种礼物每日有购买数量限制,品质越高限制越严格\n"
        "  • 商店会显示每种礼物的今日剩余购买次数\n"
        "【赠礼 UID 礼物名 [数量]】 赠送好感度礼物(远程,消耗型)\n"
        "  示例: 赠礼 123 红玫瑰 10\n"
        "  • 好感度礼物会被消耗,转化为好感度和魅力值\n"
        "  • 每人对另一人每天最多获得500好感度\n"
        "  • 好感度上限10000,达到5000即可结婚/结义\n"
        "【转移 UID 物品名 [数量]】 当面转移物品\n"
        "  示例: 转移 456 回春散 5\n"
        "  示例: 转移 123 白骨护甲 1\n"
        "  • 必须在同一地点,物品实际转移到对方背包\n"
        "  • 不能转移跑商商品(请使用市场交易)\n"
        "  • 可以转移材料、装备、好感度礼物(礼物不消耗)\n"
        "  • 转移装备时如有多件同名装备,会显示列表供选择\n"
        "  • 装备显示升阶、耐久、宝石等详细属性,确保转移正确装备\n"
        "【送礼记录】 查看送礼历史\n"
        "【收礼记录】 查看收礼历史\n"
        "【好感度 [UID]】 查看与指定玩家的好感度\n"
        "【好感度】 不带参数查看所有好感度记录\n"
        "【魅力榜】 查看全服魅力值排行榜\n"
        "【社交统计】 查看社交系统统计信息\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "== 查询指令(随时随地) ==\n"
        "【师徒信息】 查看师徒关系\n"
        "【婚姻信息】 查看婚姻状态\n"
        "【结义信息】 查看结义关系\n"
        "【好感度 UID】 查看与某人的好感度\n"
        "\n"
        "== 变更操作(需前往上京0,0) ==\n"
        "\n"
        "💒 结婚系统 - 找月老\n"
        "【交互 月老 结婚 UID】 与心爱的人结为夫妻\n"
        "  • 需要双方好感度5000\n"
        "  • 双方必须在上京(0,0)\n"
        "【交互 月老 离婚】 单方面离婚(10万金币)\n"
        "\n"
        "🤝 结义系统 - 找结义使者\n"
        "【交互 结义使者 结义 UID1 UID2...】 与兄弟结义(2-4人)\n"
        "  • 每两人之间需要5000好感度\n"
        "  • 所有人必须在上京(0,0)\n"
        "【交互 结义使者 断义】 解除所有结义关系\n"
        "\n"
        "👨‍🏫 师徒系统 - 找师徒使者\n"
        "【拜师申请流程】\n"
        "【交互 师徒使者 拜师 UID】 向某玩家发起拜师申请\n"
        "  • 徒弟主动申请,师父确认收徒\n"
        "  • 需注册满24小时,对方需境界高于你50级或转数更高\n"
        "【交互 师徒使者 拜师申请】 查看收到的拜师申请列表\n"
        "【交互 师徒使者 同意拜师 UID】 同意某人的拜师申请\n"
        "【交互 师徒使者 拒绝拜师 UID】 拒绝申请(对方24小时冷却)\n"
        "【交互 师徒使者 撤销拜师 UID】 撤销自己发出的申请\n"
        "\n"
        "【师父功能】\n"
        "【交互 师徒使者 出师 UID】 让徒弟正常出师(3天冷却)\n"
        "【交互 师徒使者 逐出 UID】 将徒弟逐出师门(3天冷却)\n"
        "\n"
        "【徒弟功能】\n"
        "【交互 师徒使者 叛师】 主动叛离师门(属性惩罚,7天冷却)\n"
        "\n"
        "【其他】\n"
        "【交互 师徒使者 购买徒弟位】 500香火扩展1个徒弟位\n"
        "【交互 师徒使者 查询】 查看师徒状况\n"
        "香火获取：徒弟升级时师父获得香火\n"
        "⚠️ 徒弟一转后升级不再贡献香火，建议让其出师\n"
        "注意：每个徒弟使修炼效率-1%\n"
        "注意：拜师申请7天后自动过期\n"
        "\n"
        "💝 好感度提升\n"
        "【赠礼 UID 礼物名】 送礼增加好感度\n"
        "  • 每天对同一人上限500好感度\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "💬 NPC对话系统：\n"
        "【交互 <NPC名字> [对话内容]】 与NPC进行对话\n"
        "【对话历史 <NPC名字>】 查看与NPC的对话历史\n"
        "【观察】 查看当前位置的所有NPC\n"
        "\n"
        "💬 留言板系统：\n"
        "【留言 <内容>】 发布世界留言\n"
        "【私信 <UID> <内容>】 给指定玩家发送私信\n"
        "【留言板】 查看世界留言板\n"
        "【留言板 私信】 查看私信箱\n"
        "💡 需要达到10级才能发言（防止恶意刷屏）\n"
        "\n"
        "🏆 排行榜：\n"
        "【魅力榜】 查看全服魅力值排行榜\n"
        "【社交统计】 查看社交系统统计信息"
    )
    await social_help_cmd.finish(Message(msg))

# 每日任务系统
daily_task_help_cmd = on_command("委托系统", aliases={"任务系统", "委托帮助"}, priority=4, block=True)

@daily_task_help_cmd.handle()
async def handle_daily_task_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 委托系统帮助 ✨\n"
        "大都会缉邪司每日颁发退邪委托，以恶鬼身，行菩萨事\n"
        "━━━━━━━━━━━━━\n"
        "📋 基础功能：\n"
        "【每日委托】 查看今日所有委托详情\n"
        "【接取委托 <编号>】 接取指定委托\n"
        "【完成委托】 在目标位置完成委托\n"
        "【刷新委托】 生成新委托（每日最多3个）\n"
        "【委托统计】 查看完成统计\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 任务流程：\n"
        "1️⃣ 【每日委托】查看委托\n"
        "2️⃣ 【接取委托 编号】接取任务\n"
        "3️⃣ 导航到任务坐标位置\n"
        "4️⃣ 【观察】查看鬼怪NPC\n"
        "5️⃣ 【攻击 鬼怪名字】击杀目标\n"
        "6️⃣ 【完成委托】领取奖励\n"
        "━━━━━━━━━━━━━\n"
        "💰 奖励：经验、金币、公会积分和经验\n"
        "🎭 任务类型：鬼怪消除、笔仙案件、邪修蛊惑等\n"
        "👻 可与其他玩家合作击杀鬼怪\n"
        "📅 每日最多接取3个委托，次日过期\n"
        "━━━━━━━━━━━━━\n"
        "🎯 智能匹配（已优化）：\n"
        "• 遇到重名NPC时，系统自动优先匹配你的任务目标\n"
        "• 无需担心攻击到其他玩家的委托NPC"
    )
    await daily_task_help_cmd.finish(Message(msg))

# 备份系统
backup_help_cmd = on_command("备份系统", aliases={"备份帮助"}, priority=4, block=True)

@backup_help_cmd.handle()
async def handle_backup_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 数据库备份系统帮助 ✨\n"
        "自动备份游戏数据，确保数据安全（仅限超级用户）\n"
        "━━━━━━━━━━━━━\n"
        "🔄 自动备份：每小时自动执行一次\n"
        "📦 保留策略：只保留最近3个备份文件\n"
        "📁 备份位置：项目根目录\n"
        "\n"
        "🛠️ 管理命令（超级用户专用）：\n"
        "【手动备份】 立即创建数据库备份\n"
        "【备份状态】 查看备份文件列表和状态\n"
        "【恢复备份 <文件名>】 从指定备份恢复数据库\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 恢复操作具有破坏性，请谨慎使用！\n"
        "💡 备份文件命名格式：game_backup_YYYYMMDD_HHMMSS.db"
    )
    await backup_help_cmd.finish(Message(msg))

# 抽奖系统
lottery_help_cmd = on_command("抽奖系统", aliases={"抽奖帮助"}, priority=4, block=True)

@lottery_help_cmd.handle()
async def handle_lottery_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 抽奖系统帮助 ✨\n"
        "管理员发起，玩家参与\n"
        "━━━━━━━━━━━━━\n"
        "👥 玩家指令：\n"
        "【参与抽奖 <抽奖ID>】 参与指定抽奖活动\n"
        "【抽奖详情 <抽奖ID>】 查看抽奖详情和中奖名单\n"
        "【我的抽奖】 查看我参与的抽奖记录\n"
        "━━━━━━━━━━━━━\n"
        "🔧 管理员指令：\n"
        "【发起抽奖 <物品名/金币> <中奖人数> <每人数量> [最低等级 [最高等级]] [-描述]】\n"
        "  发起抽奖活动，奖品从背包扣除，可限制参与等级范围，可添加活动描述\n"
        "【开奖 <抽奖ID>】 进行开奖并发放奖品\n"
        "【取消抽奖 <抽奖ID>】 取消抽奖并退还奖品\n"
        "━━━━━━━━━━━━━\n"
        "📝 说明：\n"
        "• 发起抽奖时会从管理员背包扣除奖品\n"
        "• 可设置最低等级要求，防止小号参与\n"
        "• 可添加活动描述，用 - 开头，例如：-新年特别活动\n"
        "• 参与人数少于中奖人数时，全部参与者中奖\n"
        "• 参与人数多于中奖人数时，随机抽取中奖者\n"
        "• 发起人不能参与自己发起的抽奖\n"
        "━━━━━━━━━━━━━\n"
        "💡 示例：\n"
        "发起抽奖 棺材钉 10 10\n"
        "发起抽奖 金币 5 1000 50 120\n"
        "发起抽奖 棺材钉 5 20 -新年福利活动\n"
        "参与抽奖 1\n"
        "开奖 1"
    )
    await lottery_help_cmd.finish(Message(msg))

# 管理员系统
admin_help_cmd = on_command("管理员系统", aliases={"管理员帮助", "管理指令"}, priority=4, block=True, permission=SUPERUSER)

@admin_help_cmd.handle()
async def handle_admin_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 管理员系统帮助 ✨\n"
        "超级管理员专用指令\n"
        "━━━━━━━━━━━━━\n"
        "🔧 物品管理：\n"
        "【发物品 <UID> <物品名> [数量]】 给玩家发放物品\n"
        "【发装备 <UID> <装备名> [数量]】 给玩家发放装备\n"
        "【转移物品 <UID1> <UID2> <物品名> <数量>】 转移物品\n"
        "━━━━━━━━━━━━━\n"
        "🎁 抽奖系统：\n"
        "【发起抽奖 <物品名/金币> <中奖人数> <每人数量> [最低等级 [最高等级]]】 发起抽奖活动\n"
        "【开奖 <抽奖ID>】 进行开奖（仅发起人）\n"
        "【抽奖详情 <抽奖ID>】 查看抽奖详情\n"
        "【取消抽奖 <抽奖ID>】 取消抽奖并退还奖品\n"
        "━━━━━━━━━━━━━\n"
        "📊 数据统计：\n"
        "【材料统计】 查看全服材料分布统计\n"
        "【材料详情 <材料名>】 查看指定材料详细分布\n"
        "━━━━━━━━━━━━━\n"
        "🔍 日志管理：\n"
        "【查看报错 [数量]】 查看最近的报错日志（默认10条）\n"
        "【最近报错】 查看最近的报错日志\n"
        "【报错日志】 查看最近的报错日志\n"
        "【最近活动 [数量]】 查看全服最近活动（默认10条，最多50条）\n"
        "━━━━━━━━━━━━━\n"
        "💾 备份管理：\n"
        "【手动备份】 立即创建数据库备份\n"
        "【备份状态】 查看备份文件列表\n"
        "【恢复备份 <文件名>】 从备份恢复数据库\n"
        "━━━━━━━━━━━━━\n"
        "🖼️ 物品图片管理：\n"
        "【设置物品图片 <物品名> <图片URL>】 设置/覆盖物品图片\n"
        "  • 如物品已有图片，仅管理员可覆盖\n"
        "【删除物品图片 <物品名>】 删除物品图片配置\n"
        "【物品图片列表】 查看所有已配置的物品图片\n"
        "💡 配置图片后，玩家使用【图鉴 物品名】可查看带配图的图鉴\n"
        "💡 普通玩家请使用【提交物品图片】为没有图片的物品提供图片\n"
        "━━━━━━━━━━━━━\n"
        "🛠️ 工坊维护：\n"
        "【刷新工坊清单】 覆盖更新所有城镇的锻造清单（超级用户）\n"
        "━━━━━━━━━━━━━\n"
        "💹 气运系统管理：\n"
        "【初始化气运】 初始化气运系统（超级用户）\n"
        "【更新气运价格】 手动刷新所有气运价格（超级用户）\n"
        "【触发黑天鹅】 手动触发黑天鹅事件检查（超级用户）\n"
        "━━━━━━━━━━━━━\n"
        "🚫 封禁管理：\n"
        "【禁言 <UID> [原因] [时长]】 禁言玩家（禁止留言板发言）\n"
        "【解禁 <UID>】 解除禁言\n"
        "【黑名单】 查看当前黑名单\n"
        "【删除留言 <留言ID>】 删除恶意留言\n"
        "【封禁 <UID> [原因] [时长]】 全局封禁玩家（禁止所有游戏操作）\n"
        "【解封 <UID>】 解除全局封禁\n"
        "【封禁列表】 查看所有被封禁的玩家\n"
        "【封禁信息 <UID>】 查看玩家封禁详情\n"
        "💡 时长格式：3d（3天）、24h（24小时）、永久\n"
        "⚠️ 全局封禁将禁止玩家执行所有游戏指令！\n"
        "━━━━━━━━━━━━━\n"
        "🏰 公会管理：\n"
        "【删除公会 <公会ID或名称>】 全面删除公会及其所有数据\n"
        "⚠️ 删除公会操作不可逆，将清空所有成员数据并删除所有相关记录！\n"
        "━━━━━━━━━━━━━\n"
        "🧩 数据迁移 / 修复：\n"
        "【迁移加体比例 [预览|执行|执行 不备份]】 按新规则(1:3)迁移max_hp，并清零装备持久化max_hp，加装后生效\n"

    )
    await admin_help_cmd.finish(Message(msg))

button_test_cmd = on_command("按钮测试", priority=4, block=True)
@button_test_cmd.handle()
async def handle_button_test(event: MessageEvent, args: Message = CommandArg()):
    btn_json = {
        "rows": [
            {
                "buttons": [
                    {
                        "id": "1",
                        "render_data": {
                            "label": "修炼",
                            "visited_label": "",
                            "style": 0
                        },
                        "action": {
                            "type": 2,
                            "permission": {
                                "type": 2
                            },
                            "data": "/修炼",
                            "unsupport_tips": "不支持该操作",
                            "reply": False,
                            "enter": False
                        }
                    }
                ]
            }
        ]
    }
    keyboard = MessageKeyboard(id="102499345_1738493417",content=btn_json)
    await button_test_cmd.finish(MessageSegment.keyboard(keyboard))


# 赞助码
support_cmd = on_command("赞助", aliases={"赞赏","充值","打赏","氪金"}, priority=4, block=True)
@support_cmd.handle()
async def handle_support(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 赞助系统 ✨\n"
        "支持游戏发展，获得作者的回馈\n"
        "━━━━━━━━━━━━━\n"
        "💳 赞助类型：\n"
        "🔸 8.8元 - 基础月卡（30天）\n"
        "   • 修炼闭关效率+20%\n"
        "   • 闭关上限增加至9小时，突破失败损失减少5%\n"
        "   • 背包扩容+5格\n"
        "   • 签到获得月卡宝箱*1，咒抗+5\n"
        "   • 一键献祭、一键修复装备\n"
        "🔸 28.8元 - 高级月卡（30天）\n"
        "   • 修炼闭关效率+50%\n"
        "   • 闭关上限增加至12小时，突破失败损失减少10%\n"
        "   • 背包扩容+20格\n"
        "   • 副本自动采集、装备一键修理、一键献祭\n"
        "   • 签到获得月卡宝箱*3，咒抗+5\n"
        "🔸 5元 - 永久背包扩容+5格\n"
        "   • 永久增加背包容量5格，可重复购买\n"
        "🔸 2元 - 哭坟帽/棺材钉\n"
        "   • 使用后直接获得1w怨念值\n"
        "🔸 后续将推出【诡烛】作为赞助兑换专属货币\n"
        "━━━━━━━━━━━━━\n"
        "📝 注意：支付时请备注UID + 联系方式（可选）\n"
        "💡 发送【月卡】查看当前权益\n"
        "━━━━━━━━━━━━━\n"
        "🙏 感谢您对游戏的支持！"
    )

    # 获取当前文件所在目录
    cur_dir = os.path.dirname(__file__)
    img_path = os.path.join(cur_dir, "../sponsor.jpg")
    img_path = os.path.abspath(img_path)  # 转为绝对路径
    with open(img_path, "rb") as f:
        import base64
        base64_img = base64.b64encode(f.read()).decode("utf-8")

    img = MessageSegment.file_image(base64_img)
    msg = Message(msg).append(img)
    await support_cmd.finish(msg)

# Ark天气测试
ark_weather_test_cmd = on_command("ark测试", priority=4, block=True)
@ark_weather_test_cmd.handle()
async def handle_ark_weather_test(event: MessageEvent, args: Message = CommandArg()):
    # 模拟天气数据
    weather_dict = {
        "result": {
            "citynm": "杭州",
            "weather": "晴",
            "days": "2024-04-01",
            "week": "星期一",
            "temperature": "10~20℃",
            "temperature_curr": "18℃",
            "humidity": "60%"
        }
    }

    async def _create_ark_obj_list(weather_dict):
        return [
            MessageArkObj(obj_kv=[MessageArkObjKv(key="desc", value=f"{weather_dict['result']['citynm']} {weather_dict['result']['weather']} {weather_dict['result']['days']} {weather_dict['result']['week']}")]),
            MessageArkObj(obj_kv=[MessageArkObjKv(key="desc", value=f"当日温度区间：{weather_dict['result']['temperature']}")]),
            MessageArkObj(obj_kv=[MessageArkObjKv(key="desc", value=f"当前温度：{weather_dict['result']['temperature_curr']}")]),
            MessageArkObj(obj_kv=[MessageArkObjKv(key="desc", value=f"当前湿度：{weather_dict['result']['humidity']}")])
        ]

    ark = MessageArk(
        template_id=23,
        kv=[
            MessageArkKv(key="#DESC#", value="🌤️ 天气播报"),
            MessageArkKv(key="#PROMPT#", value="今日天气一览"),
            MessageArkKv(key="#LIST#", obj=await _create_ark_obj_list(weather_dict))
        ]
    )
    await ark_weather_test_cmd.finish(MessageSegment.ark(ark))


give_equip_cmd = on_command("发装备", aliases={"发装", "给装"}, priority=2, block=True,permission=SUPERUSER)

@give_equip_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) < 2 or len(parts) > 3:
        await give_equip_cmd.finish("格式：发装备 UID 装备名称 [数量]")

    uid_str, item_name = parts[0], parts[1]
    qty = 1
    if len(parts) == 3:
        if not parts[2].isdigit() or int(parts[2]) < 1:
            await give_equip_cmd.finish("数量必须为正整数")
        qty = int(parts[2])

    if not uid_str.isdigit():
        await give_equip_cmd.finish("UID 必须为数字")
    target_uid = int(uid_str)

    async with safe_session() as session:
        # 查找目标玩家
        from sqlalchemy import select
        player = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not player:
            await give_equip_cmd.finish(f"❌ 未找到 UID 为 {target_uid} 的玩家")

        # 物品模板校验
        tpl = config.items_config["by_name"].get(item_name)
        if not tpl or tpl.type != ItemType.EQUIPMENT:
            await give_equip_cmd.finish("❌ 装备名称不存在或该物品不是装备")

        try:
            await ItemInstance.add_item(session, player.id, tpl.item_id, quantity=qty)
            await session.commit()
        except ValueError as e:
            await give_equip_cmd.finish(f"❌ 失败：{e}")

        await give_equip_cmd.finish(f"✅ 已给予 UID:{target_uid} 装备 {tpl.name} ✖️{qty}")

# ------------------ 管理员：发物品 ------------------

give_item_cmd = on_command("发物品", aliases={"给物", "发道具"}, priority=2, block=True, permission=SUPERUSER)


@give_item_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：发物品 UID 物品名 [数量]"""
    parts = args.extract_plain_text().strip().split()
    if len(parts) < 2 or len(parts) > 3:
        await give_item_cmd.finish("格式：发物品 UID 物品名称 [数量]")

    uid_str, item_name = parts[0], parts[1]
    qty = 1
    if len(parts) == 3:
        if not parts[2].isdigit() or int(parts[2]) < 1:
            await give_item_cmd.finish("数量必须为正整数")
        qty = int(parts[2])

    if not uid_str.isdigit():
        await give_item_cmd.finish("UID 必须为数字")
    target_uid = int(uid_str)

    async with safe_session() as session:
        from sqlalchemy import select
        player = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not player:
            await give_item_cmd.finish(f"❌ 未找到 UID 为 {target_uid} 的玩家")

        # 查配置
        tpl = config.items_config["by_name"].get(item_name)
        if not tpl:
            await give_item_cmd.finish("❌ 未找到该物品配置")
        if tpl.type == ItemType.EQUIPMENT:
            await give_item_cmd.finish("❌ 该物品为装备，请使用 /发装备 指令")

        try:
            await ItemInstance.add_item(session, player.id, tpl.item_id, quantity=qty)
            await session.commit()
        except ValueError as e:
            await give_item_cmd.finish(f"❌ 失败：{e}")

        await give_item_cmd.finish(f"✅ 已给予 UID:{target_uid} {tpl.name} ✖️{qty}")


# ==================== 账号管理帮助 ====================
account_help_cmd = on_command("账号管理", aliases={"账号帮助", "账号系统"}, block=True, priority=5)

@account_help_cmd.handle()
async def handle_account_help(event: MessageEvent, args: Message = CommandArg()):
    """账号切换系统帮助"""
    msg = (
        "✨ 账号管理系统 ✨\n"
        "支持多账号切换和管理\n"
        "━━━━━━━━━━━━━\n"
        "📋 账号查看：\n"
        "【我的账号】 查看拥有的所有游戏账号\n"
        "【账号列表】 同上\n"
        "━━━━━━━━━━━━━\n"
        "🔄 账号切换：\n"
        "【切换账号 <UID>】 切换到指定的游戏账号\n"
        "• 只能切换到自己拥有的账号\n"
        "• 每次只能激活一个账号\n"
        "• 切换后所有命令自动使用激活账号\n"
        "━━━━━━━━━━━━━\n"
        "✏️ 账号管理：\n"
        "【重命名账号 <UID> <新名称>】 设置账号备注名\n"
        "• 备注名最长32字符\n"
        "• 方便识别多个账号（如'主号'、'小号'）\n"
        "━━━━━━━━━━━━━\n"
        "📊 历史记录：\n"
        "【转让历史】 查看账号买入/卖出历史\n"
        "【账号交易历史】 同上\n"
        "━━━━━━━━━━━━━\n"
        "🔑 账号买卖（仅管理员）：\n"
        "如需买卖账号，请联系管理员操作\n"
        "管理员可使用以下命令：\n"
        "• 【生成转让密钥 <UID>】\n"
        "• 【接收账号 <转让密钥>】\n"
        "• 【取消转让 <UID>】\n"
        "━━━━━━━━━━━━━\n"
        "💡 使用场景：\n"
        "• 多号管理：在一个QQ号下管理多个游戏角色\n"
        "• 快速切换：无需退出登录即可切换角色"
    )
    await account_help_cmd.finish(Message(msg))


# ==================== 完整帮助系统（纯文字版）====================
full_help_cmd = on_command("完整帮助", aliases={"全部帮助", "帮助大全"}, priority=5, block=True)

@full_help_cmd.handle()
async def handle_full_help(event: MessageEvent, args: Message = CommandArg()):
    """
    纯文字版完整帮助 - 列出所有游戏系统的完整指令
    """
    msg = (
        "✨ 完整帮助系统 ✨\n"
        "═════════════════════\n"
        "📚 共20个游戏系统 + 管理功能\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎮 修炼系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【修炼】【闭关】【出关】【突破】\n"
        "【加点 属性 点数】【献祭 材料 数量】\n"
        "【面板】【战力】【加点帮助】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👤 玩家系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【注册】【改名 新名字】【改性别 男/女】\n"
        "【面板 UID】【完整面板 UID】【战力说明】\n"
        "【排行榜】【财富榜】【修为榜】【幸运榜】\n"
        "【探索榜】【敏捷榜】【魅力榜】\n"
        "【成就】【成就 页码】【成就 成就名】\n"
        "【邀请码】【绑定邀请码】【邀请状态】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚔️ 战斗系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【切磋 UID】【攻击 UID/NPC】\n"
        "【世界BOSS】【讨伐BOSS】【BOSS排行】\n"
        "【死斗日志】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎽 装备系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【装备栏】【装备 编号/名称】【卸下 编号/名称】\n"
        "【一键卸下】【装备详情 编号/名称】\n"
        "【修理 编号/名称】【锻造列表】\n"
        "【配方 装备名】【锻造 装备名】\n"
        "【升阶信息】【升阶 编号/名称】【升阶列表】\n"
        "【孔位】【镶嵌】【拆卸】【镶嵌物品】\n"
        "【合成镶嵌物】【总部商店】【总部兑换】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎒 背包系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【背包】【背包 类别】【使用 物品名 数量】\n"
        "【一键嗑药】【整理背包】【图鉴】【耐药性】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🗺️ 探索系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【地图】【可视化地图】【附近地点】\n"
        "【导航 地点名】【导航 x y】【中断导航】\n"
        "【查找 NPC名】【观察】【地点详情】\n"
        "【交互 NPC名】【NPC列表】【附近玩家】\n"
        "【本周主题】【更新】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💰 经济系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【市集】【购买 物品 数量】【出售 物品 数量】\n"
        "【跑商推荐】【市集列表】【黑市】\n"
        "【存 金额】【取 金额】【余额】\n"
        "【转账 UID 金额】【理财产品】【我的理财】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📈 投资系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【投资行情】【投资刷新时间】\n"
        "【投资气运 代码 数量】【出售气运 代码 数量】\n"
        "【我的投资】【投资记录】【气运事件】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔄 交易系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【交易清单】【查牌 物品名】\n"
        "【挂牌 出售/收购 物品名 单价 数量】\n"
        "【我的挂牌】【撤牌 挂牌ID】【税率】\n"
        "【估价 编号/名称】【转账 UID 金额】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💼 打工系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【打工】【打工 工作名】【收工】\n"
        "【工作状态】【工作地点】【打工记录】\n"
        "【打工统计】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏰 公会系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【创建公会 公会名】【我的公会】【公会列表】\n"
        "【公会成员】【加入公会 公会ID】【退会】\n"
        "【申请列表】【同意/拒绝入会 UID】\n"
        "【设置职位 UID 职位名】【踢出公会 UID】\n"
        "【设置基地】【转让会长 UID】【解散公会】\n"
        "【捐献金币 金额】【公会升级】【公会建筑】\n"
        "【建造 建筑名】【公会传送】【公会丹房】\n"
        "【兑换丹药】【公会任务】【完成公会任务】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👥 社交系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【礼物商店】【买礼物 礼物名 数量】\n"
        "【赠礼 UID 礼物名 数量】【转移 UID 物品名 数量】\n"
        "【送礼记录】【收礼记录】【好感度 UID】\n"
        "【交互 月老】【离婚】【断义】【脱离师门】\n"
        "【交互 NPC名 对话内容】【对话历史 NPC名】\n"
        "【留言 内容】【私信 UID 内容】【留言板】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🌀 副本系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【进入 N层诡域】【诡域】【返回】【探索】\n"
        "【上/下/左/右】【上一层/下一层】\n"
        "【俯瞰 N层诡域】【探索宝箱】【领取宝箱】\n"
        "【使用 扫荡令】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏠 阴宅系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【阴宅】【购买阴宅】【升级阴宅】\n"
        "【迁移阴宅】【设置阴宅费用 金额】\n"
        "【切换阴宅权限】【切换阴宅付费意愿】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎣 钓鱼系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【钓鱼】【钓鱼状态】【钓鱼记录】\n"
        "【钓鱼概率】【钓鱼排行】【钓鱼图鉴】\n"
        "【鱼栏】【吃鱼 鱼名 数量】【丢弃 鱼名 数量】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🧪 炼丹系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【丹方】【炼丹状态】\n"
        "【炼丹 丹方序号/名称 数量】【收获丹药】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 委托系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【每日委托】【接取委托 编号】【完成委托】\n"
        "【刷新委托】【委托统计】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎲 娱乐系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【签到】【月卡】【抽签】【摸鱼日历】\n"
        "【每日一言】【今天吃什么】\n"
        "【恶魔轮盘帮助】【试炼列表】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎁 抽奖系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【参与抽奖 抽奖ID】【抽奖详情 抽奖ID】\n"
        "【我的抽奖】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💳 账号管理\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【我的账号】【切换账号 UID】\n"
        "【重命名账号 UID 新名称】【转让历史】\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💎 赞助系统\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "【赞助】 查看月卡权益和购买方式\n"
        "\n"
        "═════════════════════\n"
        "💡 发送具体系统名（如【修炼系统】）\n"
        "   查看该系统的详细帮助和使用说明"
    )
    await full_help_cmd.finish(Message(msg))

