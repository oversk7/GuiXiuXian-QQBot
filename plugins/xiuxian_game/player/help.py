from nonebot import on_command, on_message
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageKeyboard,MessageArk
from nonebot.adapters.qq.models import MessageArkKv, MessageArk, MessageArkObj, MessageArkObjKv
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from nonebot.rule import to_me
import os
import asyncio
from ..models import Player
from ..models.inventory import ItemInstance, ItemType
from ..models.db import safe_session
from ..config import config
from ..utils_markdown import cmd, build_markdown

# 生成经验表
generate_exp_table_cmd = on_command("生成经验表", priority=4, block=True, permission=SUPERUSER)
@generate_exp_table_cmd.handle()
async def handle_generate_exp_table(event: MessageEvent, args: Message = CommandArg()):
    from ..utils import generate_exp_table
    await generate_exp_table_cmd.finish(await generate_exp_table())


# 帮助
help_cmd = on_command("帮助", aliases={"help","怎么玩"}, priority=5, block=True)
@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    GROUP_LINK = (
        "https://qun.qq.com/universal-share/share?"
        "ac=1&authKey=fBfQXvfkDK92gotOtEFTjwLD4R3qKy%2BV79jJCyMLKqTWKmazq23NO3miCxBir7aL"
        "&busi_data=eyJncm91cENvZGUiOiI5NjI0OTQ2NzkiLCJ0b2tlbiI6IjdSUURicDczVGpFclVUUDRF"
        "RFh4R1lYaXdzMmtyTEgvU040UlJyUkhjVUxXUGZyb0NHR3Iwa1VIZnAranpqQTQiLCJ1aW4iOiIy"
        "Njk4NTk1MTE1In0%3D"
        "&data=lTl1gOtgo5gvdmyaAmJGiAZBK6oI7nGH1jr_AuHfsltlCDUTpIdA7qvXh5k5Yj0uidZilU_o"
        "g4nQXsr8cflTzA&svctype=4&tempid=h5_group_info"
    )
    content = (
        "# 诡修仙 · 帮助菜单\n"
        "***\n"
        "**⚔️ 修仙主线**（点击查看详细指令）\n"
        f"{cmd('新手上路')} 注册/修炼/突破/加点\n"
        f"{cmd('成长核心')} 装备/锻造/炼丹/阴宅\n"
        f"{cmd('资源获取')} 打工/钓鱼/灵田/副本/委托\n"
        f"{cmd('战斗挑战')} PVE/PVP/世界BOSS/天灾\n"
        f"{cmd('经济市场')} 跑商/银行/投资/拍卖行\n"
        f"{cmd('社交公会')} 送礼/结婚/师徒/公会\n"
        f"{cmd('图鉴记录')} 排行榜/成就/图鉴\n"
        "***\n"
        "**🎮 趣味功能**（不影响修仙，随时玩）\n"
        f"{cmd('签到')} 每日签到 | {cmd('今天吃什么')} 随机食谱\n"
        f"{cmd('起卦 你的问题', '起卦 ')} 六爻占卜 | {cmd('驾考题目')} 随机驾考\n"
        f"{cmd('每日一言')} 名言 | {cmd('微博热搜')} 实时热搜\n"
        f"{cmd('恶魔轮盘帮助')} PVP博弈 | {cmd('人机轮盘 金额', '人机轮盘 ')} 单人版\n"
        f"{cmd('随机人生')} 人生重开模拟器 | {cmd('人生选择')} 自选天赋版\n"
        f"{cmd('今日小猪')} 今天你是什么猪\n"
        f"{cmd('福利娱乐')} 更多 → 猜拳/抽奖/试炼...\n"
        "***\n"
        f"{cmd('切换称号')} | {cmd('赞助商店')} | {cmd('月卡')} 月卡权益\n"
        "***\n"
        f"💡 新手？点 {cmd('新手指引')} 看成长路线\n"
        f"💡 有疑问？点 {cmd('问 你的问题', '问 ')} 询问AI\n"
        f"💡 {cmd('完整帮助')} 查看所有功能\n"
        f"💡 [加入官群【꧁༺诡修仙༻꧂】]({GROUP_LINK})\n"
        "💡 游戏资料教程👉<HTTPS://GITEE.COM/ling-gtq/TheWestTutorial>"
    )
    await help_cmd.finish(build_markdown(content))

# 空消息@机器人 → 触发帮助
empty_at_cmd = on_message(rule=to_me(), priority=99, block=True)
@empty_at_cmd.handle()
async def handle_empty_at(event: MessageEvent):
    """用户仅@机器人不说话时，等同于触发帮助"""
    text = event.get_plaintext().strip()
    if text:
        return
    await handle_help(event, Message())

# ==================== 8大帮助模块 ====================

# 1. 新手上路
newbie_module_cmd = on_command("新手上路", priority=4, block=True)
@newbie_module_cmd.handle()
async def handle_newbie_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 新手上路\n"
        "注册角色，迈出修仙第一步\n"
        "***\n"
        "**👤 注册与角色**\n"
        f"{cmd('注册 男/女', '注册 ')} 创建角色 | {cmd('面板')} 查看状态\n"
        f"{cmd('改名 新名字', '改名 ')} 改名(需改名卡) | {cmd('改性别 男/女', '改性别 ')} 修改性别\n"
        "***\n"
        "**🧘 修炼成长**\n"
        f"{cmd('修炼')} 获取经验(5分钟冷却)\n"
        f"{cmd('闭关')} 离线挂机修炼 → {cmd('出关')} 结束闭关\n"
        f"{cmd('突破')} 经验满后升级境界\n"
        f"{cmd('突破 镇厄')} 消耗怨念确保突破成功\n"
        f"{cmd('冥返')} 轮回转生(等级重置获永久加成) | {cmd('冥返信息')} 查看要求\n"
        "***\n"
        "**📊 属性加点**\n"
        f"{cmd('加点 力 10', '加点 ')} 分配属性点(力/体/敏/智/运/防) | {cmd('加点帮助')}\n"
        "***\n"
        "**🎯 每日必做**\n"
        f"{cmd('签到')} → {cmd('修炼')} → {cmd('闭关')} 睡前挂机\n"
        "***\n"
        f"> 💡 30级前突破100%成功，大胆突破！\n"
        f"> {cmd('新手指引')} 完整成长路线 | {cmd('帮助', '帮助')} 返回"
    )
    await newbie_module_cmd.finish(build_markdown(content))

# 2. 成长核心
growth_module_cmd = on_command("成长核心", priority=4, block=True)
@growth_module_cmd.handle()
async def handle_growth_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 成长核心\n"
        "装备、锻造、炼丹、阴宅——战力怎么涨\n"
        "***\n"
        "**🎽 装备线**\n"
        f"{cmd('装备栏')} 查看已穿戴\n"
        f"{cmd('装备 编号', '装备 ')} 穿戴 | {cmd('卸下 编号', '卸下 ')} 卸下 | {cmd('修理 编号', '修理 ')} 修理\n"
        f"{cmd('锻造列表')} 可锻造装备 | {cmd('锻造 装备名', '锻造 ')} 锻造\n"
        f"{cmd('升阶 编号', '升阶 ')} 升阶强化\n"
        "***\n"
        "**💎 镶嵌系统**\n"
        f"{cmd('孔位 编号', '孔位 ')} 查看孔位 | {cmd('镶嵌物品')} 可镶嵌物\n"
        f"{cmd('镶嵌 编号 孔位 镶嵌物', '镶嵌 ')} 镶嵌宝石\n"
        "***\n"
        "**🧪 炼丹线**\n"
        f"{cmd('丹方')} 查看配方 → {cmd('炼丹 丹方名 数量', '炼丹 ')} 炼制 → {cmd('收获丹药')} → {cmd('使用 丹药名', '使用 ')} 服用\n"
        "***\n"
        "**💀 怨念系统**\n"
        f"{cmd('献祭 材料名 数量', '献祭 ')} 献祭材料获取怨念(用于{cmd('突破 镇厄')})\n"
        "***\n"
        "**🏠 阴宅(修炼基地)**\n"
        f"{cmd('阴宅')} 查看 | {cmd('购买阴宅')} 购买(1000万) | {cmd('升级阴宅')} 升级 | {cmd('阴宅仓库')} 仓库\n"
        "***\n"
        f"> 💡 卡境界→先突破 | 战力低→先装备 | 药不够→炼丹或市场买\n"
        f"> {cmd('装备系统')} | {cmd('炼丹系统')} | {cmd('阴宅系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await growth_module_cmd.finish(build_markdown(content))

# 3. 资源获取
resource_module_cmd = on_command("资源获取", priority=4, block=True)
@resource_module_cmd.handle()
async def handle_resource_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 资源获取\n"
        "钱和材料从哪来？统统在这里\n"
        "***\n"
        "**💼 打工(稳定收入+道具掉落)**\n"
        f"{cmd('打工')} 查看可用工作 → {cmd('打工 工作名', '打工 ')} 开始 → {cmd('收工')} 领钱\n"
        f"{cmd('工作地点')} 所有地点 | 评级S~D倍率奖励 | 熟练度越高收入越高\n"
        "***\n"
        "**📋 委托(任务奖励)**\n"
        f"{cmd('每日委托')} 查看 → {cmd('接取委托 编号', '接取委托 ')} 接取 → {cmd('完成委托')} 完成\n"
        "***\n"
        "**🌀 诡域(副本掉落)**\n"
        f"{cmd('进入 1层诡域', '进入 ')} 进入 → {cmd('探索')} 探索 → {cmd('领取宝箱')} 领奖 → {cmd('返回')} 回来\n"
        "***\n"
        "**🗺️ 地图探索**\n"
        f"{cmd('地图')} 查看地点 | {cmd('导航 地点名', '导航 ')} 前往 | {cmd('观察')} 周围 | {cmd('交互 NPC名', '交互 ')} 交互\n"
        "***\n"
        f"**🎣 钓鱼** {cmd('钓鱼')}(5分钟冷却) | {cmd('鱼栏')} 查看存量\n"
        f"**🍳 餐厅** {cmd('创建餐厅')} 开店 | {cmd('餐厅')} 状态\n"
        f"**🌱 灵田** {cmd('灵田')} 查看 | {cmd('收菜')} 收获 | {cmd('菜市场')} 市价 | {cmd('卖菜 作物名 数量', '卖菜 ')} 出售\n"
        "***\n"
        f"> 💡 缺钱→打工/跑商 | 缺材料→副本/委托 | 缺药→炼丹/买\n"
        f"> {cmd('打工系统')} | {cmd('副本系统')} | {cmd('钓鱼系统')} | {cmd('灵田系统')} | {cmd('宠物系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await resource_module_cmd.finish(build_markdown(content))

# 4. 战斗挑战
battle_module_cmd = on_command("战斗挑战", priority=4, block=True)
@battle_module_cmd.handle()
async def handle_battle_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 战斗挑战\n"
        "打谁、掉什么、风险是什么\n"
        "***\n"
        "**⚔️ PVE - 打怪**\n"
        f"{cmd('攻击 NPC名', '攻击 ')} 攻击怪物/NPC\n"
        "荒野/诡域：真实战斗，死亡掉落 | 城镇安全区：只能切磋\n"
        "***\n"
        "**🤝 PVP - 对战**\n"
        f"{cmd('切磋 UID', '切磋 ')} 友好切磋(无损失) | {cmd('攻击 UID', '攻击 ')} 真实战斗(荒野/诡域)\n"
        "***\n"
        "**🌟 世界BOSS**\n"
        f"{cmd('世界BOSS')} 查看信息 | {cmd('讨伐BOSS')} 攻击(每日3次) | {cmd('BOSS排行')} 排行\n"
        "***\n"
        "**📊 查看战力**\n"
        f"{cmd('战力')} 完整属性 | {cmd('战力说明')} 属性作用 | {cmd('死斗日志')} 战斗记录\n"
        "***\n"
        f"> 💡 装备和丹药是提升战力的关键\n"
        f"> {cmd('战斗系统')} 详细说明 | {cmd('帮助', '帮助')} 返回"
    )
    await battle_module_cmd.finish(build_markdown(content))

# 5. 经济市场
economy_module_cmd = on_command("经济市场", priority=4, block=True)
@economy_module_cmd.handle()
async def handle_economy_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 经济市场\n"
        "所有跟钱有关的，都在这里\n"
        "***\n"
        "**🏦 银行**\n"
        f"{cmd('存 金额', '存 ')} 存入 | {cmd('取 金额', '取 ')} 取出 | {cmd('余额')} 查询 | {cmd('转账 UID 金额', '转账 ')} 转账(3%)\n"
        "***\n"
        "**🏪 跑商**\n"
        f"{cmd('市集')} 当前市场 | {cmd('市价 物品名', '市价 ')} 比价 | {cmd('跑商推荐')} 盈利路线\n"
        f"{cmd('购买 物品 数量', '购买 ')} 买入 | {cmd('出售 物品 数量', '出售 ')} 卖出 | {cmd('自动出售')} 一键卖\n"
        f"{cmd('市集列表')} | {cmd('黑市')} | {cmd('食材铺')} | {cmd('交易限制')} 冷却\n"
        "***\n"
        "**📈 气运投资(高风险)**\n"
        f"{cmd('投资行情')} 查看价格 | {cmd('我的投资')} 持仓\n"
        f"{cmd('投资气运 代码 数量', '投资气运 ')} 买入 | {cmd('出售气运 代码 数量', '出售气运 ')} 卖出\n"
        "***\n"
        "**💎 银行理财**\n"
        f"{cmd('定期理财')} 七日定存(5%周利率) | {cmd('购买定期 金额', '购买定期 ')} 买入 | {cmd('我的定期')} 持仓\n"
        f"{cmd('理财产品')} 活期理财 | {cmd('购买理财 金额', '购买理财 ')} 买入 | {cmd('我的理财')} 持仓\n"
        "***\n"
        "**🔄 玩家交易(挂牌市场)**\n"
        f"{cmd('交易清单')} 在售物品 | {cmd('我的挂牌')} 我的牌子\n"
        f"{cmd('挂牌 出售 物品 单价 数量', '挂牌 ')} 挂牌 | {cmd('撤牌 ID', '撤牌 ')} 撤回\n"
        "***\n"
        "**🏛️ 拍卖行**\n"
        f"{cmd('拍卖行')} 查看拍卖 | {cmd('出价 拍卖ID 金额', '出价 ')} 竞价\n"
        "***\n"
        f"> 💡 新手赚钱：{cmd('打工')}(稳) → {cmd('跑商推荐', '跑商推荐')}(中) → {cmd('投资行情', '投资行情')}(险)\n"
        f"> {cmd('经济系统')} | {cmd('投资系统')} | {cmd('拍卖行系统')} | {cmd('烹饪系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await economy_module_cmd.finish(build_markdown(content))

