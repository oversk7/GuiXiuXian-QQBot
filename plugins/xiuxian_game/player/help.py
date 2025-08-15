from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageKeyboard,MessageArk
from nonebot.adapters.qq.models import MessageArkKv, MessageArk, MessageArkObj, MessageArkObjKv
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
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "═════════════\n"
        "🧘 修炼系统  🏪 跑商系统\n"
        "🎭 玩家系统  🎒 背包系统\n"
        "🛒 系统商店  📦 交易系统\n"
        "🗓️ 世界系统  🛒 装备系统\n"
        "🎮 公会系统  💰 银行系统\n"
        "🔮 炼丹系统  🎮 娱乐系统\n"
        "💕 社交系统  🏰 副本系统\n"
        "📈 投资系统  💼 打工系统\n"
        "🏛️ 委托系统\n"
        "═════════════\n"
        "💡 发送对应系统查看详细指令，【赞助】支持诡修仙\n"
        "💡 【】括号里是指令，<>里是必填，[]里是选填\n"
        "💡 官群：962494679，不会玩直接问机器人或者加群\n"
        "💡 发送/邀请码 邀请好友获得分级奖励，最高可获得3万+金币\n"
    )
    await help_cmd.finish(Message(msg))

# 跑商系统
market_cmd = on_command("跑商系统",aliases={"跑商帮助"}, block=True, priority=5)
@market_cmd.handle()
async def handle_market(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 跑商系统帮助 ✨\n"
        "利用不同坐标的差价赚取金币，每日早9点刷新基础价格，一天内的价格受供需波动，及时查看市价避免亏损\n"
        "━━━━━━━━━━━━━\n"
        "🏪 市集交易：\n"
        "【市集】 查看当前坐标市场价格表\n"
        "【市集列表】 查看全部市集坐标\n"
        "【市集详情 <市集名称>】 查看指定市集商品\n"
        "【市价 <物品名称>】 查看某物品在各市集的买/卖价\n"
        "【购买 <物品> <数量>】 消耗金币购买\n"
        "【出售 <物品> <数量>】 将背包物品卖给市场\n"
        "【跑商记录 [页数]】 查看市集购买历史\n"
        "【跑商推荐】 查看利润最高的买卖路线\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 缉邪司总部商店：\n"
        "【缉邪司总部】 查看总部商店（风雪镇 -5,390）\n"
        "【总部兑换 <物品名称> [数量]】 用积分兑换升阶材料\n"
        "• 专售装备升阶相关特殊物品\n"
        "• 使用公会积分兑换，无需加入公会\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 防刷钱：在某地购买的商品，8小时内不可在同地出售\n"
        "⚖️ 携带限制：背包中商品总量不能超过500个，防止垄断库存"
    )
    await market_cmd.finish(Message(msg))
# 炼丹系统
alchemy_cmd = on_command("炼丹系统",aliases={"炼丹帮助"}, priority=4, block=True)

@alchemy_cmd.handle()
async def handle_alchemy(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 炼丹系统帮助 ✨\n"
        "消耗材料，获得丹药，丹炉属于装备，炉ID即装备ID\n"
        "炼丹失败时会返还50%材料\n"
        "━━━━━━━━━━━━━\n"
        "【丹方】 查看炼丹配方\n"
        "【炼丹状态】 查看炼丹状态\n"
        "【炼丹 <炉ID> <丹方序号|名称> <数量>】 消耗炉子、材料，获得丹药\n"
        "【收获丹药】"
    )
    await alchemy_cmd.finish(Message(msg))

# 银行系统
bank_cmd = on_command("银行系统",aliases={"银行帮助"}, priority=4, block=True)
@bank_cmd.handle()
async def handle_bank(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 银行系统帮助 ✨\n"
        "冥行存取金币，查询余额时自动利滚利\n"
        "━━━━━━━━━━━━━\n"
        "【存 <金额>】 存入冥行\n"
        "【取 <金额>】 从冥行取出\n"
        "【余额】 查询冥行存款并进行利滚利\n"
        "【存款榜】 查看冥行存款排行榜\n"
        "【银行投资】 查看气运投资理财选项"
    )
    await bank_cmd.finish(Message(msg))

