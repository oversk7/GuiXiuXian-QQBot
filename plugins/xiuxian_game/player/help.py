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
        "🛒 商店系统  📦 交易系统\n"
        "🗓️ 世界系统  🛒 装备系统\n"
        "🎮 公会系统  💰 银行系统\n"
        "🔮 炼丹系统  🎮 活动系统\n"
        "🏰 副本系统\n"
        "═════════════\n"
        "💡 发送/系统名称 查看详细指令，/更新 查看最近更新内容\n"
        "💡 教程及反馈请加官群：962494679，官群签到奖励翻倍\n"
        "💡 发送/邀请码 邀请好友获得上万金币，获得启动资金"
    )
    await help_cmd.finish(Message(msg))

# 跑商系统
market_cmd = on_command("跑商系统",aliases={"跑商帮助"}, block=True, priority=5)
@market_cmd.handle()
async def handle_market(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 跑商系统帮助 ✨\n"
        "【市集】 查看当前坐标市场价格表\n"
        "【市集列表】 查看全部市集坐标\n"
        "【市集详情 [市集名称]】 查看指定市集商品\n"
        "【市价 [物品名称]】 查看某物品在各市集的买/卖价\n"
        "【购买 [物品] [数量]】 消耗金币购买\n"
        "【出售 [物品] [数量]】 将背包物品卖给市场\n"
        "【跑商推荐】 查看利润最高的买卖路线\n"
        "═══════════════\n"
        "◈ 玩法：利用差价赚取金币，每日早9点刷新价格"
    )
    await market_cmd.finish(Message(msg))
# 炼丹系统
alchemy_cmd = on_command("炼丹系统",aliases={"炼丹帮助"}, priority=4, block=True)

@alchemy_cmd.handle()
async def handle_alchemy(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 炼丹系统帮助 ✨\n"
        "【丹方】 查看炼丹配方\n"
        "【炼丹状态】 查看炼丹状态\n"
        "【炼丹 [炉ID] [丹方序号|名称] [数量]】 消耗炉子、材料，获得丹药\n"
        "【收获丹药】\n"
        "═══════════════\n"
        "◈ 丹炉属于装备，炉ID即装备ID"
    )
    await alchemy_cmd.finish(Message(msg))

# 银行系统
bank_cmd = on_command("银行系统",aliases={"银行帮助"}, priority=4, block=True)
@bank_cmd.handle()
async def handle_bank(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 银行系统帮助 ✨\n"
        "【存 金额】 存入冥行\n"
        "【取 金额】 从冥行取出\n"
        "【余额】 查询冥行存款并进行利滚利\n"
        "【存款榜】 查看冥行存款排行榜\n"
    )
    await bank_cmd.finish(Message(msg))

# 玩家系统
player_cmd = on_command("玩家系统", priority=4, block=True)
@player_cmd.handle()
async def handle_player(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 玩家系统帮助 ✨\n"
        "【面板 [UID]】 查看指定玩家面板\n"
        "【财富榜】 查看财富榜\n"
        "【修为榜】 查看修为榜\n"
        "【注册】 注册角色\n"
        "【改名 [新名字]】 改名\n"
    )
    await player_cmd.finish(Message(msg))

# 装备系统
equip_cmd = on_command("装备系统", aliases={"装备帮助"}, priority=4, block=True)
@equip_cmd.handle()
async def handle_equip(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 装备系统帮助 ✨\n"
        "【装备栏】 查看自己装备\n"
        "【装备 [装备ID/名称]】 穿戴指定装备\n"
        "【卸下 [装备ID/名称]】 卸下指定装备\n"
        "【锻造列表】 查看锻造列表\n"
        "【配方 [装备名称]】 查看锻造配方\n"
        "【锻造 [装备名称]】 锻造指定装备\n"
        "【修理 [装备ID/名称]】 修理指定装备"
    )
    await equip_cmd.finish(Message(msg))

# 修炼系统
xiu_lian_cmd = on_command("修炼系统", aliases={"修炼帮助"}, priority=4, block=True)

@xiu_lian_cmd.handle()
async def handle_xiu_lian(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 修炼系统帮助 ✨\n"
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
        "【签到】 每日签到，获取奖励"
        "直接发送活动名称查看详细指令"
    )
    await huo_dong_cmd.finish(Message(msg))