# 6. 社交公会
social_module_cmd = on_command("社交公会", priority=4, block=True)
@social_module_cmd.handle()
async def handle_social_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 社交公会\n"
        "结伴江湖，建立羁绊\n"
        "***\n"
        "**🎁 送礼系统**\n"
        f"{cmd('礼物商店')} 查看 → {cmd('买礼物 礼物名 数量', '买礼物 ')} 购买 → {cmd('赠礼 UID 礼物名 数量', '赠礼 ')} 赠送\n"
        f"{cmd('好感度 UID', '好感度 ')} 查看好感度\n"
        "***\n"
        "**💒 结婚/结义/师徒**(找月老/结义使者/师徒使者或各集群社交代理)\n"
        f"{cmd('交互 月老 求婚 UID', '交互 月老 求婚 ')} 求婚\n"
        f"{cmd('交互 结义使者 结义 UID', '交互 结义使者 结义 ')} 结义\n"
        f"{cmd('交互 师徒使者 拜师 UID', '交互 师徒使者 拜师 ')} 拜师\n"
        "***\n"
        f"**🕯️ 香火商店** {cmd('香火商店')} | {cmd('买食谱 食谱名', '买食谱 ')} 购买食谱\n"
        "***\n"
        "**🏰 公会**\n"
        f"{cmd('公会列表')} 查看 | {cmd('加入公会 ID', '加入公会 ')} 申请 | {cmd('我的公会')} 信息\n"
        f"{cmd('公会建筑')} 建筑加成 | {cmd('捐献金币 金额', '捐献金币 ')} 捐献\n"
        "***\n"
        "**💬 消息**\n"
        f"{cmd('消息')} 世界频道 | {cmd('发消息 内容', '发消息 ')} 发言 | {cmd('私信 UID 内容', '私信 ')} 私信\n"
        f"**🧧 红包** {cmd('发红包 金额 份数', '发红包 ')} | {cmd('抢红包')} | {cmd('红包记录')}\n"
        "***\n"
        f"> 💡 好感度5000可结婚/结义\n"
        f"> {cmd('社交系统')} | {cmd('公会系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await social_module_cmd.finish(build_markdown(content))

# 7. 图鉴记录
info_module_cmd = on_command("图鉴记录", priority=4, block=True)
@info_module_cmd.handle()
async def handle_info_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 图鉴记录\n"
        "查看数据、排行榜、收集图鉴\n"
        "***\n"
        "**📚 物品图鉴**\n"
        f"{cmd('图鉴 物品名', '图鉴 ')} 查看物品信息 | {cmd('钓鱼图鉴')} 鱼类图鉴\n"
        "***\n"
        f"**🏆 排行榜** {cmd('排行榜')} 总览\n"
        f"{cmd('财富榜')} | {cmd('修为榜')} | {cmd('幸运榜')} | {cmd('探索榜')}\n"
        f"{cmd('敏捷榜')} | {cmd('魅力榜')} | {cmd('钓鱼排行')} | {cmd('BOSS排行')}\n"
        "***\n"
        "**🎯 成就系统**\n"
        f"{cmd('成就')} 查看所有 | {cmd('成就 成就名', '成就 ')} 查看详情(自动触发，达成即解锁)\n"
        "***\n"
        "**📊 个人记录**\n"
        f"{cmd('面板')} 角色面板 | {cmd('完整面板')} 详细\n"
        f"{cmd('打工记录')} | {cmd('钓鱼记录')} | {cmd('投资记录')} | {cmd('委托统计')} | {cmd('打工统计')}\n"
        "***\n"
        f"> {cmd('玩家系统')} 更多指令 | {cmd('帮助', '帮助')} 返回"
    )
    await info_module_cmd.finish(build_markdown(content))

# 8. 福利娱乐
fun_module_cmd = on_command("福利娱乐", priority=4, block=True)
@fun_module_cmd.handle()
async def handle_fun_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 福利娱乐\n"
        "签到、小游戏、休闲玩法\n"
        "***\n"
        "**🎯 每日福利**\n"
        f"{cmd('签到')} 每日签到 | {cmd('月卡')} 月卡状态 | {cmd('邀请码')} 邀请好友\n"
        "***\n"
        "**🎮 小游戏**\n"
        f"{cmd('抽签 你的问题', '抽签 ')} 观音灵签 | {cmd('答案之书 你的问题', '答案之书 ')} 宇宙智慧\n"
        f"{cmd('起卦 你的问题', '起卦 ')} 六爻占卜(500金币) | {cmd('驾考题目')} 随机驾考题\n"
        f"{cmd('恶魔轮盘帮助')} PVP博弈\n"
        f"{cmd('猜拳 石头 金额', '猜拳 ')} 猜拳鬼(仅周六) | {cmd('试炼列表')} 互动剧情\n"
        f"{cmd('随机人生')} 人生重开模拟器 | {cmd('人生选择')} 自选天赋属性\n"
        f"{cmd('今日小猪')} 今天你是什么猪\n"
        "***\n"
        "**🎉 休闲功能**\n"
        f"{cmd('每日一言')} 名言 | {cmd('今天吃什么')} 随机食谱 | {cmd('微博热搜')} 热搜\n"
        "***\n"
        f"**🎁 抽奖** {cmd('参与抽奖 ID', '参与抽奖 ')} 参与 | {cmd('我的抽奖')} 记录\n"
        "***\n"
        "**🏰 天灾玩法**\n"
        f"{cmd('降临')} 降临下位世界 | {cmd('镇守')} 山寨状态 | {cmd('迎战')} 与英雄战斗\n"
        f"{cmd('侦查')} 查看英雄(10天灾点) | {cmd('天灾商店')} 兑换福利\n"
        "***\n"
        f"> {cmd('娱乐系统')} | {cmd('抽奖系统')} | {cmd('天灾系统')} | {cmd('赞助商店')} | {cmd('帮助', '帮助')} 返回"
    )
    await fun_module_cmd.finish(build_markdown(content))

# 经济系统（整合跑商、银行）
economy_cmd = on_command("经济系统",aliases={"经济帮助","跑商系统","跑商帮助","银行系统","银行帮助"}, block=True, priority=5)
@economy_cmd.handle()
async def handle_economy(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 经济系统\n"
        "管理金币、跑商赚钱、银行理财\n"
        "***\n"
        "**银行系统**\n"
        f"{cmd('存 金额', '存 ')} 存入冥行（不产生利息）\n"
        f"{cmd('取 金额', '取 ')} 取出存款\n"
        f"{cmd('余额')} 查询存款余额\n"
        f"{cmd('转账 UID 金额', '转账 ')} 银行转账（手续费3%）\n"
        "***\n"
        "**跑商系统**\n"
        f"{cmd('市集')} 查看当前市场商品和价格\n"
        f"{cmd('市价 物品名', '市价 ')} 查看物品在各市集的买卖价格\n"
        f"{cmd('市集详情')} 查看指定市集的详细商品价格\n"
        f"{cmd('购买 物品名 数量', '购买 ')} 购买商品\n"
        f"{cmd('出售 物品名 数量', '出售 ')} 出售商品\n"
        f"{cmd('自动出售')} 一键卖出所有可售商品\n"
        f"{cmd('跑商推荐')} 查看盈利路线推荐\n"
        f"{cmd('跑商记录')} 查看最近交易历史\n"
        f"{cmd('交易限制')} 查看当前交易冷却状态\n"
        f"{cmd('市集列表')} 查看所有市集坐标\n"
        f"{cmd('黑市')} 查看黑市特殊商品\n"
        f"{cmd('食材铺')} 购买烹饪基础调料（盐/酱油/醋/糖）\n"
        "***\n"
        "**跑商机制**\n"
        "同一地点买的商品4小时内不能原地卖\n"
        "市集每6小时自动补货\n"
        "同商品买越多越贵(商人加价50个后加价)\n"
        "跑商奖励：跨域贸易/远途补贴/稀缺供应/首单加成/行情红利/连续跑商\n"
        "累进跑商税：日收入30万内免税，超出部分5%-15%\n"
        "***\n"
        "**理财产品**\n"
        f"{cmd('理财产品')} 查看活期理财（随存随取）\n"
        f"{cmd('我的理财')} 查看活期持仓\n"
        f"{cmd('定期理财')} 查看七日定存（固定5%周利率）\n"
        f"{cmd('购买定期 金额', '购买定期 ')} 买入七日定存（锁定7天）\n"
        f"{cmd('我的定期')} 查看定存持仓及到期时间\n"
        f"{cmd('赎回定期 编号', '赎回定期 ')} 到期后赎回定存\n"
        "***\n"
        "**新手快速赚钱方式**\n"
        f"1. {cmd('打工系统')} 稳定收入（90-270金币/次+评级翻倍）\n"
        "2. 跑商系统 - 低买高卖赚差价\n"
        "3. 副本探索 - 获得材料出售\n"
        "***\n"
        f"> {cmd('投资系统')} 气运投资 | {cmd('帮助', '帮助')} 返回"
    )
    await economy_cmd.finish(build_markdown(content))

# 投资系统（独立详细教程）
investment_cmd = on_command("投资系统", aliases={"气运投资", "投资帮助"}, block=True, priority=5)
@investment_cmd.handle()
async def handle_investment(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 气运投资系统\n"
        "修仙界的气运交易，高风险高收益\n"
        "***\n"
        "**基本命令**\n"
        f"{cmd('投资行情')} 查看所有可投资的气运及灵力指数\n"
        f"{cmd('投资刷新时间')} 查看气运价格刷新时间\n"
        f"{cmd('投资气运 代码 数量', '投资气运 ')} 投资气运(可加 银行)\n"
        f"{cmd('出售气运 代码 数量', '出售气运 ')} 出售气运(可加 银行)\n"
        f"{cmd('我的投资')} 查看投资情况和灵力预警\n"
        f"{cmd('投资记录')} 查看投资记录\n"
        f"{cmd('气运事件')} 查看市场黑天鹅事件\n"
        "***\n"
        "**新手快速入门（3步）**\n"
        f"1. {cmd('投资行情')} 看哪个气运灵力充沛(绿光)\n"
        f"2. {cmd('投资气运 代码 10', '投资气运 ')} 买10份试试水\n"
        f"3. 涨了就 {cmd('出售气运 代码 10', '出售气运 ')} 卖掉赚钱\n"
        "***\n"
        "**重要风险（必看）**\n"
        "灵力指数系统：气运消耗过度会灵力枯竭\n"
        "绿光(70-100)=充沛 | 黄光(30-69)=谨慎 | 红光(0-29)=快跑\n"
        "灵力归零=气运消散，投资全没\n"
        "每天保管费0.1% | 买卖手续费共1%\n"
        "黑天鹅事件：每周15%概率暴跌40-50%\n"
        "***\n"
        "**防坑指南**\n"
        "别All in！只用愿意输掉的钱，多种分散风险\n"
        "红光(灵力<30)赶紧出手 | 赚了就跑别贪\n"
        "短期(1-2周)比长期好，避免保管费\n"
        "高风险玩法，新手建议先打工赚钱\n"
        "***\n"
        f"> {cmd('经济系统')} 银行/跑商 | {cmd('帮助', '帮助')} 返回"
    )
    await investment_cmd.finish(build_markdown(content))

# 钓鱼系统
fishing_cmd = on_command("钓鱼系统", aliases={"钓鱼帮助"}, block=True, priority=5)

@fishing_cmd.handle()
async def handle_fishing(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 钓鱼系统\n"
        "随时随地享受钓鱼乐趣，获得各种珍贵鱼类\n"
        "***\n"
        "**钓鱼操作**\n"
        f"{cmd('钓鱼')} 开始钓鱼（冷却5分钟）\n"
        f"{cmd('钓鱼状态')} 查看状态和统计\n"
        f"{cmd('钓鱼记录')} 查看个人钓鱼记录\n"
        f"{cmd('钓鱼概率')} 查看各品阶钓到概率\n"
        f"{cmd('钓鱼排行')} 查看钓鱼排行榜\n"
        f"{cmd('钓鱼图鉴')} 查看详细钓鱼说明\n"
        f"{cmd('鱼栏', '鱼栏 ')} 查看鱼类存量（不占背包）\n"
        f"{cmd('吃鱼 鱼名 数量', '吃鱼 ')} 品尝鱼类美味\n"
        f"{cmd('丢弃 鱼名 数量', '丢弃 ')} 放生鱼类，获得功德\n"
        "***\n"
        "**鱼类稀有度**\n"
        "普通(55%) 鲤鱼、鲫鱼、草鱼等\n"
        "优良(28%) 鲈鱼、桂鱼、黄花鱼等\n"
        "精品(14%) 三文鱼、金枪鱼、石斑鱼等\n"
        "稀有(2.5%) 中华鲟、龙鱼等\n"
        "传说(0.5%) 金龙鱼、凤凰鱼等\n"
        "***\n"
        "**图鉴功能**\n"
        f"{cmd('图鉴 物品名称', '图鉴 ')} 查看物品详细信息\n"
        f"{cmd('提交物品图片 物品名 图片URL', '提交物品图片 ')} 为物品提供图片(等级>50)\n"
        "***\n"
        "**鱼类交易**\n"
        "可在沿海城市出售给商人（舟山/海门/鹭岛/荔湾镇/鹏城/琼崖）\n"
        "稀有鱼类价值更高，运气值影响稀有鱼概率\n"
        f"{cmd('钓鱼概率')} 查看你的实际钓到概率\n"
        "***\n"
        "**鱼栏系统**\n"
        "鱼类存入专属鱼栏，不占背包空间，容量无限\n"
        f"{cmd('鱼栏')} 查看所有鱼类存量和总估值\n"
        "***\n"
        "冷却5分钟 | 每日限制50次 | 不受地点限制，新手友好\n"
        "***\n"
        f"> {cmd('烹饪系统')} 鱼类烹饪 | {cmd('帮助', '帮助')} 返回"
    )
    await fishing_cmd.finish(build_markdown(content))

# 烹饪系统
cooking_cmd = on_command("烹饪系统", aliases={"烹饪帮助", "餐厅系统", "餐厅帮助"}, block=True, priority=5)