# 气运投资系统
stock_cmd = on_command("气运投资",aliases={"投资系统"}, priority=4, block=True)
@stock_cmd.handle()
async def handle_stock(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 气运投资系统帮助 ✨\n"
        "投资各类气运项目，获得修仙资源收益\n"
        "━━━━━━━━━━━━━\n"
        "【投资行情】 查看所有可投资项目\n"
        "【投资刷新时间】 查看气运价格刷新时间\n"
        "【投资气运 <代码> <数量>】 投资气运（使用现金）\n"
        "【投资气运 <代码> <数量> 银行】 投资气运（使用银行资金）\n"
        "【出售气运 <代码> <数量>】 出售气运（收入到现金）\n"
        "【出售气运 <代码> <数量> 银行】 出售气运（收入到银行）\n"
        "【我的投资】 查看投资情况\n"
        "【投资记录】 查看投资记录\n"
        "━━━━━━━━━━━━━\n"
        "💎 投资类型：\n"
        "🔬 法宝气运 - 高波动，高风险高收益\n"
        "🏦 金融气运 - 相对稳定\n"
        "⚡ 灵气气运 - 中等波动\n"
        "🛒 丹药气运 - 较为稳定\n"
        "🏥 医道气运 - 中等波动\n"
        "🏗️ 材料气运 - 较高波动\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 风险提示：气运投资有风险，投资需谨慎！\n"
        "💸 手续费：交易金额的3%"
    )
    await stock_cmd.finish(Message(msg))

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
        "2. 使用【打工】查看可用工作\n"
        "3. 使用【打工 工作名称】开始工作\n"
        "4. 等待工作完成后使用【收工】获得奖励\n"
        "\n"
        "🏢 工作地点：\n"
        "• 上京商业中心 (0,0) - 服务业工作\n"
        "• 制造工业区 (100,200) - 体力工作\n"
        "• 休闲娱乐街区 (-50,150) - 轻松工作\n"
        "• 物流配送中心 (200,-100) - 物流工作\n"
        "\n"
        "• 工作时长：2-3分钟 (极速完成!)\n"
        "• 工资：60-180金币/次 + 特殊事件奖励\n"
        "• 频率限制：每小时最多10次，每次间隔1分钟\n"
        "\n"
        "📋 相关命令：\n"
        "【打工】 查看当前位置工作\n"
        "【打工 <工作名>】 开始工作\n"
        "【收工】 完成工作获得奖励\n"
        "【工作状态】 查看当前工作状态\n"
        "【工作地点】 查看所有工作地点\n"
        "【打工记录】 查看打工历史\n"
        "【打工统计】 查看打工数据\n"
        "\n"
        "💰 收入计算：\n"
        "基础收入 + 等级加成 + 运气加成 + 连续奖励 + 特殊事件\n"
        "\n"
        "💡 小贴士：\n"
        "• 连续打工可获得额外奖励\n"
        "• 运气值影响收入和特殊事件\n"
        "• 不同工作有不同的等级要求\n"
        "• 特殊事件可能带来额外收入\n"
        "• 适合碎片化时间，随时开始!"
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
        "【排行榜】 查看所有排行榜总览\n"
        "【财富榜】 查看财富榜\n"
        "【修为榜】 查看修为榜\n"
        "【幸运榜】 查看幸运榜\n"
        "【探索榜】 查看探索榜\n"
        "【战力】 查看自身完整属性\n"
        "【战力说明】 查看各项战斗属性的作用\n"
        "【加点帮助】 查看基本属性加点指南\n"
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
        "穿戴装备提升属性，用材料锻造新装备，升阶强化，镶嵌宝石\n"
        "━━━━━━━━━━━━━\n"
        "🎽 基础功能：\n"
        "【装备栏】 查看自己装备\n"
        "【装备详情 <装备ID/名称>】 查看装备详细信息和升阶效果\n"
        "【装备 <装备ID/名称>】 穿戴指定装备\n"
        "【卸下 <装备ID/名称>】 卸下指定装备\n"
        "【一键卸下】 卸下全部装备\n"
        "【锻造列表】 查看锻造列表\n"
        "【配方 <装备名称>】 查看锻造配方\n"
        "【锻造 <装备名称>】 锻造指定装备\n"
        "【修理 <装备ID/名称> [金币比例:怨念比例]】 修理指定装备\n"
        "━━━━━━━━━━━━━\n"
        "⭐ 升阶系统（装备合成模式）：\n"
        "【升阶信息 <装备ID/名称>】 查看升阶需求和成功率\n"
        "【升阶 <装备ID/名称>】 装备合成升阶（需要多个相同装备+升阶石）\n"
        "【升阶 <装备ID/名称> 稳定水晶】 使用稳定水晶提升成功率\n"
        "【升阶列表】 查看可升阶装备\n"
        "━━━━━━━━━━━━━\n"
        "💎 镶嵌系统：\n"
        "【孔位 <装备ID/名称>】 查看装备孔位信息\n"
        "【镶嵌 <装备名> <孔位号> <镶嵌物名称>】 镶嵌宝石/佛珠/符文\n"
        "【拆卸 <装备名> <孔位号>】 拆卸镶嵌物品（有风险）\n"
        "【镶嵌物品】 查看可镶嵌物品列表\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 缉邪司总部商店：\n"
        "【总部商店】位于北极风雪镇 (-5,390)\n"
        "【总部兑换 <物品名称> [数量]】 用积分兑换升阶材料\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 装备限制：最多穿戴4件装备，且不能重复穿戴\n"
        "⚠️ 等级限制：装备有等级要求，等级不足无法穿戴\n"
        "⚠️ 升阶说明：等阶越高成功率越低，失败可能降级或损坏\n"
        "⚠️ 镶嵌说明：需要镶嵌锤，拆卸需要拆卸凿，有损坏风险"
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
        "【突破 [镇厄|棺材钉]】 突破境界，可消耗怨念或者棺材钉来确保成功\n"
        "【冥返】 300级满级后，冥返重塑根基，获得更强潜力\n"
        "【加点 <属性> <点数>】 分配突破获得的属性点，增强实力\n"
        "【加点帮助】 查看属性详解和推荐加点方案\n"
        "【献祭】 献祭材料以获取怨念值，用于为突破护航\n"
    )
    await xiu_lian_cmd.finish(Message(msg))


