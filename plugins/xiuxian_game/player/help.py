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
        "🛒 特殊商店  📦 交易系统\n"
        "🗓️ 世界系统  🛒 装备系统\n"
        "🎮 公会系统  💰 银行系统\n"
        "🔮 炼丹系统  🎮 活动系统\n"
        "💕 社交系统  🏰 副本系统\n"
        "👻 鬼怪系统\n"
        "═════════════\n"
        "💡 发送/系统名称 查看详细指令，/赞助 支持诡修仙\n"
        "💡 【】括号里是指令，<>里是必填，[]里是选填\n"
        "💡 教程及反馈请加官群：962494679，官群签到奖励翻倍\n"
        "💡 发送/邀请码 邀请好友获得上万金币，获得启动资金\n"
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
        "【市集】 查看当前坐标市场价格表\n"
        "【市集列表】 查看全部市集坐标\n"
        "【市集详情 <市集名称>】 查看指定市集商品\n"
        "【市价 <物品名称>】 查看某物品在各市集的买/卖价\n"
        "【购买 <物品> <数量>】 消耗金币购买\n"
        "【出售 <物品> <数量>】 将背包物品卖给市场\n"
        "【跑商记录 [页数]】 查看市集购买历史\n"
        "【跑商推荐】 查看利润最高的买卖路线\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 防刷钱：在某地购买的商品，8小时内不可在同地出售"
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
        "【存款榜】 查看冥行存款排行榜"
    )
    await bank_cmd.finish(Message(msg))

# 玩家系统
player_cmd = on_command("玩家系统", priority=4, block=True)
@player_cmd.handle()
async def handle_player(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 玩家系统帮助 ✨\n"
        "查看玩家信息、排行榜，注册角色和改名\n"
        "━━━━━━━━━━━━━\n"
        "【面板 [UID]】 查看指定玩家面板\n"
        "【财富榜】 查看财富榜\n"
        "【修为榜】 查看修为榜\n"
        "【幸运榜】 查看幸运榜\n"
        "【注册】 注册角色\n"
        "【改名 <新名字>】 改名\n"
        "【改性别 <男/女>】 修改角色性别\n"
        "━━━━━━━━━━━━━\n"
        "💡 新手注册：发送【注册】，系统会引导你输入昵称\n"
        "💡 快速注册：发送【注册 昵称】，如：注册 道爷"
    )
    await player_cmd.finish(Message(msg))

# 装备系统
equip_cmd = on_command("装备系统", aliases={"装备帮助"}, priority=4, block=True)
@equip_cmd.handle()
async def handle_equip(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 装备系统帮助 ✨\n"
        "穿戴装备提升属性，用材料锻造新装备，修装备需要金币\n"
        "━━━━━━━━━━━━━\n"
        "【装备栏】 查看自己装备\n"
        "【装备 <装备ID/名称>】 穿戴指定装备\n"
        "【卸下 <装备ID/名称>】 卸下指定装备\n"
        "【锻造列表】 查看锻造列表\n"
        "【配方 <装备名称>】 查看锻造配方\n"
        "【锻造 <装备名称>】 锻造指定装备\n"
        "【修理 <装备ID/名称> [金币比例:怨念比例]】 修理指定装备（默认使用金币，可指定比例如3:2或3：2）\n"
        "【分解 <装备ID/名称>】 分解装备获得材料或金币（有损失）\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 装备限制：最多穿戴4件装备，且不能重复穿戴\n"
        "⚠️ 分解说明：只能分解未装备的装备，耐久度越高损失越少\n"
        "⚠️ 分解收益：有配方装备→材料，无配方装备→金币"
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
        "【突破 [镇厄]】 突破境界，可消耗怨念来确保成功\n"
        "【加点】 分配突破获得的属性点，增强实力\n"
        "【献祭】 献祭材料以获取怨念值，用于为突破护航"
    )
    await xiu_lian_cmd.finish(Message(msg))


# 活动系统
huo_dong_cmd = on_command("活动系统", aliases={"活动帮助"}, priority=4, block=True)

@huo_dong_cmd.handle()
async def handle_huo_dong(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 活动系统帮助 ✨\n"
        "每日签到获取奖励，参与各种活动\n"
        "━━━━━━━━━━━━━\n"
        "【签到】 每日签到，获取奖励\n"
        "【井字棋】 井字棋游戏，战胜AI获得奖励\n"
        "【试炼列表】 查看可用的互动剧情\n"
        "【月卡】 查看月卡状态和权益\n"
        "💳 月卡权益：修炼效率提升、闭关时长增加、背包扩容、签到获得扫荡令等\n"
        "直接发送活动名称查看详细指令"
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
        "【导航 [x] [y]】 开启/查看导航进度\n"
        "【中断导航】 取消当前导航\n"
        "【附近玩家】 查看附近玩家\n"
        "【留言 <内容>】 在世界留言板发布信息\n"
        "【留言板 [页码]】 查看世界留言板\n"
        "【更新】 查看最近一次更新公告"
    )
    await ren_wu_cmd.finish(Message(msg))

