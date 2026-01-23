from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageKeyboard,MessageArk, MessageMarkdown
from nonebot.adapters.qq.models import MessageArkKv, MessageArk, MessageArkObj, MessageArkObjKv, MessageMarkdownParams
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
    # 先发送帮助文本
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "═════════════\n"
        "🧘 修炼系统  🎭 玩家系统\n"
        "🎒 背包系统  🛒 装备系统\n"
        "⚔️ 战斗系统  🗺️ 探索系统\n"
        "🏰 副本系统  🏛️ 委托系统\n"
        "💰 经济系统  📦 交易系统\n"
        "🎮 公会系统  💕 社交系统\n"
        "🔮 炼丹系统  🏠 阴宅系统\n"
        "💼 打工系统  🎣 钓鱼系统\n"
        "🎮 娱乐系统  🎁 抽奖系统\n"
        "📱 账号管理\n"
        "═════════════\n"
        "💡 发送对应系统查看详细指令，【赞助】支持诡修仙\n"
        "💡 【】括号里是指令，<>里是必填，[]里是选填\n"
        "💡 发送【问 你的问题】使用AI助手获得游戏指引\n"
        "💡 发送/邀请码 邀请好友获得分级奖励，最高可获得3万+金币\n"
        "💡 不会玩加频道：https://Pd.qq.Com/s/d0g9cvds4\n"
        "💡 教程：https://Tutorials.Bossjlb.Top\n"
        "💡 官群：962494679\n\n"
        "👇 快捷操作菜单:"
    )

    # 创建Markdown快捷菜单
    template_params = [
        MessageMarkdownParams(key="t1", values=["修炼"]),
        MessageMarkdownParams(key="t2", values=["面板"]),
        MessageMarkdownParams(key="t3", values=["修炼系统"]),
        MessageMarkdownParams(key="t4", values=["背包"]),
        MessageMarkdownParams(key="t5", values=["装备系统"]),
        MessageMarkdownParams(key="t6", values=["战斗系统"]),
        MessageMarkdownParams(key="t7", values=["探索系统"]),
        MessageMarkdownParams(key="t8", values=["经济系统"]),
        MessageMarkdownParams(key="t9", values=["帮助"]),
        MessageMarkdownParams(key="t10", values=["md测试"]),
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    # 组合消息:先文本,再Markdown
    final_message = Message(msg)
    final_message.append(MessageSegment.markdown(markdown))

    await help_cmd.finish(final_message)

# 经济系统（整合跑商、银行）
economy_cmd = on_command("经济系统",aliases={"经济帮助","跑商系统","跑商帮助","银行系统","银行帮助"}, block=True, priority=5)
@economy_cmd.handle()
async def handle_economy(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 经济系统帮助 ✨\n"
        "管理金币、跑商赚钱、银行理财\n"
        "━━━━━━━━━━━━━\n"
        "💰 银行系统：\n"
        "【存 <金额>】 存入冥行\n"
        "【取 <金额>】 从冥行取出\n"
        "【余额】 查询冥行存款\n"
        "【存款榜】 查看冥行存款排行榜\n"
        "【转账 <UID> <金额>】 银行转账（手续费3%）\n"
        "━━━━━━━━━━━━━\n"
        "💎 理财产品：\n"
        "【理财产品】 查看可购买的理财产品\n"
        "【购买理财 <金额> [银行]】 购买活期理财\n"
        "【我的理财】 查看理财持仓和收益\n"
        "【赎回理财 <编号> [银行]】 赎回理财产品\n"
        "• 最低投资1万，最高100万金币\n"
        "• 每日收益波动±5%，管理费0.1%/天\n"
        "• 可随时赎回，每日自动结算\n"
        "⚠️ 理财有风险，投资需谨慎！\n"
        "━━━━━━━━━━━━━\n"
        "📈 气运投资：\n"
        "【投资系统】或【气运投资】 查看详细投资教程\n"
        "【投资行情】 查看可投资气运\n"
        "【我的投资】 查看持仓情况\n"
        "⚠️ 高风险玩法，新手建议先看【投资系统】教程！\n"
        "━━━━━━━━━━━━━\n"
        "🏪 跑商系统：\n"
        "【市集】 查看当前坐标市场价格表\n"
        "【市集列表】 查看全部市集坐标\n"
        "【市集详情 <市集名称>】 查看指定市集商品\n"
        "【市价 <物品名称>】 查看某物品在各市集的买/卖价\n"
        "【购买 <物品> <数量>】 消耗金币购买\n"
        "【出售 <物品> <数量>】 将背包物品卖给市场\n"
        "【自动出售】 一键出售背包中所有可出售商品\n"
        "【跑商记录 [页数]】 查看市集购买历史\n"
        "【跑商推荐】 查看个性化盈利路线推荐\n"
        "【交易限制】 查看当前交易限制情况\n"
        "━━━━━━━━━━━━━\n"
        "🕳️ 黑市：\n"
        "【黑市】 查看今日上架与基础物品\n"
        "• 基础物品（药、改名卡等）原价售卖\n"
        "• 其他道具每日09:00随机上架，远超市价，限量出售\n"
        "• 除基础物品外，每人每天总计限购50件\n"
        "• 使用【购买 物品 数量】直接购买\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 缉邪司总部商店：\n"
        "【缉邪司总部】 查看总部商店（风雪镇 -5,390）\n"
        "【总部兑换 <物品名称> [数量]】 用积分兑换升阶材料\n"
        "• 专售装备升阶相关特殊物品、镶嵌物\n"
        "• 使用公会积分兑换，无需加入公会\n"
        "━━━━━━━━━━━━━\n"
        "📢 银行改革公告：已取消存款利息，新增理财产品\n"
        "⚠️ 跑商防刷钱：在某地购买的商品，4小时内不可在同地出售\n"
        "⚖️ 携带限制：背包中商品总量不能超过500个"
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
    msg = (
        "✨ 战斗系统帮助 ✨\n"
        "玩家对战、NPC战斗、世界BOSS挑战\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 玩家对战：\n"
        "【切磋 <UID>】 友好切磋，无损失\n"
        "【模拟战斗 <UID1> <UID2>】 观看两个玩家的模拟战斗\n"
        "【攻击 <玩家UID/NPC名称>】 攻击目标\n"
        "  • 城镇安全区：友好切磋，无损失\n"
        "  • 荒野/诡域：真实死斗，败者掉落物品\n"
        "【死斗日志 [页码]】 查看PVP日志\n"
        "━━━━━━━━━━━━━\n"
        "🌟 世界BOSS：\n"
        "【世界BOSS】 查看BOSS信息与规则\n"
        "【讨伐BOSS】 攻击BOSS（每日3次）\n"
        "【BOSS排行】 查看伤害排行榜\n"
        "【开启深渊宝箱】 开启获得的深渊宝箱奖励\n"
        "━━━━━━━━━━━━━\n"
        "� 战力系统：\n"
        "【战力】 查看自身完整属性\n"
        "【战力说明】 查看各项战斗属性的作用\n"
        "【加点帮助】 查看基本属性加点指南\n"
        "━━━━━━━━━━━━━\n"
        "⚡ 战斗机制：\n"
        "• 敏捷高的玩家更容易获得先手\n"
        "• 支持暴击、连击、反击、闪避等效果\n"
        "• 最多进行30回合，超时则平局\n"
        "� 城镇安全区包括：市集、总部、打工地点附近5格"
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
    msg = (
        "✨ 修炼系统帮助 ✨\n"
        "突破境界获得属性点，献祭材料获取怨念保驾护航\n"
        "━━━━━━━━━━━━━\n"
        "【修炼】 获取经验，冷却时间5分钟\n"
        "【闭关】 闭关修炼，挂机升级，但效率减半\n"
        "【出关】 出关后可继续修炼\n"
        "【突破 [镇厄|棺材钉]】 突破境界，可消耗怨念或棺材钉确保成功\n"
        "【连续突破 [镇厄]】 连续突破直到修为或怨念耗尽\n"
        "【冥返】 300级满级后，冥返重塑根基，获得更强潜力\n"
        "【加点 <属性> <点数>】 分配突破获得的属性点\n"
        "【加点帮助】 查看属性详解和推荐加点方案\n"
        "【免费洗点】 新手专用，30级以下消耗5点咒抗重置属性点\n"
        "【献祭 <材料名> <数量>】 献祭材料以获取怨念值\n"
        "【一键献祭 <材料1> [材料2...]】 月卡专属，批量献祭指定材料\n"
        "━━━━━━━━━━━━━\n"
        "💡 突破失败会损失部分修为，使用怨念或棺材钉可确保成功\n"
        "💡 属性点分配影响战斗力，发送【加点帮助】查看详细指南\n"
        "💡 一键献祭会献上背包中所有指定材料，请谨慎选择\n"
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
        "� 发送【赞助】查看月卡购买方式"
    )
    await entertainment_cmd.finish(Message(msg))

# 背包系统
bag_cmd = on_command("背包系统", aliases={"背包帮助"}, priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 背包系统帮助 ✨\n"
        "管理物品，使用道具，查看图鉴。类别可选：消耗品、材料、商品、丹药、装备、宝石、礼物\n"
        "━━━━━━━━━━━━━\n"
        "💡 装备不占用背包容量，请使用【装备栏】查看装备\n"
        "━━━━━━━━━━━━━\n"
        "【背包 [类别/物品名] [页码]】 类别用于过滤，页码用于翻页，不填则查看所有\n"
        "【背包 <物品名>】 查询指定物品的数量和详细信息\n"
        "【使用 <物品名> <数量>】 使用指定道具\n"
        "【一键嗑药】 自动使用回春散和凝神草补满血量和法力值\n"
        "【丢弃 <物品名> <数量>】 丢弃指定道具\n"
        "【整理背包】 将同类型可堆叠物品合并，释放背包空间\n"
        "【图鉴 <关键词>】 查看物品或装备描述，丹药会显示每日限制\n"
        "【耐药性】 查看今日丹药使用状态\n"
        "【丹药加成】 查看历史服用丹药的总属性加成\n"
        "【欺骗帮助】 想想骗人鬼会怎么做？(材料转换)\n"
        "━━━━━━━━━━━━━\n"
        "✨ 临时增益系统：\n"
        "【增益状态】 查看当前临时增益效果\n"
        "【清理增益】 手动清理过期的增益效果\n"
        "【属性分解】 查看属性来源详细分解（基础/装备/特殊装备/丹药/临时）\n"
        "【属性检查】 检查属性数据是否正常，发现异常会提示\n"
        "━━━━━━━━━━━━━\n"
        "📊 属性分解说明：\n"
        "• 基础属性：初始值 + 加点增长（不含丹药）\n"
        "• 装备加成：所有已装备装备提供的属性加成\n"
        "• 特殊装备：VIP定制装备带来的永久属性加成（如斩龙闪、镜怨之衣）\n"
        "• 丹药加成：历史服用永久丹药的累计加成\n"
        "• 临时增益：当前生效的临时buff加成\n"
        "━━━━━━━━━━━━━\n"
        "💊 丹药使用限制：\n"
        "• 每种丹药都有每日服用上限，合理安排使用计划\n"
        "• 图鉴指令可查看丹药限制和使用状态\n"
        "💡 物品查询示例：\n"
        "• 【背包 回春散】 查询回春散的数量\n"
        "• 【背包 装备】 查看所有装备\n"
        "• 【背包 礼物】 查看所有礼物\n"
        "• 【背包 2】 查看第2页物品\n"
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
        "💒 结婚系统(通过月老NPC)：\n"
        "• 前往上京(0,0)找到月老\n"
        "• 【交互 月老】查看结婚菜单\n"
        "• 需要双方好感度达到5000,且都在上京\n"
        "• 离婚需要支付10万金币\n"
        "\n"
        "🤝 结义系统(通过结义使者NPC)：\n"
        "• 前往上京(0,0)找到结义使者\n"
        "• 【交互 结义使者】查看结义菜单\n"
        "• 支持2-4人结义,每两人需要5000好感度\n"
        "• 所有人必须在上京\n"
        "\n"
        "💔 解除关系：\n"
        "【离婚】 单方面离婚(需支付10万金币)\n"
        "【断义】 解除所有结义关系\n"
        "【脱离师门】 结束师徒关系\n"
        "\n"
        "💬 NPC对话系统：\n"
        "【交互 <NPC名字> [对话内容]】 与NPC进行AI对话\n"
        "【对话历史 <NPC名字>】 查看与NPC的对话历史\n"
        "【观察】 查看当前位置的所有NPC\n"
        "💡 AI对话支持多轮上下文，NPC会记住之前的对话内容\n"
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
        "【发起抽奖 <物品名/金币> <中奖人数> <每人数量> [最低等级 [最高等级]]】\n"
        "  发起抽奖活动，奖品从背包扣除，可限制参与等级范围\n"
        "【开奖 <抽奖ID>】 进行开奖并发放奖品\n"
        "【取消抽奖 <抽奖ID>】 取消抽奖并退还奖品\n"
        "━━━━━━━━━━━━━\n"
        "📝 说明：\n"
        "• 发起抽奖时会从管理员背包扣除奖品\n"
        "• 可设置最低等级要求，防止小号参与\n"
        "• 参与人数少于中奖人数时，全部参与者中奖\n"
        "• 参与人数多于中奖人数时，随机抽取中奖者\n"
        "• 发起人不能参与自己发起的抽奖\n"
        "━━━━━━━━━━━━━\n"
        "💡 示例：\n"
        "发起抽奖 棺材钉 10 10\n"
        "发起抽奖 金币 5 1000 50 120\n"
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


# Markdown模版测试
md_test_help_info_cmd = on_command("md测试帮助", aliases={"markdown测试帮助", "模版测试帮助"}, priority=4, block=True)

@md_test_help_info_cmd.handle()
async def handle_md_test_help_info(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ Markdown模版测试帮助 ✨\n"
        "━━━━━━━━━━━━━\n"
        "📝 测试指令：\n"
        "【md测试】 使用默认值测试模版\n"
        "【md测试 参数1 参数2 ...】 自定义参数测试\n"
        "━━━━━━━━━━━━━\n"
        "🎯 模版信息：\n"
        "• 模版ID: 102499345_1768473387\n"
        "• 支持参数: t1-t10 (10个输入框)\n"
        "• 参数类型: 文本输入\n"
        "━━━━━━━━━━━━━\n"
        "💡 使用示例：\n"
        "• /md测试\n"
        "• /md测试 签到 修炼 突破\n"
        "• /md测试 测试1 测试2 测试3 测试4 测试5\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 仅支持QQ官方平台"
    )
    await md_test_help_info_cmd.finish(Message(msg))


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
