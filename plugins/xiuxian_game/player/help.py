from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageKeyboard,MessageArk
from nonebot.adapters.qq.models import MessageArkKv, MessageArk, MessageArkObj, MessageArkObjKv
from nonebot.params import CommandArg
import os

# 注册"帮助"指令
help_cmd = on_command("帮助", aliases={"help","菜单"}, priority=5, block=True)


@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "═════════════\n"
        "🧘 修炼系统  🎪 活动系统\n"
        "🎭 玩家系统  🎒 背包系统\n"
        "🛒 商店系统  📦 交易系统\n"
        "🗓️ 世界系统\n"
        "═════════════\n"
        "💡 输入系统名称查看详细指令\n"
        "💡 教程及反馈请去gitee搜索TheWestTutorial项目\n"
        "💡 官群：962494679，官群签到奖励翻倍"
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
        "【押大小】 押大小游戏，押赢翻倍"
        "直接发送活动名称查看详细指令"
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
        "【使用 [物品名] [数量]】 使用指定道具\n"
        "═══════════════\n"
        "◈ 使用传送符示例：/传送 [地点]"
    )
    await bag_cmd.finish(Message(msg))

# 任务系统
ren_wu_cmd = on_command("世界系统", priority=4, block=True)
@ren_wu_cmd.handle()
async def handle_ren_wu(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 世界系统帮助 ✨\n"
        "【传送 [地点]】 传送到指定地点\n"
        "【地图】 查看当前可探索的地点\n"
        "【探索】 探索玩家所在地点\n"
        "【[上|下|左|右]】 向指定方向移动一格\n"
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