# 背包系统
bag_cmd = on_command("背包系统", aliases={"背包帮助"}, priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 背包系统帮助 ✨\n"
        "【背包 [类别] [页码]】 类别用于过滤，页码用于翻页，不填则查看所有\n"
        "【使用 [物品名] [数量]】 使用指定道具\n"
        "【丢弃 [物品名] [数量]】 丢弃指定道具\n"
        "【图鉴 [关键词]】 查看物品或装备描述\n"
        "═══════════════\n"
        "◈ 使用示例：/背包 消耗品 1"
        "◈ 类别可选：消耗品、材料、商品、丹药、装备"
    )
    await bag_cmd.finish(Message(msg))

# 任务系统
ren_wu_cmd = on_command("世界系统", aliases={"世界帮助"}, priority=4, block=True)
@ren_wu_cmd.handle()
async def handle_ren_wu(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 世界系统帮助 ✨\n"
        "【导航 [x] [y]】 开启/查看导航进度\n"
        "【中断导航】 取消当前导航\n"
        "【附近玩家】 查看附近玩家\n"
        "【留言 内容】 在世界留言板发布信息\n"
        "【留言板 [页码]】 查看世界留言板\n"
        "【更新】 查看最近一次更新公告\n"
    )
    await ren_wu_cmd.finish(Message(msg))

# 副本系统
fan_ben_cmd = on_command("副本系统", aliases={"副本帮助"}, priority=4, block=True)
@fan_ben_cmd.handle()
async def handle_fan_ben(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 副本系统帮助 ✨\n"
        "【传送 [诡域]】 进入指定诡域\n"
        "【诡域】 查看当前可探索的诡域\n"
        "【[上|下|左|右]】 向指定方向移动一格\n"
        "【跳跃 [x] [y]】 跳跃到指定坐标，仅在驿站可使用\n"
        "【返回】 返回现实世界并满状态\n"
        "【探索】 探索玩家所在地点\n"
    )
    await fan_ben_cmd.finish(Message(msg))

# 交易系统
trade_cmd = on_command("交易系统", aliases={"交易帮助"}, priority=4, block=True)
@trade_cmd.handle()
async def handle_trade(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 交易系统帮助 ✨\n"
        "【交易清单 [页数]】 当前所有在售与求购物品总览\n"
        "【查牌 <物品名> [页数]】 查看物品在自由市场的买卖价格\n"
        "【挂牌 <出售/收购> <物品名> <单价> <数量>】 最多挂6个牌子\n"
        "【撤牌 <挂牌ID>】\n"
    )
    await trade_cmd.finish(Message(msg))

# 公会系统
guild_help_cmd = on_command("公会系统", aliases={"公会帮助"}, priority=4, block=True)

@guild_help_cmd.handle()
async def handle_guild_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 公会系统帮助 ✨\n"
        "【创建公会 公会名】 创建公会（消耗会长委任书）\n"
        "【我的公会】 查看公会信息\n"
        "【公会成员】 查看成员列表\n"
        "【公会列表 [页码]】 查看公会排行榜\n"
        "【加入公会 公会ID】 加入公会\n"
        "【申请列表】 查看待处理申请（会长）\n"
        "【[同意/拒绝]入会 UID】 审核入会（会长）\n"
        "【捐献金币 金额】 捐献金币提升贡献/公会经验\n"
        "【公会公告 [新内容|清空]】 查看公告（会长可附内容修改/清空）\n"
        "【转让会长 UID】 转让会长职位\n"
        "【退会】 退出公会\n"
        "【解散公会】 解散公会（会长）\n"
        "【公会商店】 查看公会商店"
    )
    await guild_help_cmd.finish(Message(msg))

button_test_cmd = on_command("测试", priority=4, block=True)
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


# 图片测试
img_test_cmd = on_command("图片测试", priority=4, block=True)
@img_test_cmd.handle()
async def handle_img_test(event: MessageEvent, args: Message = CommandArg()):
    # 获取当前文件所在目录
    cur_dir = os.path.dirname(__file__)
    img_path = os.path.join(cur_dir, "../test.png")
    img_path = os.path.abspath(img_path)  # 转为绝对路径
    with open(img_path, "rb") as f:
        import base64
        base64_img = base64.b64encode(f.read()).decode("utf-8")
    await img_test_cmd.finish(MessageSegment.file_image(base64_img))

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