@cooking_cmd.handle()
async def handle_cooking(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 烹饪与餐厅系统\n"
        "当老板开餐厅，雇佣厨师NPC自动经营赚钱\n"
        "***\n"
        "**餐厅管理**\n"
        f"{cmd('创建餐厅')} 开启美食帝国（初始免费）\n"
        f"{cmd('餐厅')} 查看状态和经营数据\n"
        f"{cmd('餐厅升级')} 提升等级 | {cmd('扩张餐厅')} 扩大面积(+5席位)\n"
        f"{cmd('升级厨房')} 解锁高级食谱\n"
        f"{cmd('开店')} 开始营业 | {cmd('打烊')} 暂停营业\n"
        "***\n"
        "**厨师招募**\n"
        f"{cmd('招募厨师')} 随机4个候选(500金起,4h冷却)\n"
        "费用递增: 首次500 > 1000 > 2000 > +5000\n"
        "候选有效期24h | 受餐厅等级限制\n"
        f"{cmd('雇佣 编号', '雇佣 ')} 雇佣厨师 | {cmd('解雇 厨师名', '解雇 ')} 解雇(不退费)\n"
        f"{cmd('我的厨师')} 厨师列表 | {cmd('培训厨师 厨师名', '培训厨师 ')} 升级厨师\n"
        "***\n"
        "**烹饪制作**\n"
        f"{cmd('烹饪 菜名 数量', '烹饪 ')} 手动制作菜肴\n"
        f"{cmd('食谱')} 已学食谱 | {cmd('食谱图鉴')} 所有食谱(含未解锁)\n"
        f"{cmd('吃 食物名 数量', '吃 ')} 食用食物(部分可恢复理智)\n"
        "***\n"
        "**食谱获取**\n"
        "白色(80-110香火) | 绿色(80香火) | 蓝色(250-300香火)\n"
        "紫色(800-1000香火) | 橙色(3000-4000香火) | 灵蔬(灵田种植)\n"
        f"{cmd('交互 师徒使者 香火商店', '交互 师徒使者 香火商店')} 查看商店\n"
        f"{cmd('交互 师徒使者 买食谱 食谱名', '交互 师徒使者 买食谱 ')} 购买\n"
        f"{cmd('使用 食谱名', '使用 食谱·')} 学习烹饪\n"
        "***\n"
        "**仓库与菜单**\n"
        f"{cmd('补货 食材名 数量', '补货 ')} 背包转入仓库\n"
        f"{cmd('取货 食材名 数量', '取货 ')} 仓库取回背包\n"
        f"{cmd('餐厅仓库')} 查看食材 | {cmd('升级仓库')} 扩大容量(Lv.1-5)\n"
        f"{cmd('设置菜单 菜名1 菜名2', '设置菜单 ')} 设置营业菜单\n"
        f"{cmd('设置招牌菜 菜名', '设置招牌菜 ')} 招牌菜售价+30%\n"
        f"{cmd('菜单')} 查看当前营业菜单\n"
        "***\n"
        "**经营报表**\n"
        f"{cmd('经营报表')} 24h收支 | {cmd('经营日志')} 详细日志 | {cmd('餐厅排行')} 声望排行\n"
        f"{cmd('菜品利润')} 查看各菜品利润率和适合客群\n"
        "***\n"
        "**菜肴品质**\n"
        "黑暗料理(失败,扣2理智) | 普通(1.0x) | 精致(1.5x) | 完美(2.5x+buff)\n"
        "***\n"
        "**客流分层**\n"
        "普通食客(60%) 只点白/绿菜 | 富商(30%) 点绿/蓝/紫菜 | 贵宾(10%) 只点紫/橙菜\n"
        "声望越高,富商和贵宾比例越大 | 菜单需混搭覆盖各层客群\n"
        "***\n"
        "**厨师成长**\n"
        "学徒>帮厨: 500经验+1000金 | 帮厨>厨师: 1500经验+5000金\n"
        "厨师>大厨: 4000经验+20000金 | 大厨>特级: 10000经验+80000金\n"
        "做菜经验: 成功+10 完美+25 失败+3\n"
        "***\n"
        "**快速入门**\n"
        f"1. {cmd('创建餐厅')} 学会5个家常菜食谱\n"
        f"2. {cmd('招募厨师')} 并 {cmd('雇佣 编号', '雇佣 ')} (先雇1个)\n"
        f"3. {cmd('钓鱼')} 获得鱼类食材，商店购买调料\n"
        f"4. {cmd('补货 鱼名 数量', '补货 ')} 转移食材到仓库\n"
        f"5. {cmd('设置菜单 菜名', '设置菜单 ')} 设定菜品\n"
        f"6. {cmd('开店')} 营业，每小时自动结算\n"
        "***\n"
        "营业需食材(钓鱼/跑商/诡域) | 必须设置菜单\n"
        "仓库初始50可升级 | 厨师有工资(打烊可省)\n"
        "声望影响客流 | 每小时自动结算挂机赚钱\n"
        "***\n"
        f"> {cmd('钓鱼系统')} 获取食材 | {cmd('帮助', '帮助')} 返回"
    )
    await cooking_cmd.finish(build_markdown(content))

# 炼丹系统
alchemy_cmd = on_command("炼丹系统",aliases={"炼丹帮助"}, priority=4, block=True)

@alchemy_cmd.handle()
async def handle_alchemy(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 炼丹系统\n"
        "消耗材料炼丹药，失败返还50%材料，自动用最高阶炉\n"
        "***\n"
        "**基本命令**\n"
        f"{cmd('丹方', '丹方 ')} 查看或搜索炼丹配方(可加页数/关键词)\n"
        f"{cmd('炼丹状态')} 查看炼丹状态\n"
        f"{cmd('炼丹 丹方名 数量', '炼丹 ')} 自动选择最高阶炉炼丹\n"
        f"{cmd('收获丹药')} 收获炼制完成的丹药\n"
        "***\n"
        "**丹药类型**\n"
        "经验丹: 效果随等级提升(基础+等级加成)\n"
        "治疗丹: 百分比恢复，全程有效\n"
        "战斗丹: 百分比临时增益(15-30分钟)\n"
        "永久丹: 固定值永久提升，每日限量\n"
        "洗髓丹: 转换3%属性为可分配点数\n"
        "***\n"
        "**洗髓系统**\n"
        "洗髓丹将3%指定属性转为可分配点\n"
        f"例: 攻击100时转换3点，用 {cmd('加点帮助')} 查看分配指南\n"
        "***\n"
        "**炼丹炉升阶效果**\n"
        "+0阶: 成功率x1.0 耐久消耗5\n"
        "+1阶: x1.1 耐久5 | +2阶: x1.2 耐久4\n"
        "+5阶: x1.5 耐久3 | +8阶: x1.8 耐久2\n"
        "+10阶: x2.0 耐久2(满级)\n"
        f"炼丹炉可通过 {cmd('升阶帮助')} 系统提升等级\n"
        "***\n"
        f"> {cmd('成长核心')} 更多指令 | {cmd('帮助', '帮助')} 返回"
    )
    await alchemy_cmd.finish(build_markdown(content))

# 战斗系统
battle_cmd = on_command("战斗系统",aliases={"战斗帮助","PVP系统"}, priority=4, block=True)
@battle_cmd.handle()
async def handle_battle(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 战斗系统\n"
        "玩家对战、NPC战斗、世界BOSS挑战\n"
        "***\n"
        "**玩家对战**\n"
        f"{cmd('切磋 UID', '切磋 ')} 友好切磋，无损失\n"
        f"{cmd('攻击 UID', '攻击 ')} 攻击目标(可攻击NPC)\n"
        "城镇安全区: 只能友好切磋\n"
        "荒野/诡域: 真实死斗，死亡掉落\n"
        "***\n"
        "**世界BOSS**\n"
        f"{cmd('世界BOSS')} 查看BOSS信息和血量\n"
        f"{cmd('讨伐BOSS')} 攻击BOSS（每日3次）\n"
        f"{cmd('BOSS排行')} 查看伤害排行榜\n"
        "每日重置次数 | 击杀全服奖励 | 排名额外奖励\n"
        "***\n"
        "**日志设置**\n"
        f"{cmd('日志模式')} 查看当前模式\n"
        f"{cmd('日志模式 详细', '日志模式 详细')} 完整战斗细节\n"
        f"{cmd('日志模式 简洁', '日志模式 简洁')} 仅攻击和结果\n"
        "***\n"
        "**战力相关**\n"
        f"{cmd('战力')} 查看完整属性 | {cmd('战力说明')} 属性作用\n"
        f"{cmd('死斗日志')} 真实战斗记录 | {cmd('加点帮助')} 加点指南\n"
        "***\n"
        "**战斗属性说明**\n"
        "攻击/防御: 基础伤害和减伤\n"
        "暴击率/暴击力: 暴击概率和伤害倍率\n"
        "连击率: 触发连击(2-4次)的概率\n"
        "反击率: 受攻击时反击概率\n"
        "闪避率: 躲避攻击概率 | 命中率: 命中敌人概率\n"
        "敏捷: 影响先手顺序，敏捷高更容易先手\n"
        "***\n"
        f"> {cmd('炼丹系统')} 战斗丹药 | {cmd('装备系统')} 装备强化 | {cmd('帮助', '帮助')} 返回"
    )
    await battle_cmd.finish(build_markdown(content))

# 打工系统
part_time_job_cmd = on_command("打工系统", aliases={"打工帮助"}, priority=4, block=True)
@part_time_job_cmd.handle()
async def handle_part_time_job(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 打工系统\n"
        "赚钱、练熟练度、捡道具，一举三得\n"
        "***\n"
        "**基本流程**\n"
        f"1. 前往工作地点坐标(用 {cmd('移动 x y', '移动 ')})\n"
        f"2. {cmd('打工')} 查看可用工作\n"
        f"3. {cmd('打工 工作名称', '打工 ')} 开始工作\n"
        f"4. {cmd('收工')} 获得奖励(含评级+掉落)\n"
        "***\n"
        "**📊 评级系统**\n"
        "收工时随机评级，倍率影响收入：\n"
        "🏆S(×3) ⭐A(×2) ✅B(×1.5) 📋C(×1) 💤D(×0.7)\n"
        "熟练度和运气越高，高评级概率越大\n"
        "***\n"
        "**🔰 熟练度系统**\n"
        "同一工作做多了会升级，收入加成提升：\n"
        "🔰学徒(0次) → ⭐熟手(5次+15%) → 🌟专家(15次+35%) → 👑大师(30次+60%)\n"
        "***\n"
        "**🎒 道具掉落**\n"
        "收工有概率获得材料、丹药、铭文碎片等\n"
        "熟练度越高，掉落率越高，稀有物品越多\n"
        "***\n"
        "**🏢 工作地点（共15个）**\n"
        f"上京商业中心 {cmd('移动 0 0', '移动 0 0')} 服务业\n"
        f"荔湾镇工业区 {cmd('移动 250 -1350', '移动 250 -1350')} 体力工作\n"
        f"郸城娱乐街区 {cmd('移动 150 -130', '移动 150 -130')} 轻松工作\n"
        f"天海卫物流中心 {cmd('移动 250 -50', '移动 250 -50')} 物流工作\n"
        f"石关农贸集散地 {cmd('移动 -200 -150', '移动 -200 -150')} 农贸\n"
        f"金陵文化商街 {cmd('移动 450 -480', '移动 450 -480')} 文旅\n"
        f"云岭采矿区 {cmd('移动 -850 -1150', '移动 -850 -1150')} 采矿\n"
        f"摩配镇修配街 {cmd('移动 80 140', '移动 80 140')} 维修\n"
        f"风雪镇哨站 {cmd('移动 150 1200', '移动 150 1200')} 巡逻\n"
        f"舟山渔业码头 {cmd('移动 700 -600', '移动 700 -600')} 渔业\n"
        f"大昌市商贸区 {cmd('移动 -600 -800', '移动 -600 -800')} 商贸\n"
        f"长安武馆 {cmd('移动 -500 -280', '移动 -500 -280')} 武馆杂役\n"
        f"汴梁集市 {cmd('移动 -100 -450', '移动 -100 -450')} 集市帮工\n"
        f"玉门驿站 {cmd('移动 -1200 100', '移动 -1200 100')} 驿站服务\n"
        f"鹏城码头 {cmd('移动 350 -1450', '移动 350 -1450')} 码头工作\n"
        "***\n"
        "**相关命令**\n"
        f"{cmd('打工')} 查看当前位置工作\n"
        f"{cmd('打工 工作名', '打工 ')} 开始工作\n"
        f"{cmd('收工')} 完成工作获得奖励\n"
        f"{cmd('工作状态')} 查看当前工作状态\n"
        f"{cmd('工作地点')} 查看所有工作地点\n"
        f"{cmd('打工记录')} 查看打工历史\n"
        f"{cmd('打工统计')} 查看打工数据+熟练度\n"
        "***\n"
        "💰 收入 = (基础+等级+熟练度)×运气×评级 + 连续奖励 + 特殊事件\n"
        "工时2-3分钟 | 工资90-350金币/次\n"
        "***\n"
        f"> {cmd('经济系统')} 更多赚钱方式 | {cmd('帮助', '帮助')} 返回"
    )
    await part_time_job_cmd.finish(build_markdown(content))

# 玩家系统
player_cmd = on_command("玩家系统", priority=4, block=True)
@player_cmd.handle()
async def handle_player(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 玩家系统\n"
        "查看玩家信息、排行榜，注册角色和改名\n"
        "***\n"
        "**玩家面板**\n"
        f"{cmd('面板', '面板 ')} 查看玩家面板(可加UID)\n"
        f"{cmd('完整面板', '完整面板 ')} 完整面板(含战力+注册时间)\n"
        f"{cmd('战力')} 查看完整属性 | {cmd('战力说明')} 属性作用\n"
        f"{cmd('加点帮助')} 查看加点指南\n"
        "***\n"
        "**排行榜**\n"
        f"{cmd('排行榜')} 所有排行榜总览\n"
        f"{cmd('财富榜')} | {cmd('修为榜')} | {cmd('幸运榜')} | {cmd('探索榜')}\n"
        f"{cmd('敏捷榜')} | {cmd('小游戏榜')} | {cmd('魅力榜')} 魅力(收礼获得)\n"
        "***\n"
        "**成就系统**\n"
        f"{cmd('成就')} 查看所有成就(第1页)\n"
        f"{cmd('成就 页码', '成就 ')} 指定页(每页15个)\n"
        f"{cmd('成就 成就名', '成就 ')} 查看成就详情\n"
        "***\n"
        "**成就类型**\n"
        "基础成就: 修炼、战斗、探索等新手引导\n"
        "高难度成就: 百战不殆、千人斩、财富自由等\n"
        "特殊成就: 周年纪念、终身成就等限定\n"
        "***\n"
        "**成就分类**\n"
        "修炼/成长/战斗/装备/财富/探索/忠诚系列\n"
        "奖励: 金币、怨炁(经验)、属性点\n"
        "自动触发，达成即解锁，诡域击杀也计入\n"
        "***\n"
        "**注册与改名**\n"
        f"{cmd('注册 男', '注册 ')} 或 {cmd('注册 女', '注册 ')} 注册角色(自动生成道号)\n"
        f"{cmd('改名 新名字', '改名 ')} 改名(需改名卡，首次签到获得)\n"
        f"{cmd('改性别 男', '改性别 ')} 修改角色性别\n"
        f"{cmd('邀请码')} 查看邀请码 | {cmd('绑定邀请码 码', '绑定邀请码 ')} 绑定\n"
        f"{cmd('邀请状态')} 查看邀请奖励发放状态\n"
        "***\n"
        "**隐私设置**\n"
        f"{cmd('隐藏活动')} 隐藏活动记录 | {cmd('显示活动')} 恢复公开\n"
        "***\n"
        f"> {cmd('签到')} 首次获改名卡 | {cmd('帮助', '帮助')} 返回"
    )
    await player_cmd.finish(build_markdown(content))