# 活动系统
huo_dong_cmd = on_command("娱乐系统", aliases={"娱乐帮助"}, priority=4, block=True)

@huo_dong_cmd.handle()
async def handle_huo_dong(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 娱乐系统 ✨\n"
        "杂七杂八的小游戏和活动\n"
        "━━━━━━━━━━━━━\n"
        "🎯 基础功能：\n"
        "【签到】 每日签到，获取奖励\n"
        "【切磋 UID】 PVP切磋，无损失的玩家对战\n"
        "【模拟战斗 UID1 UID2】 观看两个玩家的模拟战斗\n"
        "【恶魔轮盘帮助】 PVP对战，可以获得对方的赌注（金币、物品）\n"
        "【试炼列表】 查看可用的互动剧情\n"
        "【月卡】 查看月卡状态和权益\n"
        "━━━━━━━━━━━━━\n"
        "📱 日常：\n"
        "【抽签 [你的问题]】 中国传统诸葛灵签，显示卦象、签诗、解签\n"
        "【摸鱼日历】 获取今日摸鱼日历和日报图片\n"
        "【每日一言】 获取励志名言警句\n"
        "━━━━━━━━━━━━━\n"
        "💳 月卡权益：修炼效率提升、闭关时长增加、背包扩容、签到获得扫荡令等\n"
        "💼 打工系统：前往指定坐标打工赚钱，详见【打工系统】\n"
    )
    await huo_dong_cmd.finish(Message(msg))

