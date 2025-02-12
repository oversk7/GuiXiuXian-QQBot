from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

# 注册"帮助"指令
help_cmd = on_command("帮助", aliases={"help","菜单"}, priority=5, block=True)


@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "═════════════\n"
        "🧘 修炼系统  🎪 活动系统\n"
        "🎭 玩家系统  🎒 背包系统\n"
        "🛒 每日商店  📦 交易系统\n"
        "🗓️ 任务系统"
        "═════════════\n"
        "💡 输入系统名称查看详细指令\n"
        "💡 教程及反馈请查看此链接：https://tz.nevermonarch.cn/url/?url=https://www.yuque.com/rixingyinyao-dx2t6/gs55vv/rz0e9fsw7c7sggwe \n"
        "💡 官群：962494679，官群签到奖励更多"
    )
    await help_cmd.finish(Message(msg))

# 修炼系统
xiu_lian_cmd = on_command("修炼系统", priority=4, block=True)

@xiu_lian_cmd.handle()
async def handle_xiu_lian(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 修炼系统帮助 ✨\n"
        "【修炼】 获取经验，冷却时间5分钟\n"
        "【闭关】 闭关修炼，挂机升级，但效率减半\n"
        "【出关】 出关后可继续修炼\n"
        "【突破】 突破境界，经验足够时使用\n"
        "【加点】 分配突破获得的属性点，增强实力"
    )
    await xiu_lian_cmd.finish(Message(msg))


# 活动系统
huo_dong_cmd = on_command("活动系统", priority=4, block=True)

@huo_dong_cmd.handle()
async def handle_huo_dong(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 活动系统帮助 ✨\n"
        "【签到】 每日签到，获取奖励"
        "【猜拳】 猜拳游戏，猜赢翻倍"
    )
    await huo_dong_cmd.finish(Message(msg))

# 背包系统
bag_cmd = on_command("背包系统", priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 背包系统帮助 ✨\n"
        "【背包 [页码]】 查看背包内所有物品\n"
        "【查背包 [页码] [序号]】 查询物品详细信息\n"
        "【使用物品 [物品名]】 使用指定道具\n"
        "═══════════════\n"
        "◈ 使用传送符示例：/传送 [地点]"
    )
    await bag_cmd.finish(Message(msg))

# 任务系统
ren_wu_cmd = on_command("任务系统", priority=4, block=True)
@ren_wu_cmd.handle()
async def handle_ren_wu(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 任务系统帮助 ✨\n"
        "【任务】 查看当前任务\n"
        "【传送 [地点]】 传送到指定地点\n"
        "【地图】 查看当前可探索的地点\n"
        "【探索】 探索玩家所在地点\n"
        "【队伍邀请 [UID]】 邀请玩家加入队伍\n"
        "【队伍创建/解散】 创建/解散队伍\n"
        "【踢出队员 [UID]】\n"
        "【加入队伍 [队伍ID]】用于被邀请后同意\n"
        "【退出队伍】\n"
        "【探索模式 个人/组队】 切换单人/组队探索模式"
    )
    await ren_wu_cmd.finish(Message(msg))

# 交易系统
trade_cmd = on_command("交易系统", priority=4, block=True)
@trade_cmd.handle()
async def handle_trade(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 交易系统帮助 ✨\n"
        "【交易市场】 查看玩家出售物品\n"
        "【上架 [名称] [数量] [单价]】 出售背包内物品\n"
        "【下架 [上架ID] [数量]】 下架指定商品\n"
        "【交易 [上架ID] [数量]】 购买指定商品\n"
        "【我的店铺】 查看自己上架的商品\n"
        "═══════════════\n"
        "◈ 上架示例：/上架 传送符 5 80"
    )
    await trade_cmd.finish(Message(msg))