# 装备系统
equip_cmd = on_command("装备系统", aliases={"装备帮助"}, priority=4, block=True, force_whitespace=True)
@equip_cmd.handle()
async def handle_equip(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 装备系统帮助\n"
        "穿戴装备提升属性，锻造、升阶、镶嵌强化装备\n"
        "***\n"
        "**🎽 基础功能**\n"
        f"{cmd('装备栏', '装备栏 ')} 查看装备(显示编号)\n"
        f"{cmd('装备详情 编号/名称', '装备详情 ')} 查看详细信息\n"
        f"{cmd('装备 编号', '装备 ')} 穿戴装备(支持批量)\n"
        f"{cmd('卸下 编号', '卸下 ')} 卸下装备 | {cmd('一键卸下')} 全部卸下\n"
        f"{cmd('修理 编号', '修理 ')} 修理装备\n"
        "***\n"
        "**🛠️ 耐久与损坏**\n"
        "• 耐久降至0自动卸下且无法穿戴，需修理恢复\n"
        "• 战斗/副本/扫荡均会消耗耐久\n"
        "***\n"
        "**⚒️ 锻造系统**\n"
        f"{cmd('锻造列表')} 查看全部装备及可锻造城镇\n"
        f"{cmd('配方 装备名', '配方 ')} 查看锻造配方\n"
        f"{cmd('锻造 装备名', '锻造 ')} 锻造装备(需在工坊≤3格)\n"
        "💡 诡域中无法锻造，需返回现实世界\n"
        "***\n"
        "**⭐ 升阶系统**\n"
        f"{cmd('升阶信息 编号', '升阶信息 ')} 查看升阶需求和成功率\n"
        f"{cmd('升阶 编号', '升阶 ')} 装备合成升阶\n"
        f"{cmd('升阶 编号 稳定水晶', '升阶 ')} 提升成功率\n"
        f"{cmd('一键升阶 编号 目标阶数', '一键升阶 ')} 自动连续升阶\n"
        f"{cmd('升阶列表')} 查看可升阶装备\n"
        "💡 1-3阶成功率95%-85%，7-10阶60%-25%\n"
        "***\n"
        "**💎 镶嵌系统**\n"
        f"{cmd('孔位 编号', '孔位 ')} 查看孔位信息\n"
        f"{cmd('镶嵌 编号 孔位 镶嵌物', '镶嵌 ')} 镶嵌宝石/符文\n"
        f"{cmd('拆卸 编号 孔位', '拆卸 ')} 拆卸镶嵌物(有风险)\n"
        f"{cmd('镶嵌物品')} 可镶嵌物品列表\n"
        f"{cmd('镶嵌物升级 镶嵌物名', '镶嵌物升级 ')} 查看升级信息\n"
        f"{cmd('合成镶嵌物 镶嵌物名', '合成镶嵌物 ')} 升级合成\n"
        f"{cmd('可升级镶嵌物')} 查看所有可升级的镶嵌物\n"
        "***\n"
        "**🔮 词缀系统**\n"
        "• 击杀怪物有概率掉落带词缀的装备\n"
        "• T1词缀：暴击/闪避/穿透等战斗属性加成\n"
        "• T2词缀：恐惧/吸血/反伤等特殊效果\n"
        "• 词缀数量取决于稀有度(白0-1，绿1-2，蓝2-3，紫3-4，橙4)\n"
        "• 锻造产出为素装(无词缀)，仅怪物掉落带词缀\n"
        f"{cmd('装备详情 编号', '装备详情 ')} 可查看装备词缀\n"
        "***\n"
        "**📜 铭文系统**\n"
        "• 铭文分为基础铭文(单效果)和高级铭文(多效果)\n"
        "• 品阶：下品/中品/上品/极品/仙品\n"
        "• 来源：精英怪掉落(主要)、铭文碎片合成(基础)\n"
        "• 3000级+精英怪有极低概率触发仙品铭文\n"
        f"{cmd('铭文列表')} 查看背包中的铭文\n"
        f"{cmd('合成铭文')} 消耗5碎片，60%概率合成随机铭文\n"
        f"{cmd('合成铭文 稳定水晶')} 额外消耗1稳定水晶，100%成功\n"
        f"{cmd('镶嵌 装备编号 孔位 铭文编号', '镶嵌 ')} 镶嵌铭文(编号见铭文列表)\n"
        f"{cmd('拆卸 编号 孔位', '拆卸 ')} 拆卸铭文\n"
        "***\n"
        "**🔨 分解系统**\n"
        "• 销毁装备获得洗词石(按稀有度1~15个)\n"
        "• 带T2词缀装备分解有50%概率获得铭文碎片\n"
        "• 已穿戴/VIP装备不可分解\n"
        f"{cmd('分解 编号/名称', '分解 ')} 分解装备\n"
        "***\n"
        "**🔄 洗炼系统**\n"
        "• 消耗洗词石×1重新随机词缀数值\n"
        "• 词缀类型不变，数值在区间内重随机\n"
        "• 洗炼后直接覆盖，不可保留旧值\n"
        f"{cmd('洗炼 编号 词缀序号', '洗炼 ')} 预览洗炼\n"
        f"{cmd('确认洗炼')} 执行洗炼\n"
        "***\n"
        "**🏛️ 总部商店**\n"
        f"{cmd('总部商店')} 北极风雪镇(-5,390)\n"
        f"{cmd('总部兑换 物品 数量', '总部兑换 ')} 用积分兑换材料\n"
        "***\n"
        "⚠️ 最多穿戴5件装备，不能重复穿戴\n"
        f"💡 VIP定制装备持有者可发送{cmd('装备菜单')}查看专属技能\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await equip_cmd.finish(build_markdown(content))

# 修炼系统
xiu_lian_cmd = on_command("修炼系统", aliases={"修炼帮助"}, priority=4, block=True)

@xiu_lian_cmd.handle()
async def handle_xiu_lian(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 修炼系统\n"
        "突破境界获得属性点，献祭材料获取怨念保驾护航\n"
        "***\n"
        "**🧘 修炼相关**\n"
        f"{cmd('修炼')} 获取经验，冷却5分钟\n"
        f"{cmd('闭关')} 挂机升级，效率减半\n"
        "• 基础闭关：9小时 | 高级月卡：12小时\n"
        f"{cmd('出关')} 出关后可继续修炼\n"
        "***\n"
        "**⚡ 突破系统**\n"
        f"{cmd('突破')} 突破境界，提升等级上限\n"
        "• 30级前：100%成功\n"
        "• 30级后：成功率递减(最低10%)\n"
        "• 失败保留70-80%修为\n"
        f"{cmd('突破 镇厄')} 消耗怨念确保成功\n"
        f"{cmd('突破 棺材钉')} 使用棺材钉确保成功\n"
        "***\n"
        "**📊 属性加点**\n"
        f"{cmd('加点 属性 点数', '加点 ')} 分配属性点\n"
        "可选属性：力量、体质、敏捷、智力、幸运\n"
        f"{cmd('加点帮助')} 查看详细加点指南\n"
        "***\n"
        "**💀 怨念系统**\n"
        f"{cmd('献祭 材料名 数量', '献祭 ')} 献祭材料获取怨念值\n"
        "• 不同材料怨念值不同，品质越高怨念值越多\n"
        "***\n"
        "**🔥 焚金炉(充能系统)**\n"
        f"{cmd('焚金', '焚金')} 查看充能状态和炉火状态\n"
        f"{cmd('焚金 金额', '焚金 ')} 投入金币为焚金炉充能\n"
        "• 充能越高修炼/闭关效率越高，满充+100%\n"
        "• 非线性成本：充能越高每1%越贵\n"
        "• 三档衰减：勤续费慢衰减，长期不充快速衰减\n"
        "***\n"
        "**📈 查询相关**\n"
        f"{cmd('面板')} 查看角色面板 | {cmd('战力')} 查看战斗属性\n"
        "***\n"
        "💡 突破失败会损失部分修为，使用怨念或棺材钉可确保成功\n"
        "💡 焚金炉、阴宅、月卡、公会建筑可提升修炼效率\n"
        f"> {cmd('加点帮助')} 详细指南 | {cmd('帮助', '帮助')} 返回主菜单"
    )
    await xiu_lian_cmd.finish(build_markdown(content))


# 阴宅系统
mansion_cmd = on_command("阴宅系统", aliases={"阴宅帮助"}, priority=4, block=True)

@mansion_cmd.handle()
async def handle_mansion(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 阴宅系统帮助\n"
        "拥有阴宅可大幅提升修炼效率，支持其他玩家付费使用\n"
        "***\n"
        "**🏠 基础操作**\n"
        f"{cmd('阴宅')} 查看阴宅状态和位置信息\n"
        f"{cmd('购买阴宅')} 在当前位置花费1000万金币购买1级阴宅\n"
        f"{cmd('升级阴宅')} 在阴宅位置消耗金币升级等级\n"
        f"{cmd('迁移阴宅')} 将阴宅迁移到当前位置\n"
        f"{cmd('设置阴宅费用 金币数', '设置阴宅费用 ')} 设置他人使用费用\n"
        f"{cmd('切换阴宅权限')} 允许/禁止他人使用\n"
        f"{cmd('切换阴宅付费意愿')} 设置是否愿意付费使用他人阴宅\n"
        "***\n"
        "**🗃️ 阴宅仓库(个人存储空间)**\n"
        f"{cmd('阴宅仓库')} 查看仓库内容和剩余容量\n"
        f"{cmd('存入阴宅 物品名 数量', '存入阴宅 ')} 将背包物品存入仓库\n"
        f"{cmd('取出阴宅 序号 数量', '取出阴宅 ')} 从仓库取出物品到背包\n"
        "⚠️ 必须在自己的阴宅位置才能存取\n"
        "💡 可存入：材料、消耗品、宝石\n"
        "💡 容量随等级递增：1级=50格，10级=95格，20级=245格，30级=545格\n"
        "***\n"
        "**💡 阴宅等级效率加成(修炼/闭关)**\n"
        "每级+9%效率，最高30级\n"
        "1级：+20% | 5级：+56% | 10级：+101%\n"
        "20级：+191% | 30级：+281%\n"
        "***\n"
        "**🌱 阴宅灵田加成(种植时自动生效)**\n"
        "成长加速(缩短种植时间)：\n"
        "1级：5% | 5级：25% | 10级：40% | 20级：60% | 30级：70%(上限)\n"
        "产量加成(增加收获数量)：\n"
        "1-5级：0% | 10级：+25% | 20级：+45% | 30级：+55%(上限)\n"
        "***\n"
        "⚠️ 不能在城镇市集20格半径范围内建造\n"
        f"💡 使用{cmd('观察')}命令可查看当前位置的阴宅信息\n"
        "💡 升级阴宅必须在阴宅位置进行\n"
        "***\n"
        "**⚙️ 阴宅付费意愿设置**\n"
        "• 默认愿意：在他人阴宅修炼会自动支付费用\n"
        "• 设为不愿意：不会扣费，但无法享受加成\n"
        "***\n"
        "**🚚 阴宅迁移功能**\n"
        "• 迁移费用：当前等级升级费用的50%\n"
        f"• 移动到目标位置后使用{cmd('迁移阴宅')}命令\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await mansion_cmd.finish(build_markdown(content))


# 娱乐系统
entertainment_cmd = on_command("娱乐系统", aliases={"娱乐帮助"}, priority=4, block=True)

@entertainment_cmd.handle()
async def handle_entertainment(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 娱乐系统\n"
        "签到、小游戏、互动剧情等休闲玩法\n"
        "***\n"
        "**🎯 日常活动**\n"
        f"{cmd('签到')} 每日签到，获取奖励\n"
        f"{cmd('月卡')} 查看月卡状态和权益\n"
        f"{cmd('抽签 你的问题', '抽签 ')} 观音灵签占卜\n"
        f"{cmd('起卦 你的问题', '起卦 ')} 六爻占卜，AI解卦(500金币)\n"
        f"{cmd('答案之书 你的问题', '答案之书 ')} 向宇宙提问，获得智慧指引\n"
        f"{cmd('驾考题目', '驾考题目 ')} 随机驾考题目(支持科目一~四)\n"
        f"{cmd('每日一言')} 获取励志名言警句\n"
        f"{cmd('今天吃什么')} 获取随机食谱推荐\n"
        f"{cmd('微博热搜')} 查看实时微博热搜榜TOP20\n"
        f"{cmd('吃掉 QQ号', '吃掉 ')} 生成吃掉指定QQ号头像的GIF动图\n"
        "***\n"
        "**🎮 小游戏**\n"
        f"{cmd('恶魔轮盘帮助')} PVP对战博弈游戏(3%税收)\n"
        f"{cmd('人机轮盘 金额', '人机轮盘 ')} 私聊对战AI版恶魔轮盘\n"
        f"{cmd('猜拳 石头 金额', '猜拳 ')} 猜拳鬼(仅限周六，1000+金币)\n"
        f"{cmd('试炼列表')} 查看可用的互动剧情\n"
        f"{cmd('已通关试炼')} 查看已通关的试炼记录\n"
        "***\n"
        "**💳 月卡权益**\n"
        "• 修炼闭关效率提升\n"
        "• 闭关时长增加\n"
        "• 背包扩容\n"
        "• 签到获得月卡宝箱\n"
        "• 一键献祭、一键修复等便捷功能\n"
        "***\n"
        f"📱 发送{cmd('赞助')}查看月卡购买方式\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await entertainment_cmd.finish(build_markdown(content))

# 背包系统
bag_cmd = on_command("背包系统", aliases={"背包帮助"}, priority=4, block=True)
@bag_cmd.handle()
async def handle_bag(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 背包系统\n"
        "管理物品，使用道具，查看图鉴\n"
        "***\n"
        "**🎒 背包管理**\n"
        f"{cmd('背包')} 查看所有物品\n"
        f"{cmd('背包 类别', '背包 ')} 查看指定类别物品\n"
        "可选类别：消耗品、材料、商品、丹药、装备、宝石、礼物、调味品、菜肴、食谱\n"
        f"{cmd('整理背包')} 自动整理背包空间\n"
        "***\n"
        "**💊 物品使用**\n"
        f"{cmd('使用 物品名 数量', '使用 ')} 使用消耗品/丹药\n"
        f"{cmd('一键嗑药')} 自动使用治疗药品至满血满蓝\n"
        f"{cmd('耐药性')} 查看丹药每日使用限制\n"
        "***\n"
        "**🎭 材料转换(欺骗系统)**\n"
        f"{cmd('欺骗 源材料 目标材料 数量', '欺骗 ')} 用3倍同品质材料转换\n"
        "机制：消耗源材料×3，支付目标材料价值×10手续费\n"
        "限制：只能转换同品质材料\n"
        f"{cmd('欺骗帮助')} 查看欺骗系统详细说明\n"
        "***\n"
        "**📖 图鉴系统**\n"
        f"{cmd('图鉴')} 查看已收集的物品图鉴\n"
        f"{cmd('图鉴 物品名', '图鉴 ')} 查看物品详细信息\n"
        f"{cmd('提交物品图片 物品名 图片URL', '提交物品图片 ')} 提交物品图片(需等级>50)\n"
        "***\n"
        "**📦 背包容量**\n"
        "• 基础容量：100格\n"
        "• 基础月卡：+5格\n"
        "• 高级月卡：+20格\n"
        "• 永久扩容：每次+5格(可重复购买)\n"
        "***\n"
        "💡 装备不占用背包容量\n"
        "💡 鱼类存入专属鱼栏，不占背包\n"
        "💡 商品类物品仅用于跑商交易\n"
        "💡 部分丹药有耐药性限制，请注意\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await bag_cmd.finish(build_markdown(content))

# 探索系统
explore_cmd = on_command("探索系统", aliases={"世界系统","世界帮助","探索帮助"}, priority=4, block=True)
@explore_cmd.handle()
async def handle_explore(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 探索系统帮助\n"
        "依赖敏捷进行坐标移动，探索世界，与NPC交互\n"
        "***\n"
        "**🗺️ 地图导航**\n"
        f"{cmd('地图')} 查看所有重要地点坐标\n"
        f"{cmd('可视化地图')} 生成地图图片\n"
        f"{cmd('附近地点')} 查看附近300格内的地点和阴宅\n"
        f"{cmd('导航 地点名', '导航 ')} 快速导航到指定地点\n"
        f"{cmd('导航 x y', '导航 ')} 坐标导航\n"
        "💡 长途导航途中可能遭遇随机事件\n"
        f"{cmd('查找 NPC名', '查找 ')} 查询NPC位置\n"
        f"{cmd('中断导航')} 取消当前导航\n"
        "***\n"
        "**🏛️ 地点和NPC**\n"
        f"{cmd('观察')} 查看当前位置信息(NPC、玩家、阴宅)\n"
        f"{cmd('地点详情')} 查看当前地点的详细信息\n"
        f"{cmd('交互 NPC名称', '交互 ')} 与NPC交互(支持关键词)\n"
        f"{cmd('NPC列表')} 查看当前位置的所有NPC\n"
        "💡 每城都有**驿丞**（查城市信息）和**情报贩子**（查物价行情）\n"
        "💡 **社交代理**（求婚/结义/拜师）在各集群主城均有\n"
        "***\n"
        "**⚒️ 工坊锻造**\n"
        f"{cmd('锻造列表')} 查看全部装备及可锻造城镇\n"
        f"{cmd('配方 装备名', '配方 ')} 查看锻造配方\n"
        f"{cmd('锻造 装备名', '锻造 ')} 在工坊附近锻造(≤3格)\n"
        f"{cmd('工匠配方一览 城市名', '工匠配方一览 ')} 远程查看城市配方\n"
        "***\n"
        "**👥 社交功能**\n"
        f"{cmd('最近活动 UID', '最近活动 ')} 查看指定玩家的最近上线时间\n"
        f"{cmd('附近玩家')} 查看附近玩家\n"
        f"{cmd('发消息 内容', '发消息 ')} 发送到世界频道\n"
        f"{cmd('发消息 公会 内容', '发消息 公会 ')} 发送到公会频道\n"
        f"{cmd('私信 UID 内容', '私信 ')} 给指定修士发送私信\n"
        f"{cmd('消息', '消息 ')} 查看对应频道(世界/私信/系统/公会)\n"
        "***\n"
        "**🔍 其他**\n"
        f"{cmd('本周主题')} 查看本周都市怪谈主题\n"
        "***\n"
        "💡 敏捷属性影响移动速度和导航效率\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await explore_cmd.finish(build_markdown(content))

# 副本系统
fan_ben_cmd = on_command("副本系统", aliases={"副本帮助"}, priority=4, block=True)
@fan_ben_cmd.handle()
async def handle_fan_ben(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 无限诡域探索系统帮助\n"
        "探索无限重叠的诡域，每重都是独立的10x10空间\n"
        "***\n"
        "**🌀 诡域机制**\n"
        "• 无限重叠：支持无限重扩展，适应任何等级\n"
        "• 逐重解锁：击败当前重诡异解锁更深诡域\n"
        "• 诡异等级：深度×5(±2波动)\n"
        "• 理智消耗：每10重+1点\n"
        "***\n"
        "**🚪 基础操作**\n"
        f"{cmd('进入 N层诡域', '进入 ')} 进入指定深度(需逐重解锁)\n"
        f"{cmd('诡域')} 查看探索进度和可访问深度\n"
        f"{cmd('上')} {cmd('下')} {cmd('左')} {cmd('右')} 在诡域内移动\n"
        f"{cmd('上一层')} {cmd('下一层')} 快速切换相邻层级\n"
        f"{cmd('传送 N层诡域', '传送 ')} 诡域内跳转到已解锁层(免咒抗)\n"
        f"{cmd('返回')} 穿越回表世界并满状态\n"
        f"{cmd('探索')} 探索当前格子的事件\n"
        "***\n"
        "**🎯 诡域特色**\n"
        "• 逐重解锁：只能进入已探索深度+1\n"
        "• 自由跳转：诡域内可直接跳转到已打过的任意层\n"
        "• 材料分层：不同深度掉落不同品质材料\n"
        "• 特殊属性：200级后诡异拥有暴击、连击、反击、抗暴\n"
        "• 宝箱奖励：每10、20、30...层可领取宝箱\n"
        "***\n"
        "**🔍 其他功能**\n"
        f"{cmd('俯瞰 N层诡域', '俯瞰 ')} 查看诡域完整小地图\n"
        f"{cmd('使用 扫荡令')} 扫荡当前诡域获得经验和材料\n"
        f"{cmd('探索宝箱')} 查看可领取的宝箱\n"
        f"{cmd('领取宝箱')} 一键领取所有宝箱\n"
        "***\n"
        "💡 从第1重开始，逐重击败诡异解锁更深诡域\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await fan_ben_cmd.finish(build_markdown(content))

# 交易系统
trade_cmd = on_command("交易系统", aliases={"交易帮助"}, priority=4, block=True)
@trade_cmd.handle()
async def handle_trade(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 交易系统帮助\n"
        "玩家间自由交易平台，支持物品、装备交易和金币转账\n"
        "***\n"
        "**💰 金币转账**\n"
        f"{cmd('转账 UID 金额', '转账 ')} 向其他玩家转账（收取3%手续费）\n"
        "***\n"
        "**🎽 物品交易**\n"
        f"{cmd('交易清单', '交易清单 ')} 查看所有在售与求购物品\n"
        f"{cmd('查牌 物品名', '查牌 ')} 查看物品买卖价格与市场参考\n"
        f"{cmd('挂牌 出售 物品名 单价 数量', '挂牌 ')} 挂牌交易\n"
        f"{cmd('我的挂牌', '我的挂牌 ')} 查看自己的挂牌订单\n"
        f"{cmd('撤牌 挂牌ID', '撤牌 ')} 撤回挂牌\n"
        f"{cmd('挂牌详情 订单ID', '挂牌详情 ')} 查看订单详情\n"
        f"{cmd('税率')} 查看分段累进交易税率\n"
        f"{cmd('市集记录')} 查看最近成交记录\n"
        "***\n"
        "**⚔️ 装备交易**\n"
        f"{cmd('估价 编号', '估价 ')} 查看装备价值评估\n"
        f"{cmd('挂牌 出售 编号 价格', '挂牌 出售 ')} 出售装备实例\n"
        "***\n"
        "**🔄 撮合原理**\n"
        "• 买单匹配价格≤买价的卖单，按价格升序成交\n"
        "• 卖单匹配价格≥卖价的买单，按价格降序成交\n"
        "• 成交价格采用对手方价格（价格优先）\n"
        "• 相同价格按时间先后顺序成交\n"
        "***\n"
        "**💰 交易税收**\n"
        "• 5000以下：免税\n"
        "• 5001-50000：超出部分3%\n"
        "• 50001-200000：超出部分5%\n"
        "• 200000以上：超出部分8%\n"
        "***\n"
        "⚠️ 限制：最多挂6个订单，8小时内购买的物品不能出售\n"
        "💡 转账可用于玩家间金币交易，手续费3%\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await trade_cmd.finish(build_markdown(content))

# 拍卖行系统
auction_help_cmd = on_command("拍卖行系统", aliases={"拍卖帮助", "拍卖行帮助"}, priority=4, block=True)

@auction_help_cmd.handle()
async def handle_auction_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 拍卖行系统帮助\n"
        "稀有高价值物品限时竞价，价高者得\n"
        "***\n"
        "**📋 基本命令**\n"
        f"{cmd('拍卖行', '拍卖行 ')} 查看当前所有进行中的拍卖\n"
        f"{cmd('上架拍卖 物品名 起拍价 时长 [一口价] [宣传语]', '上架拍卖 ')} 发起拍卖\n"
        f"{cmd('出价 拍卖编号 金额', '出价 ')} 参与竞价\n"
        f"{cmd('拍卖详情 拍卖编号', '拍卖详情 ')} 查看竞价历史\n"
        f"{cmd('我的拍卖')} 查看自己发起的拍卖\n"
        f"{cmd('撤拍 拍卖编号', '撤拍 ')} 撤回拍卖（仅无人出价时可用）\n"
        "***\n"
        "**🎮 快速上手（3步）**\n"
        f"1. {cmd('拍卖行')} 浏览当前竞价物品\n"
        f"2. {cmd('出价 编号 金额', '出价 ')} 参与竞价，金币会被冻结\n"
        "3. 拍卖结束后自动结算，被超价则自动退还金币\n"
        "***\n"
        "**📦 上架规则**\n"
        "• 除跑商商品外，所有物品均可上架\n"
        "• 装备（含镶嵌宝石）以实例形式拍卖\n"
        "• 每人同时最多上架 3 件物品\n"
        "• 时长范围：1~72 小时\n"
        "• 起拍价最低：物品系统估价\n"
        "• 一口价（可选）：必须高于起拍价\n"
        "• 宣传语（可选）：最多32字，展示在拍卖列表中\n"
        "***\n"
        "**💰 出价规则**\n"
        "• 每次出价至少高于当前价的 5%\n"
        "• 出价后金币立即冻结，被超价后自动退还\n"
        "• 出价达到一口价，立即成交并获得物品\n"
        "• 不能对自己上架的物品出价\n"
        "***\n"
        "**🏆 结算机制**\n"
        "• 有人竞得：物品转移给买家，卖家获得金币（扣税）\n"
        "• 无人竞价（流拍）：物品退回卖家\n"
        "• 税率：与挂牌市场相同的分段累进税率\n"
        "***\n"
        f"💡 发送 {cmd('交易系统')} 查看挂牌市场帮助\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await auction_help_cmd.finish(build_markdown(content))

# 公会系统
guild_help_cmd = on_command("公会系统", aliases={"公会帮助"}, priority=4, block=True)

@guild_help_cmd.handle()
async def handle_guild_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 公会系统帮助\n"
        "加入公会可以获得公会建筑福利\n"
        "***\n"
        "**🏰 基础功能**\n"
        f"{cmd('创建公会 公会名', '创建公会 ')} 创建公会（消耗会长委任书）\n"
        f"{cmd('我的公会')} 查看公会信息\n"
        f"{cmd('公会列表', '公会列表 ')} 查看所有公会及其会长信息\n"
        f"{cmd('公会成员', '公会成员 ')} 查看成员列表\n"
        f"{cmd('加入公会 公会ID', '加入公会 ')} 加入公会\n"
        f"{cmd('退会')} 退出公会（清空积分和贡献）\n"
        "***\n"
        "**👑 管理功能**\n"
        f"{cmd('申请列表')} 查看待处理申请\n"
        f"{cmd('同意入会 UID', '同意入会 ')} 审核入会\n"
        f"{cmd('设置职位 UID 职位名', '设置职位 ')} 设置成员职位\n"
        f"{cmd('踢出公会 UID', '踢出公会 ')} 踢出成员\n"
        f"{cmd('设置基地')} 设立公会基地（会长，3级+）\n"
        f"{cmd('转让会长 UID', '转让会长 ')} 转让会长职位\n"
        f"{cmd('解散公会')} 解散公会（会长）\n"
        "***\n"
        "**💰 经济系统**\n"
        f"{cmd('捐献金币 金额', '捐献金币 ')} 捐献获得积分\n"
        f"{cmd('公会升级')} 升级公会（会长）\n"
        "***\n"
        "**🏗️ 建筑系统**\n"
        f"{cmd('公会建筑')} 查看建筑列表和加成\n"
        f"{cmd('建造 建筑名', '建造 ')} 建造或升级建筑（会长）\n"
        f"{cmd('公会传送')} 传送到公会基地\n"
        f"{cmd('公会传送 x y', '公会传送 ')} 在基地时传送到势力范围内坐标\n"
        "***\n"
        "**🧪 丹房系统**\n"
        f"{cmd('公会丹房')} 查看丹房产出\n"
        f"{cmd('兑换丹药 丹药名称 数量', '兑换丹药 ')} 用积分兑换丹药\n"
        "💡 存储上限=日产量x3,请及时兑换\n"
        "***\n"
        "**📦 公会仓库**\n"
        f"{cmd('宗门仓库')} 查看仓库物品\n"
        f"{cmd('存入仓库 物品名 数量', '存入仓库 ')} 存入诡异道具\n"
        f"{cmd('取出仓库 物品名 数量', '取出仓库 ')} 取出物品\n"
        f"{cmd('仓库记录')} 查看存取流水（最近20条）\n"
        "💡 需在公会基地操作，仅可存入材料类道具\n"
        "***\n"
        "**📋 任务系统**\n"
        f"{cmd('公会任务')} 查看任务列表和进度\n"
        f"{cmd('完成公会任务')} 领取任务奖励\n"
        f"{cmd('公会任务统计')} 查看任务统计\n"
        "***\n"
        "💡 职位体系：会长>副会长>核心成员>普通成员\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await guild_help_cmd.finish(build_markdown(content))

# 社交系统
social_help_cmd = on_command("社交系统", aliases={"社交帮助"}, priority=4, block=True)

@social_help_cmd.handle()
async def handle_social_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 社交系统帮助\n"
        "送礼传情，结伴江湖，建立深厚的羁绊\n"
        "***\n"
        "**🎁 礼物系统**\n"
        f"{cmd('礼物商店')} 查看可购买的礼物列表\n"
        f"{cmd('买礼物 礼物名 数量', '买礼物 ')} 购买好感度礼物\n"
        f"{cmd('赠礼 UID 礼物名 数量', '赠礼 ')} 赠送好感度礼物(远程,消耗型)\n"
        f"{cmd('转移 UID 物品名 数量', '转移 ')} 当面转移物品\n"
        "• 好感度礼物消耗后转化为好感度和魅力值\n"
        "• 每人对另一人每天最多获得500好感度\n"
        "• 好感度上限10000,达到5000即可结婚/结义\n"
        f"{cmd('送礼记录')} 查看送礼历史\n"
        f"{cmd('收礼记录')} 查看收礼历史\n"
        f"{cmd('好感度', '好感度 ')} 查看好感度记录\n"
        f"{cmd('魅力榜')} 查看全服魅力值排行榜\n"
        f"{cmd('社交统计')} 查看社交系统统计信息\n"
        "***\n"
        "**📋 查询指令(随时随地)**\n"
        f"{cmd('师徒信息')} 查看师徒关系\n"
        f"{cmd('婚姻信息')} 查看婚姻状态\n"
        f"{cmd('结义信息')} 查看结义关系\n"
        "***\n"
        "**💒 结婚系统 - 找月老(临安580,-650)或各集群社交代理**\n"
        f"{cmd('交互 月老 求婚 UID', '交互 月老 求婚 ')} 发起求婚申请\n"
        f"{cmd('交互 月老 求婚申请')} 查看收到的求婚申请\n"
        f"{cmd('交互 月老 同意求婚 UID', '交互 月老 同意求婚 ')} 同意求婚\n"
        f"{cmd('交互 月老 拒绝求婚 UID', '交互 月老 拒绝求婚 ')} 拒绝申请\n"
        f"{cmd('交互 月老 撤销求婚 UID', '交互 月老 撤销求婚 ')} 撤销申请\n"
        f"{cmd('交互 月老 离婚', '交互 月老 离婚')} 单方面离婚(10万金币)\n"
        "• 需要双方好感度5000且在同一地点\n"
        "***\n"
        "**🤝 结义系统 - 找结义使者(长安-500,-280)或各集群社交代理**\n"
        f"{cmd('交互 结义使者 结义 UID', '交互 结义使者 结义 ')} 发起结义申请\n"
        f"{cmd('交互 结义使者 结义申请')} 查看结义申请\n"
        f"{cmd('交互 结义使者 同意结义 UID', '交互 结义使者 同意结义 ')} 同意结义\n"
        f"{cmd('交互 结义使者 断义')} 解除所有结义关系\n"
        "• 3-4人结义：所有人在场立即建立\n"
        "***\n"
        "**👨‍🏫 师徒系统 - 找师徒使者(金陵450,-480)或各集群社交代理**\n"
        f"{cmd('交互 师徒使者 拜师 UID', '交互 师徒使者 拜师 ')} 发起拜师申请\n"
        f"{cmd('交互 师徒使者 拜师申请')} 查看拜师申请\n"
        f"{cmd('交互 师徒使者 同意拜师 UID', '交互 师徒使者 同意拜师 ')} 同意拜师\n"
        f"{cmd('交互 师徒使者 出师 UID', '交互 师徒使者 出师 ')} 让徒弟出师\n"
        f"{cmd('交互 师徒使者 叛师')} 主动叛离师门\n"
        f"{cmd('交互 师徒使者 购买徒弟位')} 500香火扩展1个徒弟位\n"
        f"{cmd('交互 师徒使者 查询')} 查看师徒状况\n"
        "***\n"
        "**💬 NPC对话系统**\n"
        f"{cmd('交互 NPC名字', '交互 ')} 与NPC进行对话\n"
        f"{cmd('对话历史 NPC名字', '对话历史 ')} 查看与NPC的对话历史\n"
        f"{cmd('观察')} 查看当前位置的所有NPC\n"
        "***\n"
        "**💬 消息系统**\n"
        f"{cmd('发消息 内容', '发消息 ')} 发布世界消息\n"
        f"{cmd('发消息 公会 内容', '发消息 公会 ')} 发送公会消息\n"
        f"{cmd('私信 UID 内容', '私信 ')} 给指定玩家发送私信\n"
        f"{cmd('消息')} 查看世界频道\n"
        f"{cmd('消息 私信', '消息 私信')} 查看私信箱\n"
        f"{cmd('消息 公会', '消息 公会')} 查看公会频道\n"
        "💡 需要达到10级才能发言\n"
        "***\n"
        "**🧧 红包系统**\n"
        f"{cmd('发红包 金额 份数', '发红包 ')} 发送金币红包\n"
        f"{cmd('抢红包')} 抢当前群的红包\n"
        f"{cmd('红包记录')} 查看本群最近红包记录\n"
        "• 每群同时只有一个活跃红包\n"
        "• 红包10分钟过期自动退还\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await social_help_cmd.finish(build_markdown(content))

# 每日任务系统
daily_task_help_cmd = on_command("委托系统", aliases={"任务系统", "委托帮助"}, priority=4, block=True)

@daily_task_help_cmd.handle()
async def handle_daily_task_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 委托系统帮助\n"
        "大都会缉邪司每日颁发退邪委托，以恶鬼身，行菩萨事\n"
        "***\n"
        "**📋 基础功能**\n"
        f"{cmd('每日委托')} 查看今日所有委托详情\n"
        f"{cmd('接取委托 编号', '接取委托 ')} 接取指定委托\n"
        f"{cmd('完成委托')} 在目标位置完成委托\n"
        f"{cmd('刷新委托')} 生成新委托（每日最多3个）\n"
        f"{cmd('委托统计')} 查看完成统计\n"
        "***\n"
        "**🏛️ 任务流程**\n"
        f"1. {cmd('每日委托')} 查看委托\n"
        f"2. {cmd('接取委托 编号', '接取委托 ')} 接取任务\n"
        "3. 导航到任务坐标位置\n"
        f"4. {cmd('观察')} 查看鬼怪NPC\n"
        f"5. {cmd('攻击 鬼怪名字', '攻击 ')} 击杀目标\n"
        f"6. {cmd('完成委托')} 领取奖励\n"
        "***\n"
        "💰 奖励：经验、金币、公会积分和经验\n"
        "🎭 任务类型：鬼怪消除、笔仙案件、邪修蛊惑等\n"
        "📅 每日最多接取3个委托，次日过期\n"
        "***\n"
        "**🎯 智能匹配**\n"
        "• 遇到重名NPC时，系统自动优先匹配你的任务目标\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await daily_task_help_cmd.finish(build_markdown(content))


# 抽奖系统
lottery_help_cmd = on_command("抽奖系统", aliases={"抽奖帮助"}, priority=4, block=True)

@lottery_help_cmd.handle()
async def handle_lottery_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 抽奖系统帮助\n"
        "管理员发起，玩家参与\n"
        "***\n"
        "**👥 玩家指令**\n"
        f"{cmd('参与抽奖 抽奖ID', '参与抽奖 ')} 参与指定抽奖活动\n"
        f"{cmd('抽奖详情 抽奖ID', '抽奖详情 ')} 查看抽奖详情和中奖名单\n"
        f"{cmd('我的抽奖')} 查看我参与的抽奖记录\n"
        "***\n"
        "**🔧 管理员指令**\n"
        f"{cmd('发起抽奖 物品名 中奖人数 每人数量', '发起抽奖 ')} 发起抽奖活动\n"
        f"{cmd('开奖 抽奖ID', '开奖 ')} 进行开奖并发放奖品\n"
        f"{cmd('取消抽奖 抽奖ID', '取消抽奖 ')} 取消抽奖并退还奖品\n"
        "***\n"
        "**📝 说明**\n"
        "• 发起抽奖时会从管理员背包扣除奖品\n"
        "• 可设置最低等级要求，防止小号参与\n"
        "• 可添加活动描述，用 - 开头\n"
        "• 参与人数少于中奖人数时，全部参与者中奖\n"
        "• 发起人不能参与自己发起的抽奖\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await lottery_help_cmd.finish(build_markdown(content))

# 管理员系统
admin_help_cmd = on_command("管理员系统", aliases={"管理员帮助", "管理指令"}, priority=4, block=True, permission=SUPERUSER)

@admin_help_cmd.handle()
async def handle_admin_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 管理员系统帮助\n"
        "超级管理员专用指令\n"
        "***\n"
        "**🔧 物品管理**\n"
        f"{cmd('发物品 UID 物品名 数量', '发物品 ')} 给玩家发放物品\n"
        f"{cmd('发装备 UID 装备名 数量', '发装备 ')} 给玩家发放装备\n"
        f"{cmd('发诡烛 UID 数量', '发诡烛 ')} 给玩家发放诡烛\n"
        f"{cmd('转移物品 UID1 UID2 物品名 数量', '转移物品 ')} 转移物品\n"
        "***\n"
        "**🎁 抽奖系统**\n"
        f"{cmd('发起抽奖 物品名 中奖人数 每人数量', '发起抽奖 ')} 发起抽奖活动\n"
        f"{cmd('开奖 抽奖ID', '开奖 ')} 进行开奖（仅发起人）\n"
        f"{cmd('抽奖详情 抽奖ID', '抽奖详情 ')} 查看抽奖详情\n"
        f"{cmd('取消抽奖 抽奖ID', '取消抽奖 ')} 取消抽奖并退还奖品\n"
        "***\n"
        "**📊 数据统计**\n"
        f"{cmd('材料统计')} 查看全服材料分布统计\n"
        f"{cmd('材料详情 材料名', '材料详情 ')} 查看指定材料详细分布\n"
        "***\n"
        "**🔍 日志管理**\n"
        f"{cmd('查看报错', '查看报错 ')} 查看最近的报错日志\n"
        f"{cmd('最近报错')} 查看最近的报错日志\n"
        f"{cmd('最近活动', '最近活动 ')} 查看全服最近活动\n"
        "***\n"
        "**💾 备份管理**\n"
        f"{cmd('手动备份')} 立即创建MySQL数据库备份\n"
        f"{cmd('备份状态')} 查看备份文件列表\n"
        f"{cmd('恢复备份 序号/文件名', '恢复备份 ')} 从备份恢复数据库\n"
        "  • 每天凌晨4:00自动备份\n"
        "***\n"
        "**🖼️ 物品图片管理**\n"
        f"{cmd('设置物品图片 物品名 图片URL', '设置物品图片 ')} 设置/覆盖物品图片\n"
        f"{cmd('删除物品图片 物品名', '删除物品图片 ')} 删除物品图片配置\n"
        f"{cmd('物品图片列表')} 查看所有已配置的物品图片\n"
        "***\n"
        "**🛠️ 工坊维护**\n"
        f"{cmd('刷新工坊清单')} 覆盖更新所有城镇的锻造清单\n"
        "***\n"
        "**💹 气运系统管理**\n"
        f"{cmd('初始化气运')} 初始化气运系统\n"
        f"{cmd('更新气运价格')} 手动刷新所有气运价格\n"
        f"{cmd('触发黑天鹅')} 手动触发黑天鹅事件检查\n"
        "***\n"
        "**🚫 封禁管理**\n"
        f"{cmd('禁言 UID 原因 时长', '禁言 ')} 禁言玩家\n"
        f"{cmd('解禁 UID', '解禁 ')} 解除禁言\n"
        f"{cmd('黑名单')} 查看当前黑名单\n"
        f"{cmd('删除留言 留言ID', '删除留言 ')} 删除恶意留言\n"
        f"{cmd('封禁 UID 原因 时长', '封禁 ')} 全局封禁玩家\n"
        f"{cmd('解封 UID', '解封 ')} 解除全局封禁\n"
        f"{cmd('封禁列表')} 查看所有被封禁的玩家\n"
        f"{cmd('封禁信息 UID', '封禁信息 ')} 查看玩家封禁详情\n"
        "💡 时长格式：3d（3天）、24h（24小时）、永久\n"
        "***\n"
        "**🏰 公会管理**\n"
        f"{cmd('删除公会 公会ID', '删除公会 ')} 全面删除公会及其所有数据\n"
        "⚠️ 删除公会操作不可逆！\n"
        "***\n"
        "**🎆 活动管理**\n"
        f"{cmd('开启活动', '开启活动 ')} 开启除夕叩门活动\n"
        f"{cmd('关闭活动')} 关闭除夕叩门活动\n"
        "***\n"
        "**🤖 AI数据库操作**\n"
        f"{cmd('管理员要求 需求描述', '管理员要求 ')} 用自然语言查询/修改数据库\n"
        "⚠️ 支持SELECT和UPDATE，禁止DELETE/DROP等危险操作\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await admin_help_cmd.finish(build_markdown(content))

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
        "🔸 88诡烛 - 基础月卡（30天）\n"
        "   • 修炼闭关效率+20%\n"
        "   • 闭关上限增加至9小时，突破失败损失减少5%\n"
        "   • 背包扩容+5格\n"
        "   • 签到获得月卡宝箱*1，咒抗+5\n"
        "   • 一键献祭、一键修复装备\n"
        "🔸 288诡烛 - 高级月卡（30天）\n"
        "   • 修炼闭关效率+50%\n"
        "   • 闭关上限增加至12小时，突破失败损失减少10%\n"
        "   • 背包扩容+20格\n"
        "   • 副本自动采集、装备一键修理、一键献祭\n"
        "   • 签到获得月卡宝箱*3，咒抗+5\n"
        "🔸 10诡烛 - 背包永久扩容1格\n"
        "🔸 50诡烛 - 棺材钉\n"
        "   • 持有者增加0.5%修炼效率，上限50%\n"
        "🔸 20诡烛 - 哭坟帽\n"
        "   • 使用后直接获得1w怨念值\n"
        "🔸 改名卡 10诡烛 | 自定义称号 500诡烛\n"
        "🔸 1000诡烛 - 重启符\n"
        "   • 重置所有已分配属性点，可重新分配\n"
        "   • 装备加成、丹药加成、VIP加成均保留\n"
        "━━━━━━━━━━━━━\n"
        "🐾 宠物饰品（诡烛专属）：\n"
        "🔸 150诡烛 - 虚空锁链/诡纹和服（紫色饰品）\n"
        "🔸 300诡烛 - 星辰发冠/银铃璎珞/流光羽衣（橙色饰品）\n"
        "   • 购买：【买饰品 名称】\n"
        "━━━━━━━━━━━━━\n"
        "🕯️ 赞助特权（180诡烛/月≈18元）：\n"
        "🔸 闭关无上限 - 【购买闭关特权】\n"
        "🔸 远程仓库 - 【购买远程仓库】随地存取阴宅仓库\n"
        "🔸 鱼竿特权 - 【购买鱼竿特权】每次多钓2条\n"
        "🔸 全视之眼 - 【购买全视之眼】俯瞰显示诡域全图\n"
        "━━━━━━━━━━━━━\n"
        "🕯️ 诡烛兑换比例1:10，【赞助商店】购买服务\n"
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


# ------------------ 管理员：发诡烛 ------------------

give_guizhu_cmd = on_command("发诡烛", aliases={"给诡烛", "增加诡烛"}, priority=2, block=True, permission=SUPERUSER)


@give_guizhu_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：发诡烛 UID 数量"""
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await give_guizhu_cmd.finish("格式：发诡烛 UID 数量")

    uid_str, amount_str = parts[0], parts[1]

    if not uid_str.isdigit():
        await give_guizhu_cmd.finish("UID 必须为数字")
    if not amount_str.isdigit() or int(amount_str) < 1:
        await give_guizhu_cmd.finish("数量必须为正整数")

    target_uid = int(uid_str)
    amount = int(amount_str)

    async with safe_session() as session:
        from sqlalchemy import select
        from datetime import datetime
        from ..models.world_message import WorldMessage

        player = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not player:
            await give_guizhu_cmd.finish(f"❌ 未找到 UID 为 {target_uid} 的玩家")

        player.gui_zhu += amount

        # 给玩家发送系统私信通知诡烛到账
        notice = WorldMessage(
            player_id="SYSTEM",
            recipient_id=player.id,
            scope="private",
            content=f"🕯️ 诡烛到账通知：您已收到 {amount} 诡烛，当前余额 {player.gui_zhu}。感谢支持！",
            created_at=datetime.now(),
        )
        session.add(notice)
        await session.commit()

        await give_guizhu_cmd.finish(
            f"✅ 已给予 UID:{target_uid}({player.nickname}) 诡烛 ×{amount}\n"
            f"💎 当前诡烛：{player.gui_zhu}\n"
            f"📬 已发送到账通知至玩家私信"
        )


# ==================== 账号管理帮助 ====================
account_help_cmd = on_command("账号管理", aliases={"账号帮助", "账号系统"}, block=True, priority=5)

@account_help_cmd.handle()
async def handle_account_help(event: MessageEvent, args: Message = CommandArg()):
    """账号切换系统帮助"""
    content = (
        "# 账号管理系统\n"
        "支持多账号切换和管理\n"
        "***\n"
        "**📋 账号查看**\n"
        f"{cmd('我的账号')} 查看拥有的所有游戏账号\n"
        f"{cmd('账号列表')} 同上\n"
        "***\n"
        "**🔄 账号切换**\n"
        f"{cmd('切换账号 UID', '切换账号 ')} 切换到指定的游戏账号\n"
        "• 只能切换到自己拥有的账号\n"
        "• 每次只能激活一个账号\n"
        "• 切换后所有命令自动使用激活账号\n"
        "***\n"
        "**✏️ 账号管理**\n"
        f"{cmd('重命名账号 UID 新名称', '重命名账号 ')} 设置账号备注名\n"
        "• 备注名最长32字符\n"
        "***\n"
        "**📊 历史记录**\n"
        f"{cmd('转让历史')} 查看账号买入/卖出历史\n"
        "***\n"
        "**🔑 账号买卖（仅管理员）**\n"
        "如需买卖账号，请联系管理员操作\n"
        f"{cmd('生成转让密钥 UID', '生成转让密钥 ')} 生成转让密钥\n"
        f"{cmd('接收账号 转让密钥', '接收账号 ')} 接收账号\n"
        f"{cmd('取消转让 UID', '取消转让 ')} 取消转让\n"
        "***\n"
        "💡 多号管理：在一个QQ号下管理多个游戏角色\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await account_help_cmd.finish(build_markdown(content))


# ==================== 完整帮助图片生成 ====================

# 各系统指令数据：(系统名, 标题颜色, 指令列表)
_FULL_HELP_SYSTEMS = [
    ("修炼系统", "#8b5cf6", [
        "【修炼】 【闭关】 【出关】",
        "【突破】 【突破 镇厄/棺材钉】",
        "【加点 属性 点数】 【加点帮助】",
        "【献祭 材料 数量】",
        "【焚金 金额】",
        "【面板】 【战力】 【战力说明】",
    ]),
    ("玩家系统", "#8b5cf6", [
        "【注册 男/女】 【改名 名字】",
        "【面板 UID】 【完整面板 UID】",
        "【排行榜】 【财富榜】 【修为榜】",
        "【幸运榜】 【探索榜】 【魅力榜】",
        "【成就 页码/名称】 【邀请码】",
    ]),
    ("战斗系统", "#ef4444", [
        "【切磋 UID】 【攻击 UID/NPC】",
        "【世界BOSS】 【讨伐BOSS】",
        "【BOSS排行】 【死斗日志】",
        "【战力】 【战力说明】 【日志模式】",
    ]),
    ("装备系统", "#ef4444", [
        "【装备栏】 【装备/卸下 名称】",
        "【修理 名称】 【一键卸下】",
        "【锻造列表】 【配方】 【锻造 名称】",
        "【升阶 名称】 【一键升阶 名称 目标阶数】",
        "【升阶信息】 【升阶列表】",
        "【孔位 名称】 【镶嵌】 【镶嵌物品】",
        "【合成镶嵌物】 【总部商店】",
    ]),
    ("背包系统", "#22c55e", [
        "【背包】 【背包 类别】",
        "【使用 物品名 数量】",
        "【一键嗑药】 【整理背包】",
        "【图鉴 物品名】 【耐药性】",
        "【欺骗 源材料 目标材料 数量】",
    ]),
    ("探索系统", "#3b82f6", [
        "【地图】 【可视化地图】",
        "【导航 地点名/x y】 【中断导航】",
        "【附近地点】 【附近玩家】",
        "【观察】 【交互 NPC名】",
        "【查找 NPC名】 【本周主题】",
    ]),
    ("经济系统", "#eab308", [
        "【市集】 【购买 物品 数量】",
        "【出售 物品 数量】 【自动出售】",
        "【市价 物品名】 【跑商推荐】",
        "【跑商记录】 【交易限制】",
        "【黑市】 【食材铺】 【市集列表】",
        "【存/取 金额】 【余额】",
        "【转账 UID 金额】",
        "【理财产品】 【我的理财】",
    ]),
    ("投资系统", "#eab308", [
        "【投资行情】 【投资刷新时间】",
        "【投资气运 代码 数量】",
        "【出售气运 代码 数量】",
        "【我的投资】 【投资记录】",
        "【气运事件】",
    ]),
    ("交易系统", "#f59e0b", [
        "【交易清单】 【查牌 物品名】",
        "【挂牌 出售/收购 物品 价格 数量】",
        "【我的挂牌】 【撤牌 ID】",
        "【挂牌详情 订单ID】 【估价 名称】 【税率】 【市集记录】",
    ]),
    ("打工系统", "#22c55e", [
        "【打工】 【打工 工作名】 【收工】",
        "【工作状态】 【工作地点】",
        "【打工记录】 【打工统计】",
    ]),
    ("公会系统", "#ec4899", [
        "【我的公会】 【公会列表】",
        "【加入公会 ID】 【退会】",
        "【公会建筑】 【建造 建筑名】",
        "【公会传送】 【捐献金币 金额】",
        "【公会任务】 【完成公会任务】",
        "【公会丹房】 【兑换丹药 名称 数量】",
    ]),
    ("社交系统", "#ec4899", [
        "【礼物商店】 【买礼物 名称 数量】",
        "【赠礼 UID 名称 数量】",
        "【转移 UID 物品名 数量】",
        "【好感度 UID】 【社交统计】",
        "【交互 月老/结义使者/师徒使者】",
        "【发消息 内容】 【私信 UID 内容】",
        "【发红包 金额 份数】 【抢红包】",
    ]),
    ("副本系统", "#3b82f6", [
        "【进入 N层诡域】 【诡域】",
        "【探索】 【上/下/左/右】",
        "【传送 N层诡域】（诡域内免咒抗跳层）",
        "【俯瞰 N层诡域】 【领取宝箱】",
        "【使用 扫荡令】 【返回】",
    ]),
    ("阴宅系统", "#3b82f6", [
        "【阴宅】 【购买阴宅】 【升级阴宅】",
        "【迁移阴宅】 【设置阴宅费用 金额】",
        "【切换阴宅权限】 【切换阴宅付费意愿】",
        "【阴宅仓库】 【存入阴宅 物品 数量】",
        "【取出阴宅 序号 数量】",
    ]),
    ("钓鱼系统", "#06b6d4", [
        "【钓鱼】 【钓鱼状态】 【钓鱼概率】",
        "【钓鱼记录】 【钓鱼排行】 【钓鱼图鉴】",
        "【鱼栏】 【吃鱼 鱼名 数量】",
        "【丢弃 鱼名 数量】",
    ]),
    ("炼丹系统", "#06b6d4", [
        "【丹方 页数/关键词】 【炼丹状态】",
        "【炼丹 名称/序号 数量】",
        "【收获丹药】",
    ]),
    ("委托系统", "#84cc16", [
        "【每日委托】 【刷新委托】",
        "【接取委托 编号】",
        "【完成委托】 【委托统计】",
    ]),
    ("烹饪餐厅", "#f97316", [
        "【创建餐厅】 【餐厅】 【开店/打烊】",
        "【招募厨师】 【雇佣 编号】",
        "【烹饪 菜名 数量】 【食谱】",
        "【补货/取货 食材名 数量】",
        "【设置菜单 菜名...】 【菜单】",
        "【经营报表】 【经营日志】 【菜品利润】",
    ]),
    ("娱乐系统", "#14b8a6", [
        "【签到】 【月卡】 【邀请码】",
        "【抽签 问题】 【答案之书 问题】",
        "【每日一言】 【今天吃什么】",
        "【驾考题目】 【微博热搜】",
        "【恶魔轮盘帮助】 【试炼列表】 【已通关试炼】",
        "【猜拳 石头/剪刀/布 金额】（周六）",
        "【人机轮盘 金额】（私聊）",
    ]),
    ("抽奖系统", "#14b8a6", [
        "【参与抽奖 ID】",
        "【抽奖详情 ID】",
        "【我的抽奖】",
    ]),
    ("灵田系统", "#84cc16", [
        "【开辟灵田】 【灵田】 【灵田升级】",
        "【种植 作物名 地块号】 【一键种植】",
        "【浇水 地块号】 【一键浇水】 【收菜】",
        "【偷菜 UID】 【偷菜记录】",
        "【种子商店】 【买种子 名称 数量】",
        "【菜市场】 【卖菜 作物名 数量】",
        "【买诡兽 名称】 【放置诡兽】",
    ]),
    ("天灾系统", "#10b981", [
        "【降临】 【镇守】 【迎战】 【侦查】",
        "【天灾商店】 【兑换 商品名】",
    ]),
    ("账号管理", "#94a3b8", [
        "【我的账号】 【账号列表】",
        "【切换账号 UID】",
        "【重命名账号 UID 新名称】",
        "【转让历史】",
    ]),
    ("赞助系统", "#94a3b8", [
        "【赞助】 查看月卡权益和购买方式",
        "【月卡】 当前月卡状态",
        "【赞助商店】 诡烛购买服务",
        "【购买重启符 N】 1000诡烛/张，洗点用",
        "【购买闭关特权】 闭关无上限 180诡烛/月",
        "【购买远程仓库】 随地存取阴宅仓库 180诡烛/月",
        "【购买鱼竿特权】 每次多钓2条 180诡烛/月",
        "【购买全视之眼】 俯瞰全图 180诡烛/月",
        "【切换称号 称号名】 【卸下称号】",
    ]),
]


def _generate_full_help_image():
    """动态生成完整帮助图片，返回 base64 字符串；失败返回 None"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64 as b64_mod
    except ImportError:
        return None

    # ------ 字体加载 ------
    def _load_font(size: int):
        for fp in [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_title    = _load_font(34)
    font_subtitle = _load_font(15)
    font_header   = _load_font(16)
    font_cmd      = _load_font(13)

    # ------ 布局常量 ------
    COLS         = 3
    IMG_W        = 1200
    SIDE_M       = 15   # 两侧留边
    COL_GAP      = 12   # 列间距
    COL_W        = (IMG_W - SIDE_M * 2 - COL_GAP * (COLS - 1)) // COLS  # ≈ 382
    TITLE_H      = 72
    SEC_HDR_H    = 28   # 每个系统标题行高
    CMD_LINE_H   = 19   # 每行指令高度
    SEC_PAD      = 8    # 卡片内上下留白
    SEC_GAP      = 6    # 卡片间距
    FOOTER_H     = 32

    def _sec_h(cmds):
        return SEC_HDR_H + SEC_PAD * 2 + len(cmds) * CMD_LINE_H

    # 均匀分配到3列（交错分配）
    cols_data = [_FULL_HELP_SYSTEMS[i::COLS] for i in range(COLS)]
    max_col_h  = max(
        sum(_sec_h(s[2]) + SEC_GAP for s in col) - SEC_GAP
        for col in cols_data
    )
    IMG_H = TITLE_H + 10 + max_col_h + 10 + FOOTER_H

    # ------ 颜色工具 ------
    def _hex(c: str):
        return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))

    def _dim(c: str, factor=0.18):
        r, g, b = _hex(c)
        return (int(r * factor), int(g * factor), int(b * factor))

    # ------ 绘制图片 ------
    img  = Image.new("RGB", (IMG_W, IMG_H), color=(13, 17, 23))
    draw = ImageDraw.Draw(img)

    # 标题区背景渐变
    for y in range(TITLE_H):
        t = y / TITLE_H
        r = int(0x1a + (0x2d - 0x1a) * t)
        g = int(0x0a + (0x10 - 0x0a) * t)
        b = int(0x2e + (0x50 - 0x2e) * t)
        draw.rectangle([(0, y), (IMG_W, y)], fill=(r, g, b))

    # 标题文字（不依赖 anchor，兼容老版 Pillow）
    title_text = "诡修仙  完整指令手册"
    try:
        tw = draw.textlength(title_text, font=font_title)
    except AttributeError:
        tw = font_title.getlength(title_text) if hasattr(font_title, 'getlength') else len(title_text) * 20
    draw.text(((IMG_W - tw) // 2, 10), title_text, fill=(255, 255, 255), font=font_title)

    sub_text = f"共 {len(_FULL_HELP_SYSTEMS)} 个系统  发送【系统名】查看详细帮助  官群:962494679"
    try:
        sw = draw.textlength(sub_text, font=font_subtitle)
    except AttributeError:
        sw = len(sub_text) * 8
    draw.text(((IMG_W - sw) // 2, 50), sub_text, fill=(139, 148, 158), font=font_subtitle)

    # 各系统卡片
    y_base = TITLE_H + 10
    for col_idx, col_systems in enumerate(cols_data):
        x = SIDE_M + col_idx * (COL_W + COL_GAP)
        y = y_base
        for sys_name, sys_color, cmds in col_systems:
            h = _sec_h(cmds)
            # 卡片背景
            try:
                draw.rounded_rectangle(
                    [(x, y), (x + COL_W, y + h)],
                    radius=5, fill=(22, 27, 34), outline=_hex(sys_color), width=1
                )
            except AttributeError:
                draw.rectangle([(x, y), (x + COL_W, y + h)], fill=(22, 27, 34), outline=_hex(sys_color))

            # 标题背景
            hdr_bg = _dim(sys_color)
            try:
                draw.rounded_rectangle(
                    [(x, y), (x + COL_W, y + SEC_HDR_H)],
                    radius=5, fill=hdr_bg
                )
                draw.rectangle(
                    [(x, y + SEC_HDR_H - 5), (x + COL_W, y + SEC_HDR_H)],
                    fill=hdr_bg
                )
            except AttributeError:
                draw.rectangle([(x, y), (x + COL_W, y + SEC_HDR_H)], fill=hdr_bg)

            # 标题文字居中
            try:
                htw = draw.textlength(sys_name, font=font_header)
            except AttributeError:
                htw = len(sys_name) * 10
            hdr_x = x + (COL_W - htw) // 2
            draw.text((hdr_x, y + (SEC_HDR_H - 16) // 2), sys_name, fill=_hex(sys_color), font=font_header)

            # 指令列表
            cy = y + SEC_HDR_H + SEC_PAD
            for cmd in cmds:
                draw.text((x + 7, cy), cmd, fill=(201, 209, 217), font=font_cmd)
                cy += CMD_LINE_H

            y += h + SEC_GAP

    # 底部
    draw.rectangle([(0, IMG_H - FOOTER_H), (IMG_W, IMG_H)], fill=(22, 27, 34))
    footer_text = "发送【帮助】查看功能模块导航  |  发送【新手指引】查看新手成长路线"
    try:
        ftw = draw.textlength(footer_text, font=font_subtitle)
    except AttributeError:
        ftw = len(footer_text) * 8
    draw.text(((IMG_W - ftw) // 2, IMG_H - FOOTER_H + 8), footer_text, fill=(139, 148, 158), font=font_subtitle)

    # 导出 base64
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return b64_mod.b64encode(buf.getvalue()).decode("utf-8")


# ==================== 完整帮助系统 ====================
_cached_full_help_image: str | None = None  # 帮助图片缓存，内容固定无需重复生成

full_help_cmd = on_command("完整帮助", aliases={"全部帮助", "帮助大全"}, priority=5, block=True)

@full_help_cmd.handle()
async def handle_full_help(event: MessageEvent, args: Message = CommandArg()):
    """
    完整帮助 - 优先发送图片版，生成失败时降级为文字版
    """
    global _cached_full_help_image
    if _cached_full_help_image is None:
        _cached_full_help_image = await asyncio.to_thread(_generate_full_help_image)
    img_b64 = _cached_full_help_image
    if img_b64:
        await full_help_cmd.finish(Message([MessageSegment.file_image(img_b64)]))

    # 降级文字版（PIL 不可用时）
    sections = []
    for sys_name, _, cmds in _FULL_HELP_SYSTEMS:
        sections.append(f"**{sys_name}**\n" + "\n".join(cmds))
    content = (
        f"# 完整帮助系统\n"
        f"共 {len(_FULL_HELP_SYSTEMS)} 个系统\n"
        "***\n"
        + "\n***\n".join(sections)
        + "\n***\n"
        f"💡 发送 {cmd('帮助')} 查看功能模块导航\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await full_help_cmd.finish(build_markdown(content))


# 里界系统
inner_realm_help_cmd = on_command("里界系统", aliases={"里界帮助"}, priority=4, block=True)

@inner_realm_help_cmd.handle()
async def handle_inner_realm_help(event: MessageEvent, args: Message = CommandArg()):
    """
    里界系统帮助
    """
    content = (
        "# 里界系统\n"
        "诡域深处的凝固时空，修炼者的试炼之地\n"
        "***\n"
        "**🌌 核心玩法**\n"
        "• 场景节点探索（非坐标移动）\n"
        "• 2D6骰子判定系统\n"
        "• 修为被压制为凡人，靠智慧存活\n"
        "• 多结局结算\n"
        "• 死亡=空手而归\n"
        "***\n"
        "**📍 基础命令**\n"
        f"{cmd('里界')} 查看可进入的里界列表\n"
        f"{cmd('传送 里界名', '传送 ')} 进入指定里界\n"
        f"{cmd('前往 场景名', '前往 ')} 移动到指定场景\n"
        f"{cmd('前往')} 查看可前往的场景列表\n"
        f"{cmd('观察')} 仔细查看当前场景（发现隐藏线索）\n"
        f"{cmd('里界信息')} 查看当前探索状态\n"
        f"{cmd('返回')} 离开里界并结算结局\n"
        "***\n"
        "**🎯 互动命令**\n"
        f"{cmd('搜刮')} 搜索当前场景（2D6+属性判定）\n"
        f"{cmd('威吓')} 威吓NPC（2D6+属性判定）\n"
        f"{cmd('处决')} 静默击杀NPC（2D6+属性判定）\n"
        f"{cmd('交谈')} 与NPC对话，获取信息\n"
        f"{cmd('选择 选项名', '选择 ')} 在特殊事件中做出选择\n"
        f"{cmd('休息')} 在安全场景休息恢复理智\n"
        "***\n"
        "**🎒 道具命令**\n"
        f"{cmd('道具')} 查看里界内持有的道具\n"
        f"{cmd('使用 道具名', '使用 ')} 使用道具（如过期罐头恢复理智）\n"
        f"{cmd('查看线索')} 查看所有已收集的线索\n"
        "***\n"
        "**🎲 骰子判定**\n"
        "• 投掷2个D6骰子 + 属性修正\n"
        "• 2-3 大失败 | 4-6 失败 | 7-9 普通成功\n"
        "• 10-11 成功 | 12+ 大成功\n"
        "***\n"
        "**🧠 理智系统**\n"
        "• 初始理智100，归零则试炼失败\n"
        "• 搜刮失败、遭遇鬼怪会损失理智\n"
        "• 使用过期罐头可恢复10点理智\n"
        "***\n"
        "**🏆 结局系统**\n"
        "• 黎明幸存者：存活到黎明（x1.5奖励）\n"
        "• 真相揭示者：收集全部线索（x2.5奖励）\n"
        "• 屠镇者：击杀所有凡人NPC（x2.0奖励）\n"
        "• 猎物：被杀死（清零）\n"
        "• 理智崩溃：理智归零（清零）\n"
        "***\n"
        "**🌍 可用里界**\n"
        "• 荔湾鬼镇（Lv.50）- 凝固时空中的恐怖小镇\n"
        "***\n"
        "**💡 提示**\n"
        "• 天黑后不能在户外停留，否则必死\n"
        "• 鬼怪无法正面对抗，只能智取或规避\n"
        "• 线索收集进度永久保存，死亡不会丢失\n"
        "• 物品和金币在死亡时清零，存活才能带走\n"
        "• 首次通关有额外奖励\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await inner_realm_help_cmd.finish(build_markdown(content))


# 灵田系统
spirit_field_help_cmd = on_command("灵田系统", aliases={"灵田帮助"}, priority=4, block=True)

@spirit_field_help_cmd.handle()
async def handle_spirit_field_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 灵田系统\n"
        "开辟灵田种植灵蔬诡药，收获食材与炼丹材料\n"
        "***\n"
        "**🌱 灵田管理**\n"
        f"{cmd('开辟灵田')} 创建灵田（免费，每人一块）\n"
        f"{cmd('灵田')} 查看灵田状态（地块/作物/诡兽）\n"
        f"{cmd('灵田升级')} 升级灵田（解锁更多地块）\n"
        "***\n"
        "**🌿 种植操作**\n"
        f"{cmd('种植 作物名 地块号', '种植 ')} 在指定地块种植\n"
        f"{cmd('一键种植 作物名', '一键种植 ')} 所有空地块种植\n"
        f"{cmd('浇水 地块号', '浇水 ')} 浇水指定地块（减15%成长时间）\n"
        f"{cmd('一键浇水')} 浇水所有已种地块\n"
        f"{cmd('收菜')} 收获所有成熟作物\n"
        "***\n"
        "**🛒 种子商店**\n"
        f"{cmd('种子商店')} 查看可购买种子\n"
        f"{cmd('买种子 名称 数量', '买种子 ')} 购买种子\n"
        "***\n"
        "**💰 灵蔬市场**\n"
        f"{cmd('菜市场')} 查看当前灵蔬/诡药收购价（每小时变化）\n"
        f"{cmd('卖菜 作物名 数量', '卖菜 ')} 按市场价出售作物\n"
        "价格每小时动态变化，晚市18-22点价格最高\n"
        "***\n"
        "**🥷 偷菜**\n"
        f"{cmd('拜访灵田 UID', '拜访灵田 ')} 查看他人灵田状态\n"
        f"{cmd('偷菜', '偷菜 ')} 查看可偷目标/偷指定玩家\n"
        f"{cmd('偷菜记录', '偷菜记录 ')} 查看偷菜日志\n"
        "• 每日5次，同人每日1次，每次最多偷20%\n"
        "***\n"
        "**🐾 诡兽守田**\n"
        f"{cmd('派遣守田')} 派遣宠物伙伴守田\n"
        f"{cmd('召回宠物')} 召回守田中的宠物\n"
        f"• 详细功能见 {cmd('宠物系统')}\n"
        "***\n"
        "**📊 灵田等级**\n"
        "1级4块 -> 2级6块 -> ... -> 9级20块\n"
        "升级解锁更多地块和高级灵种\n"
        "***\n"
        "**🏠 阴宅联动**\n"
        "阴宅等级越高，灵田加成越强（种植时自动生效）\n"
        "• 成长加速：1级5% -> 5级25% -> 10级40% -> 30级70%\n"
        "• 产量加成：10级25% -> 20级45% -> 30级55%\n"
        "***\n"
        "**🍳 烹饪联动**\n"
        "灵蔬可作为烹饪食材，搭配新食谱\n"
        "种植 -> 收菜 -> 补货到餐厅 -> 烹饪出售\n"
        "***\n"
        "💡 灵蔬联动烹饪，诡药联动炼丹\n"
        "💡 浇水每地块每日3次，冷却30分钟\n"
        "💡 收菜有10%概率额外获得1颗同种种子\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await spirit_field_help_cmd.finish(build_markdown(content))

# 下位世界·第四天灾系统
lower_world_help_cmd = on_command("天灾系统", aliases={"天灾帮助", "下位世界帮助"}, priority=4, block=True)

@lower_world_help_cmd.handle()
async def handle_lower_world_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 下位世界 - 第四天灾\n"
        "降临下位世界，成为山寨之主，击退来犯英雄\n"
        "***\n"
        "**🏰 基础命令**\n"
        f"{cmd('降临')} 降临下位世界，首次使用建立山寨\n"
        f"{cmd('镇守')} 查看天灾山寨状态\n"
        "***\n"
        "**⚔️ 战斗系统**\n"
        f"{cmd('迎战')} 与当前波次的英雄战斗（1v1）\n"
        f"{cmd('侦查')} 消耗10天灾点，查看英雄详细属性\n"
        "• 击败英雄：获得天灾点奖励\n"
        "• 被英雄击败：封印12小时 + 波次降低3波\n"
        "• 超时未战：英雄自动撤退，无奖励\n"
        "• 英雄每2小时来一波，4小时内不迎战则撤退\n"
        "***\n"
        "**💰 天灾商店**\n"
        f"{cmd('天灾商店')} 查看可兑换的专属福利\n"
        f"{cmd('兑换 商品名', '兑换 ')} 花费天灾点购买商品\n"
        "***\n"
        "**📊 玩法机制**\n"
        "• 英雄波次：每2小时刷新一波英雄\n"
        "• 天灾点获取：击败英雄获得，用于兑换福利\n"
        "• 战斗规则：不消耗真实HP，模拟战斗\n"
        "• 失败降波：战败后波次-3，降低难度重新挑战\n"
        "• 解封令：天灾商店花40天灾点立即解除封印\n"
        "***\n"
        "💡 英雄强度随波次递增，准备充分再迎战\n"
        "💡 首次降临免费建立山寨\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await lower_world_help_cmd.finish(build_markdown(content))


# 宠物伙伴系统
pet_help_cmd = on_command("宠物系统", aliases={"宠物帮助"}, priority=4, block=True)

@pet_help_cmd.handle()
async def handle_pet_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 宠物伙伴系统\n"
        "驯化诡兽为宠物伙伴，聊天、养成、打扮、战斗!\n"
        "***\n"
        "**🐾 获取与管理**\n"
        f"{cmd('驯化诡兽 名称 昵称', '驯化诡兽 ')} 驯化背包中的诡兽\n"
        f"{cmd('宠物')} 查看当前伙伴状态\n"
        f"{cmd('宠物列表')} 查看所有宠物\n"
        f"{cmd('切换伙伴 宠物ID', '切换伙伴 ')} 切换当前伙伴\n"
        "***\n"
        "**💬 互动与对话**\n"
        f"{cmd('摸摸')} {cmd('摸头')} {cmd('玩耍')} {cmd('抱抱')} 互动（+好感/心情）\n"
        f"{cmd('对话 内容', '对话 ')} 与宠物对话\n"
        f"{cmd('定制人设 描述', '定制人设 ')} 花费50诡烛定制人设（需已化形）\n"
        f"{cmd('重置人设')} 免费恢复宠物默认人设\n"
        "***\n"
        "**🍖 喂食**\n"
        f"{cmd('喂食 怨念', '喂食 怨念 ')} 消耗怨念喂养\n"
        f"{cmd('喂食 菜肴名', '喂食 ')} 用菜肴喂养（更好效果）\n"
        "• 每日递减收益：前99次正常 -> 100-300次减半 -> 300次后最低\n"
        "***\n"
        "**👗 装扮**\n"
        f"{cmd('宠物装扮')} 查看饰品商店\n"
        f"{cmd('买饰品 名称', '买饰品 ')} 购买饰品\n"
        f"{cmd('宠物装扮 名称', '宠物装扮 ')} 给宠物装备饰品\n"
        "• 槽位：头饰/颈饰/服饰\n"
        "***\n"
        "**⚔️ 战斗加成**\n"
        "宠物自动为主人提供被动属性加成\n"
        "等级越高、心情越好，加成越强\n"
        "***\n"
        "**🔮 进化**\n"
        f"{cmd('进化宠物')} 查看进化条件和属性变化\n"
        f"{cmd('进化宠物 确认')} 消耗材料执行进化\n"
        "***\n"
        "**✨ 化形**\n"
        f"{cmd('化形 男', '化形 ')} 化形时选择性别\n"
        "• 需要等级50 + 好感度100\n"
        "• 化形后解锁AI对话\n"
        "• 性别一经选择无法更改，请慎重\n"
        "***\n"
        "**🌾 守田**\n"
        f"{cmd('派遣守田')} 派宠物守灵田（拦截偷菜）\n"
        f"{cmd('召回宠物')} 召回守田中的宠物\n"
        "***\n"
        "**📊 诡兽种族**\n"
        "冥犬 / 诡猫 / 鬼隼 / 噩梦狼 / 虚空蟒\n"
        "稀有度越高，属性成长越强\n"
        f"> {cmd('帮助', '帮助')} 返回主菜单"
    )
    await pet_help_cmd.finish(build_markdown(content))