# 背包系统
bag_cmd = on_command("背包系统", aliases={"背包帮助"}, priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 背包系统帮助 ✨\n"
        "管理物品，使用道具，查看图鉴。类别可选：消耗品、材料、商品、丹药、装备\n"
        "━━━━━━━━━━━━━\n"
        "【背包 [类别] [页码]】 类别用于过滤，页码用于翻页，不填则查看所有\n"
        "【使用 <物品名> <数量>】 使用指定道具\n"
        "【丢弃 <物品名> <数量>】 丢弃指定道具\n"
        "【图鉴 <关键词>】 查看物品或装备描述，丹药会显示每日限制\n"
        "【耐药性】 查看今日丹药使用状态\n"
        "【丹药加成】 查看历史服用丹药的总属性加成\n"
        "【欺骗帮助】 想想骗人鬼会怎么做？(材料转换)\n"
        "━━━━━━━━━━━━━\n"
        "💊 丹药使用限制：\n"
        "• 每种丹药都有每日服用上限，合理安排使用计划\n"
        "• 图鉴指令可查看丹药限制和使用状态"
    )
    await bag_cmd.finish(Message(msg))

# 任务系统
ren_wu_cmd = on_command("世界系统", aliases={"世界帮助"}, priority=4, block=True)
@ren_wu_cmd.handle()
async def handle_ren_wu(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 世界系统帮助 ✨\n"
        "依赖敏捷进行坐标移动，可搭配跑商玩法赚钱\n"
        "━━━━━━━━━━━━━\n"
        "🗺️ 地图导航：\n"
        "【地图】 查看所有重要地点坐标\n"
        "【可视化地图】 生成地图图片，显示所有地点和玩家位置\n"
        "【附近地点】 查看附近100格内的地点\n"
        "【导航 [x] [y]】 开启/查看导航进度（诡域中仍可静默推进）\n"
        "【中断导航】 取消当前导航\n"
        "━━━━━━━━━━━━━\n"
        "🎯 可视化地图增强功能：\n"
        "• 有导航任务时，地图会显示绿色虚线连接你和目的地\n"
        "• 导航目标用黄色圆点标记，并显示坐标信息\n"
        "• 图例中包含导航路线和目标的说明\n"
        "━━━━━━━━━━━━━\n"
        "🏛️ 地点和NPC系统：\n"
        "【观察】 查看当前位置信息（地点、NPC、附近玩家）\n"
        "【地点详情】 查看当前地点的详细信息\n"
        "【交互 <NPC名称>】 与指定NPC交互（支持关键词匹配）\n"
        "【攻击 <目标>】 攻击玩家或NPC（支持关键词匹配）\n"
        "【NPC列表】 查看当前位置的所有NPC\n"
        "• 支持部分名称匹配，无需输入完整名称\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 荒野/诡域PvP系统：\n"
        "🏘️ 城镇安全区（市集/总部/打工地点附近5格）：\n"
        "• 玩家攻击为友好切磋，无任何损失\n"
        "🌲 荒野/诡域危险区（其他所有区域）：\n"
        "• 玩家攻击为真实死斗，败者掉落部分物品\n"
        "• 只掉落消耗品、材料、商品，不掉落装备\n"
        "• 不掉落珍贵材料（紫色及以上稀有度）\n"
        "• 掉落率：10%-25%的物品堆叠，每堆损失20%-50%\n"
        "⚠️ 荒野/诡域攻击有真实风险，请谨慎选择！\n"
        "━━━━━━━━━━━━━\n"
        "🌀 无限重诡域探索：\n"
        "【进入 N层诡域】 进入指定深度的诡域（需逐重解锁）\n"
        "【诡域】 查看探索进度和可访问深度\n"
        "【上/下/左/右】 在诡域中移动（10x10独立空间）\n"
        "【上一层/下一层】 在诡域中快速切换层级（需已解锁）\n"
        "【探索】 探索当前格子的事件，击败诡异解锁更深的诡域\n"
        "【返回】 穿越回表世界\n"
        "【俯瞰/感知 [N层诡域]】 生成指定诡域小地图，不指定则以自身为中心\n"
        "━━━━━━━━━━━━━\n"
        "🎁 深渊探索者宝箱：\n"
        "【探索宝箱】 查看可领取的深渊探索者宝箱\n"
        "【领取宝箱】 一键领取所有可领取的深渊探索者宝箱\n"
        "━━━━━━━━━━━━━\n"
        "👥 社交功能：\n"
        "【附近玩家】 查看附近玩家\n"
        "【留言 <内容>】 在世界留言板发布信息\n"
        "【留言板 [页码]】 查看世界留言板\n"
        "⚠️ 请不要发布敏感内容，严重者销号！\n"
        "━━━━━━━━━━━━━\n"
        "🌟 世界BOSS：\n"
        "【世界BOSS】 查看当前BOSS信息与规则\n"
        "【讨伐BOSS】 对当前BOSS发起攻击（每日3次）\n"
        "【BOSS排行】 查看本期累计伤害排行榜\n"
        "【开启深渊宝箱】 开启获得的深渊宝箱奖励\n"
        "━━━━━━━━━━━━━\n"
        "📰 系统信息：\n"
        "【更新】 查看最近一次更新公告"
    )
    await ren_wu_cmd.finish(Message(msg))

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
        "• 逐重解锁：击败当前重诡异解锁更深的诡域\n"
        "• 诡异等级：诡域深度 × 5（±2波动），如第10重=48-52级诡异\n"
        "• 理智消耗：每10重+1点，如1-10重消耗1点，11-20重消耗2点\n"
        "━━━━━━━━━━━━━\n"
        "🗺️ 双重空间体系：\n"
        "• 表世界：大坐标系统，无限制范围\n"
        "• 诡域：小坐标系统，范围(-5,-5)到(5,5)\n"
        "━━━━━━━━━━━━━\n"
        "🚪 基础操作：\n"
        "【进入 N层诡域】 进入指定深度的诡域（需要逐重解锁）\n"
        "【诡域】 查看探索进度和可访问深度\n"
        "【上|下|左|右】 在诡域内移动一格\n"
        "【上一层|下一层】 在诡域中快速切换层级（需已解锁）\n"
        "【返回】 穿越回表世界并满状态\n"
        "【探索】 探索当前格子的事件\n"
        "━━━━━━━━━━━━━\n"
        "🎯 诡域特色：\n"
        "• 🔓 逐重解锁：只能进入已探索深度+1\n"
        "• 📈 难度递增：深度越深，诡异越强，奖励越丰富\n"
        "• 🏆 记录进度：记录最深探索深度，永久保存\n"
        "• 🎲 材料分层：不同深度范围掉落不同品质材料\n"
        "• 🔥 特殊属性：300级以后诡异拥有暴击、连击、反击、抗暴等特殊能力\n"
        "• 🎁 宝箱奖励：每探索到第10、20、30...层可领取深渊探索者宝箱\n"
        "━━━━━━━━━━━━━\n"
        "🔍 其他功能：\n"
        "【俯瞰 N层诡域】 查看指定诡域的完整小地图\n"
        "【使用 扫荡令】 扫荡当前诡域，消耗1点咒抗获得经验和材料\n"
        "【探索宝箱】 查看可领取的深渊探索者宝箱\n"
        "【领取宝箱】 一键领取所有可领取的深渊探索者宝箱\n"
        "━━━━━━━━━━━━━\n"
        "💡 探索提示：\n"
        "• 从第1重开始，逐重击败诡异解锁更深的诡域\n"
        "• 可以重复探索已通过的深度\n"
        "• 深度越深有更好的材料和更多经验\n"
        "• 适合300+级玩家的无限探索体验\n"
        "━━━━━━━━━━━━━\n"
        "🔥 特殊属性说明（300级以后诡异）：\n"
        "• 💥暴击率：造成1.5倍伤害\n"
        "• 🔄连击率：额外攻击一次（85%伤害）\n"
        "• ⚡反击率：受到攻击后反击（70%伤害）\n"
        "• 🛡️抗暴率：抵消玩家的暴击率\n"
        "• 精英诡异的特殊属性更强！"
    )
    await fan_ben_cmd.finish(Message(msg))