# 副本系统
fan_ben_cmd = on_command("副本系统", aliases={"副本帮助"}, priority=4, block=True)
@fan_ben_cmd.handle()
async def handle_fan_ben(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 副本系统帮助 ✨\n"
        "每日耗费咒抗进入诡域探索，进入后尽可能拿到更多的经验和材料\n"
        "━━━━━━━━━━━━━\n"
        "【传送 <诡域>】 进入指定诡域\n"
        "【诡域】 查看当前可探索的诡域\n"
        "【上|下|左|右】 向指定方向移动一格\n"
        "【返回】 返回现实世界并满状态\n"
        "【探索】 探索玩家所在地点\n"
        "【使用 扫荡令】 扫荡当前诡域，消耗1点咒抗获得经验和材料"
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
        "【交易清单 [页数]】 当前所有在售与求购物品总览\n"
        "【查牌 <物品名> [页数]】 查看物品在自由市场的买卖价格\n"
        "【挂牌 <出售/收购> <物品名> <单价> <数量>】 最多挂6个牌子\n"
        "【我的挂牌 [页数]】 查看自己的所有挂牌订单\n"
        "【撤牌 <挂牌ID>】 撤回指定牌子\n"
        "【税率】 查看当前阶梯交易税率\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 交易税收：5000金币以下免税，超出部分按阶梯税率征收\n"
    )
    await trade_cmd.finish(Message(msg))

# 公会系统
guild_help_cmd = on_command("公会系统", aliases={"公会帮助"}, priority=4, block=True)

@guild_help_cmd.handle()
async def handle_guild_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 公会系统帮助 ✨\n"
        "全新职位体系，建筑加成，任务系统\n"
        "━━━━━━━━━━━━━\n"
        "🏰 基础功能\n"
        "【创建公会 <公会名>】 创建公会（消耗会长委任书）\n"
        "【我的公会】 查看公会信息\n"
        "【公会成员】 查看成员列表\n"
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
        "━━━━━━━━━━━━━\n"
        "📋 任务系统\n"
        "【公会任务】 查看任务列表\n"
        "【签到】 每日签到（有公会时自动获得公会积分）\n"
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

ghost_suppression_help_cmd = on_command("鬼怪系统", aliases={"镇压系统", "鬼怪帮助"}, priority=4, block=True)

@ghost_suppression_help_cmd.handle()
async def handle_ghost_suppression_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 鬼怪镇压系统帮助 ✨\n"
        "驾驭鬼怪镇压入侵现实世界的野生鬼，获得碎片合成更强鬼怪\n"
        "━━━━━━━━━━━━━\n"
        "🔍 查看入侵：\n"
        "【入侵事件】 查看今日鬼怪入侵列表\n"
        "\n"
        "⚔️ 镇压战斗：\n"
        "【镇压 [棺材钉]】 镇压当前位置的鬼怪（需先移动到事件坐标）\n"
        "\n"
        "👻 鬼怪管理：\n"
        "【驾驭 [鬼怪名称]】 切换驾驭的鬼怪，不填则查看当前驾驭状态\n"
        "【合成 [鬼怪名称]】 使用碎片合成完整鬼怪，不填则查看可合成列表\n"
        "【升级 [鬼怪名称]】 消耗怨念值升级鬼怪，不填则查看可升级列表\n"
        "━━━━━━━━━━━━━\n"
        "📋 镇压流程：\n"
        "1️⃣ 威压判定：比较双方威压等级，不足可用棺材钉\n"
        "2️⃣ 数值战斗：基于属性进行自动战斗计算\n"
        "3️⃣ 战利品：镇压成功后有概率获得鬼怪碎片\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 威压机制：鬼怪威压等级由玩家属性决定\n"
        "⚠️ 升级机制：鬼怪等级影响属性，升级消耗怨念值\n"
        "⚠️ 每日刷新鬼怪入侵现实"
    )
    await ghost_suppression_help_cmd.finish(Message(msg))


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
        "✨ 赞助码系统帮助 ✨\n"
        "支持游戏发展，获得月卡权益和背包扩容\n"
        "━━━━━━━━━━━━━\n"
        "💳 赞助码类型：\n"
        "🔸 8.8元 - 基础月卡（30天）\n"
        "   • 修炼闭关效率+20%\n"
        "   • 闭关上限增加至9小时\n"
        "   • 背包扩容+5格\n"
        "   • 签到获得扫荡令*1，咒抗+5\n"
        "\n"
        "🔸 28.8元 - 高级月卡（30天）\n"
        "   • 修炼闭关效率+50%\n"
        "   • 闭关上限增加至12小时\n"
        "   • 背包扩容+20格\n"
        "   • 副本遇到材料和宝藏自动采集\n"
        "   • 签到获得扫荡令*3，咒抗+5\n"
        "\n"
        "🔸 5元 - 永久背包扩容+5格\n"
        "   • 永久增加背包容量5格\n"
        "   • 可重复购买叠加效果\n"
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