# 交易系统
trade_cmd = on_command("交易系统", aliases={"交易帮助"}, priority=4, block=True)
@trade_cmd.handle()
async def handle_trade(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 交易系统帮助 ✨\n"
        "初始6个牌子，玩家可用于出售或者收购物品，挂牌后自动以最优价成交\n"
        "━━━━━━━━━━━━━\n"
        "🎽 基础功能：\n"
        "【交易清单 [页数]】 当前所有在售与求购物品总览\n"
        "【查牌 <物品名> [页数]】 查看物品在自由市场的买卖价格\n"
        "【挂牌 <出售/收购> <物品名> <单价> [数量]】 最多挂6个牌子\n"
        "【我的挂牌 [页数]】 查看自己的所有挂牌订单\n"
        "【撤牌 <挂牌ID>】 撤回指定牌子\n"
        "【税率】 查看当前阶梯交易税率\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 装备交易：\n"
        "【估价 <装备ID>】 查看装备价值评估和市场参考\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 交易税收：5000金币以下免税，超出部分按阶梯税率征收\n"
        "⚠️ 装备交易：支持升阶、镶嵌等个性化属性，按实例交易\n"
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
        "🏰 基础功能\n"
        "【创建公会 <公会名>】 创建公会（消耗会长委任书）\n"
        "【我的公会】 查看公会信息\n"
        "【公会成员 [页码]】 查看成员列表\n"
        "【公会列表 [页码]】 查看公会排行榜\n"
        "【加入公会 <公会ID>】 加入公会\n"
        "【退会】 退出公会（清空积分和贡献）\n"
        "━━━━━━━━━━━━━\n"
        "👑 管理功能\n"
        "【申请列表】 查看待处理申请（会长/副会长）\n"
        "【[同意/拒绝]入会 <UID>】 审核入会（会长/副会长）\n"
        "【设置职位 <UID> <职位名>】 设置成员职位\n"
        "【设置基地】 在当前位置设立公会基地（会长，3级+）\n"
        "【转让会长 <UID>】 转让会长职位\n"
        "【解散公会】 解散公会（会长）\n"
        "━━━━━━━━━━━━━\n"
        "💰 经济系统\n"
        "【捐献金币 <金额>】 捐献获得积分，增加公会经验和资金\n"
        "【公会升级】 消耗经验和资金升级公会（会长）\n"
        "━━━━━━━━━━━━━\n"
        "🏗️ 建筑系统\n"
        "【公会建筑】 查看建筑列表\n"
        "【建造 <建筑名>】 建造或升级建筑（会长）\n"
        "【公会属性】 查看建筑提供的加成效果\n"
        "【公会传送】 传送到公会基地（要求传送阵）\n"
        "━━━━━━━━━━━━━\n"
        "📋 任务系统\n"
        "【公会任务】 查看任务列表和进度\n"
        "【完成公会任务】 领取满足条件的任务奖励\n"
        "【公会任务统计】 查看个人和公会任务统计\n"
        "【签到】 每日签到（自动完成公会签到任务）\n"
        "【捐献金币】 捐献时自动完成每日捐献任务\n"
        "━━━━━━━━━━━━━\n"
        "🎯 职位体系：会长 > 副会长 > 核心成员 > 普通成员\n"
        "💡 只有普通成员不享受经验加成\n"
        "🏋️ 训练场建筑提供修炼效率加成，在修炼和闭关时生效"
    )
    await guild_help_cmd.finish(Message(msg))

# 社交系统
social_help_cmd = on_command("社交系统", aliases={"社交帮助"}, priority=4, block=True)

@social_help_cmd.handle()
async def handle_social_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 社交系统帮助 ✨\n"
        "结婚生子，师徒传承，互送礼物增进感情\n"
        "━━━━━━━━━━━━━\n"
        "💒 婚姻系统：\n"
        "【求婚 <UID>】 向指定玩家求婚\n"
        "【求婚申请】 查看收到的求婚申请\n"
        "【同意求婚 <UID>】 同意求婚申请\n"
        "【拒绝求婚 <UID>】 拒绝求婚申请\n"
        "【配偶】 查看配偶信息\n"
        "【离婚】 解除婚姻关系\n"
        "\n"
        "🎓 师徒系统：\n"
        "【拜师 <UID>】 向指定玩家拜师\n"
        "【拜师申请】 查看收到的拜师申请\n"
        "【收徒 <UID>】 同意拜师申请\n"
        "【拒绝收徒 <UID>】 拒绝拜师申请\n"
        "【师父】 查看师父信息\n"
        "【徒弟】 查看徒弟列表\n"
        "【出师 <UID>】 逐出指定徒弟\n"
        "【脱离师门】 脱离师父\n"
        "\n"
        "🎁 礼物系统：\n"
        "【送礼 <UID> <物品名称> <数量>】 向配偶/师父/徒弟送礼\n"
        "【送礼记录】 查看送礼历史\n"
        "【收礼记录】 查看收礼历史\n"
        "\n"
        "🏆 排行榜：\n"
        "【恩爱榜】 查看夫妻恩爱值排行榜\n"
        "【恩师榜】 查看师父恩师点排行榜\n"
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
        "【每日委托】 查看今日所有委托详情和完成统计\n"
        "【接取委托 <编号>】 接取指定编号的委托（如：接取委托 1）\n"
        "【完成委托】 在目标位置检测鬼怪死亡完成委托\n"
        "【刷新委托】 生成新的委托任务（每日最多3个）\n"
        "【委托统计】 查看委托完成统计信息\n"
        "\n"
        "🏛️ 任务流程：\n"
        "1️⃣ 查看任务：使用【每日委托】查看今日所有委托\n"
        "2️⃣ 接取委托：使用【接取委托 编号】接取指定委托\n"
        "3️⃣ 前往目标：导航到任务指定的坐标位置\n"
        "4️⃣ 观察鬼怪：使用【观察】查看当前位置的鬼怪NPC\n"
        "5️⃣ 击杀鬼怪：使用【攻击 鬼怪名字】击杀目标鬼怪\n"
        "6️⃣ 完成任务：使用【完成委托】领取奖励\n"
        "\n"
        "💰 奖励机制：\n"
        "• 经验奖励：根据敌人等级和难度计算\n"
        "• 金币奖励：完成任务获得金币收入\n"
        "• 公会积分：加入公会的玩家额外获得积分\n"
        "• 公会经验：公会成员完成任务为公会贡献经验\n"
        "\n"
        "🎭 任务类型：\n"
        "• 鬼怪消除：基础厉鬼作祟事件处理\n"
        "• 笔仙案件：笔仙梦游诡异事件调查（奖励+20%）\n"
        "• 邪修蛊惑：邪修邪教事件清理（奖励+10%）\n"
        "• 变形追捕：变形怪追捕任务（奖励+30%）\n"
        "• 石化破解：石化怪诅咒破解任务（奖励+15%）\n"
        "• 邪教清剿：邪教徒清剿任务（奖励+25%）\n"
        "\n"
        "👻 鬼怪机制：\n"
        "• 接取委托后，鬼怪NPC会在指定位置生成\n"
        "• 可以与其他玩家合作击杀鬼怪\n"
        "• 只要鬼怪死亡，任何人都可以完成对应委托\n"
        "\n"
        "📅 刷新机制：\n"
        "• 每个玩家每日最多可接取3个委托\n"
        "• 使用【刷新委托】可获取更多委托任务\n"
        "• 未完成的任务会在次日过期"
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
        "   • 签到获得扫荡令*1，咒抗+5\n"
        "🔸 28.8元 - 高级月卡（30天）\n"
        "   • 修炼闭关效率+50%\n"
        "   • 闭关上限增加至12小时，突破失败损失减少10%\n"
        "   • 背包扩容+20格\n"
        "   • 副本自动采集、装备一键修理、一键嗑药\n"
        "   • 签到获得扫荡令*3，咒抗+5\n"
        "🔸 5元 - 永久背包扩容+5格\n"
        "   • 永久增加背包容量5格，可重复购买\n"
        "🔸 2元 - 哭坟帽\n"
        "   • 使用后直接获得1w怨念值\n"
        "🔸 100元 - 当前财富榜第一名的1/10金币（限购1次）\n"
        "🔸 20元 - 随机十级宝石一颗\n"
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



