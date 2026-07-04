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
        "# 诡修仙 · 帮助\n"
        "***\n"
        "**⚔️ 修仙主线**\n"
        f"{cmd('新手上路')} 注册 · 修炼 · 突破 · 加点\n"
        f"{cmd('成长核心')} 装备 · 锻造 · 炼丹 · 阴宅\n"
        f"{cmd('资源获取')} 打工 · 钓鱼 · 灵田 · 副本\n"
        f"{cmd('战斗挑战')} PVE · PVP · 世界BOSS · 天灾\n"
        f"{cmd('经济市场')} 跑商 · 银行 · 投资 · 拍卖\n"
        f"{cmd('社交公会')} 送礼 · 结婚 · 师徒 · 公会\n"
        f"{cmd('图鉴记录')} 排行榜 · 成就 · 图鉴\n"
        "***\n"
        "**🎮 趣味功能**\n"
        f"{cmd('签到')} | {cmd('今天吃什么')} | {cmd('每日一言')} | {cmd('微博热搜')}\n"
        f"{cmd('起卦 你的问题', '起卦 ')} | {cmd('驾考题目')} | {cmd('今日小猪')}\n"
        f"{cmd('恶魔轮盘帮助')} | {cmd('斗兽棋')} | {cmd('人机轮盘 金额', '人机轮盘 ')}\n"
        f"{cmd('随机人生')} | {cmd('人生选择')} | {cmd('福利娱乐')} 更多…\n"
        "***\n"
        f"{cmd('切换称号')} | {cmd('赞助商店')} | {cmd('月卡')}\n"
        "***\n"
        f"> 点击蓝字即可发送指令。新手先看 {cmd('新手指引')}，全部指令见 {cmd('完整帮助')}\n"
        f"> 有疑问 @机器人 {cmd('问 你的问题', '问 ')}\n"
        f"> [加入官群【꧁༺诡修仙༻꧂】]({GROUP_LINK})\n"
        "> 游戏资料：HTTPS://GITEE.COM/ling-gtq/TheWestTutorial"
    )
    await help_cmd.finish(build_markdown(content))

# 空消息@机器人 → 触发帮助
empty_at_cmd = on_message(rule=to_me(), priority=99, block=True)


def _is_text_only_empty_message(event: MessageEvent) -> bool:
    message = event.get_message()
    return all(segment.type == "text" for segment in message) and not event.get_plaintext().strip()


@empty_at_cmd.handle()
async def handle_empty_at(event: MessageEvent):
    """用户仅@机器人不说话时，等同于触发帮助"""
    if not _is_text_only_empty_message(event):
        return
    await handle_help(event, Message())

# ==================== 8大帮助模块 ====================

# 1. 新手上路
newbie_module_cmd = on_command("新手上路", priority=4, block=True)
@newbie_module_cmd.handle()
async def handle_newbie_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 新手上路\n"
        "***\n"
        "**👤 注册与角色**\n"
        f"{cmd('注册 男/女', '注册 ')} 创建角色 | {cmd('面板')} 角色状态\n"
        f"{cmd('改名 新名字', '改名 ')} 需改名卡 | {cmd('改性别 男/女', '改性别 ')}\n"
        "***\n"
        "**🧘 修炼**\n"
        f"{cmd('修炼')} 获取经验，5分钟冷却\n"
        f"{cmd('闭关')} 离线挂机 → {cmd('出关')} 结算收益\n"
        f"{cmd('突破')} 提升境界，30级前必定成功\n"
        f"{cmd('突破 镇厄')} 消耗怨念，确保成功\n"
        f"{cmd('冥返')} 转生重修，换取永久加成 | {cmd('冥返信息')} 条件\n"
        "***\n"
        "**📊 加点**\n"
        f"{cmd('加点 力 10', '加点 ')} 力/体/敏/智/运/防 | {cmd('加点帮助')} 加点推荐\n"
        "***\n"
        "**🎯 每日**\n"
        f"{cmd('签到')} → {cmd('修炼')} → 睡前{cmd('闭关')}\n"
        "***\n"
        f"> 完整成长路线见 {cmd('新手指引')} | {cmd('帮助', '帮助')} 返回"
    )
    await newbie_module_cmd.finish(build_markdown(content))

# 2. 成长核心
growth_module_cmd = on_command("成长核心", priority=4, block=True)
@growth_module_cmd.handle()
async def handle_growth_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 成长核心\n"
        "***\n"
        "**🎽 装备**\n"
        f"{cmd('装备栏')} 已穿戴 | {cmd('装备 编号', '装备 ')} 穿戴 | {cmd('卸下 编号', '卸下 ')} | {cmd('修理 编号', '修理 ')}\n"
        f"{cmd('锻造列表')} 可锻造清单 → {cmd('锻造 装备名', '锻造 ')}\n"
        f"{cmd('升阶 编号', '升阶 ')} 升阶强化\n"
        "***\n"
        "**💎 镶嵌**\n"
        f"{cmd('孔位 编号', '孔位 ')} 孔位详情 | {cmd('镶嵌物品')} 可用镶嵌物\n"
        f"{cmd('镶嵌 编号 孔位 镶嵌物', '镶嵌 ')} 镶嵌宝石\n"
        "***\n"
        "**🧪 炼丹**\n"
        f"{cmd('丹方')} → {cmd('炼丹 丹方名 数量', '炼丹 ')} → {cmd('收获丹药')} → {cmd('使用 丹药名', '使用 ')}\n"
        "***\n"
        "**💀 怨念**\n"
        f"{cmd('献祭 材料名 数量', '献祭 ')} 材料换怨念，供{cmd('突破 镇厄')}使用\n"
        "***\n"
        "**🏠 阴宅**\n"
        f"{cmd('阴宅')} | {cmd('购买阴宅')} 售价1000万 | {cmd('升级阴宅')} | {cmd('阴宅仓库')}\n"
        "***\n"
        f"> 卡境界先突破，战力低先补装备，缺药就炼丹或去市场\n"
        f"> {cmd('装备系统')} | {cmd('炼丹系统')} | {cmd('阴宅系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await growth_module_cmd.finish(build_markdown(content))

# 3. 资源获取
resource_module_cmd = on_command("资源获取", priority=4, block=True)
@resource_module_cmd.handle()
async def handle_resource_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 资源获取\n"
        "***\n"
        "**💼 打工**\n"
        f"{cmd('打工')} 可选工作 → {cmd('打工 工作名', '打工 ')} 上工 → {cmd('收工')} 领钱\n"
        f"{cmd('工作地点')} 全部地点。评级S~D决定倍率，熟练度越高收入越高\n"
        "***\n"
        "**📋 委托**\n"
        f"{cmd('每日委托')} → {cmd('接取委托 编号', '接取委托 ')} → {cmd('完成委托')}\n"
        "***\n"
        "**🌀 诡域副本**\n"
        f"{cmd('进入 1层诡域', '进入 ')} → {cmd('探索')} → {cmd('领取宝箱')} → {cmd('返回')}\n"
        "***\n"
        "**🗺️ 地图**\n"
        f"{cmd('地图')} 地点总览 | {cmd('导航 地点名', '导航 ')} 前往 | {cmd('观察')} 四周 | {cmd('交互 NPC名', '交互 ')}\n"
        "***\n"
        f"**🎣 钓鱼** {cmd('钓鱼')} 5分钟冷却 | {cmd('鱼栏')} 存量\n"
        f"**🍳 餐厅** {cmd('创建餐厅')} 开店 | {cmd('餐厅')} 经营状态\n"
        f"**🌱 灵田** {cmd('灵田')} | {cmd('收菜')} | {cmd('菜市场')} 市价 | {cmd('卖菜 作物名 数量', '卖菜 ')}\n"
        "***\n"
        f"> 缺钱打工跑商，缺材料下副本接委托，缺药炼丹或市场买\n"
        f"> {cmd('打工系统')} | {cmd('副本系统')} | {cmd('钓鱼系统')} | {cmd('灵田系统')} | {cmd('宠物系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await resource_module_cmd.finish(build_markdown(content))

# 4. 战斗挑战
battle_module_cmd = on_command("战斗挑战", priority=4, block=True)
@battle_module_cmd.handle()
async def handle_battle_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 战斗挑战\n"
        "***\n"
        "**⚔️ PVE**\n"
        f"{cmd('攻击 NPC名', '攻击 ')} 攻击怪物或NPC\n"
        "荒野与诡域为真实战斗，死亡掉落；城镇是安全区，只能切磋\n"
        "***\n"
        "**🤝 PVP**\n"
        f"{cmd('切磋 UID', '切磋 ')} 友好切磋，无损失 | {cmd('攻击 UID', '攻击 ')} 真实死斗\n"
        "***\n"
        "**🏆 斗法天梯**\n"
        "残魂对决，肉身不损\n"
        f"{cmd('斗法天梯')} 主页 | {cmd('斗法天梯 匹配', '斗法天梯 匹配')} 匹配入场\n"
        f"{cmd('斗法天梯 排行', '斗法天梯 排行')} 凶名榜 | {cmd('斗法商店')} 魂晶兑换\n"
        "***\n"
        "**🌟 世界BOSS**\n"
        f"{cmd('世界BOSS')} 信息 | {cmd('讨伐BOSS')} 每日3次 | {cmd('BOSS排行')} 伤害榜\n"
        "***\n"
        "**📊 战力**\n"
        f"{cmd('战力')} 完整属性 | {cmd('战力说明')} 属性作用 | {cmd('死斗日志')} 战斗记录\n"
        "***\n"
        f"> 装备与丹药是战力提升的大头\n"
        f"> {cmd('战斗系统')} | {cmd('斗法天梯帮助')} | {cmd('帮助', '帮助')} 返回"
    )
    await battle_module_cmd.finish(build_markdown(content))

# 5. 经济市场
economy_module_cmd = on_command("经济市场", priority=4, block=True)
@economy_module_cmd.handle()
async def handle_economy_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 经济市场\n"
        "***\n"
        "**🏦 银行**\n"
        f"{cmd('存 金额', '存 ')} | {cmd('取 金额', '取 ')} | {cmd('余额')} | {cmd('转账 UID 金额', '转账 ')} 手续费3%\n"
        "***\n"
        "**🏪 跑商**\n"
        f"{cmd('市集')} 当前行情 | {cmd('市价 物品名', '市价 ')} 各地比价 | {cmd('跑商推荐')} 盈利路线\n"
        f"{cmd('购买 物品 数量', '购买 ')} | {cmd('出售 物品 数量', '出售 ')} | {cmd('自动出售')} 一键卖出\n"
        f"{cmd('市集列表')} | {cmd('市集记录')} 交易动态 | {cmd('黑市')} | {cmd('食材铺')} | {cmd('交易限制')} 冷却规则\n"
        "***\n"
        "**📈 气运投资**\n"
        "高风险高波动，量力而行\n"
        f"{cmd('投资行情')} 实时价格 | {cmd('我的投资')} 持仓\n"
        f"{cmd('投资气运 代码 数量', '投资气运 ')} 买入 | {cmd('出售气运 代码 数量', '出售气运 ')} 卖出\n"
        "***\n"
        "**💎 理财**\n"
        f"{cmd('定期理财')} 七日定存，周利率5% | {cmd('购买定期 金额', '购买定期 ')} | {cmd('我的定期')}\n"
        f"{cmd('理财产品')} 活期 | {cmd('购买理财 金额', '购买理财 ')} | {cmd('我的理财')}\n"
        "***\n"
        "**🔄 玩家挂牌**\n"
        f"{cmd('交易清单')} 在售 | {cmd('我的挂牌')}\n"
        f"{cmd('挂牌 出售 物品 单价 数量', '挂牌 ')} 上架 | {cmd('撤牌 ID', '撤牌 ')} 撤回\n"
        "***\n"
        "**🏛️ 拍卖行**\n"
        f"{cmd('拍卖行')} 在拍物品 | {cmd('出价 拍卖ID 金额', '出价 ')} 竞价\n"
        "***\n"
        f"> 赚钱由稳到险：{cmd('打工')} → {cmd('跑商推荐', '跑商推荐')} → {cmd('投资行情', '投资行情')}\n"
        f"> {cmd('经济系统')} | {cmd('投资系统')} | {cmd('拍卖行系统')} | {cmd('烹饪系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await economy_module_cmd.finish(build_markdown(content))

# 6. 社交公会
social_module_cmd = on_command("社交公会", priority=4, block=True)
@social_module_cmd.handle()
async def handle_social_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 社交公会\n"
        "***\n"
        "**🎁 送礼**\n"
        f"{cmd('礼物商店')} → {cmd('买礼物 礼物名 数量', '买礼物 ')} → {cmd('赠礼 UID 礼物名 数量', '赠礼 ')}\n"
        f"{cmd('好感度 UID', '好感度 ')} 好感度进度\n"
        "***\n"
        "**💒 结婚 · 结义 · 师徒**\n"
        "找月老、结义使者、师徒使者，或各集群社交代理\n"
        f"{cmd('交互 月老 求婚 UID', '交互 月老 求婚 ')} 求婚\n"
        f"{cmd('交互 结义使者 结义 UID', '交互 结义使者 结义 ')} 结义\n"
        f"{cmd('交互 师徒使者 拜师 UID', '交互 师徒使者 拜师 ')} 拜师\n"
        "***\n"
        f"**🕯️ 香火商店** {cmd('香火商店')} | {cmd('买食谱 食谱名', '买食谱 ')}\n"
        "***\n"
        "**🏰 公会**\n"
        f"{cmd('公会列表')} | {cmd('加入公会 ID', '加入公会 ')} 申请 | {cmd('我的公会')}\n"
        f"{cmd('公会建筑')} 建筑加成 | {cmd('捐献金币 金额', '捐献金币 ')}\n"
        "***\n"
        "**💬 消息**\n"
        f"{cmd('消息')} 世界频道 | {cmd('发消息 内容', '发消息 ')} | {cmd('私信 UID 内容', '私信 ')}\n"
        f"**🧧 红包** {cmd('发红包 金额 份数', '发红包 ')} | {cmd('抢红包')} | {cmd('红包记录')}\n"
        "***\n"
        f"> 好感度满5000可结婚、结义\n"
        f"> {cmd('社交系统')} | {cmd('公会系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await social_module_cmd.finish(build_markdown(content))

# 7. 图鉴记录
info_module_cmd = on_command("图鉴记录", priority=4, block=True)
@info_module_cmd.handle()
async def handle_info_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 图鉴记录\n"
        "***\n"
        "**📚 图鉴**\n"
        f"{cmd('图鉴 物品名', '图鉴 ')} 物品详情 | {cmd('钓鱼图鉴')} 鱼类收集\n"
        "***\n"
        f"**🏆 排行榜** {cmd('排行榜')} 总览\n"
        f"{cmd('财富榜')} | {cmd('修为榜')} | {cmd('幸运榜')} | {cmd('探索榜')}\n"
        f"{cmd('敏捷榜')} | {cmd('魅力榜')} | {cmd('钓鱼排行')} | {cmd('BOSS排行')}\n"
        "***\n"
        "**🎯 成就**\n"
        f"{cmd('成就')} 全部成就 | {cmd('成就 成就名', '成就 ')} 详情。达成自动解锁\n"
        "***\n"
        "**📊 个人记录**\n"
        f"{cmd('面板')} | {cmd('完整面板')} 详细数据\n"
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
        "***\n"
        "**🎯 每日福利**\n"
        f"{cmd('签到')} | {cmd('月卡')} 权益状态 | {cmd('邀请码')} 邀请好友\n"
        "***\n"
        "**🎮 小游戏**\n"
        f"{cmd('抽签 你的问题', '抽签 ')} 观音灵签 | {cmd('答案之书 你的问题', '答案之书 ')}\n"
        f"{cmd('起卦 你的问题', '起卦 ')} 六爻占卜，500金币 | {cmd('驾考题目')}\n"
        f"{cmd('恶魔轮盘帮助')} PVP博弈 | {cmd('斗兽棋')} 押注棋局\n"
        f"{cmd('猜拳 石头 金额', '猜拳 ')} 猜拳鬼，仅周六 | {cmd('试炼列表')} 互动剧情\n"
        f"{cmd('随机人生')} 人生重开 | {cmd('人生选择')} 自选天赋\n"
        f"{cmd('今日小猪')} | {cmd('怪谈系统')} 规则怪谈\n"
        "***\n"
        "**🎉 休闲**\n"
        f"{cmd('每日一言')} | {cmd('今天吃什么')} | {cmd('微博热搜')}\n"
        "***\n"
        f"**🎁 抽奖** {cmd('参与抽奖 ID', '参与抽奖 ')} | {cmd('我的抽奖')}\n"
        "***\n"
        "**🏰 天灾**\n"
        f"{cmd('降临')} 降临下位世界 | {cmd('镇守')} 山寨状态 | {cmd('迎战')} 迎击英雄\n"
        f"{cmd('侦查')} 探查英雄，10天灾点 | {cmd('天灾商店')} 兑换\n"
        "***\n"
        f"> {cmd('娱乐系统')} | {cmd('抽奖系统')} | {cmd('天灾系统')} | {cmd('赞助商店')} | {cmd('帮助', '帮助')} 返回"
    )
    await fun_module_cmd.finish(build_markdown(content))

# 管理员系统
admin_help_cmd = on_command("管理员系统", aliases={"管理员帮助", "管理指令"}, priority=4, block=True, permission=SUPERUSER)

@admin_help_cmd.handle()
async def handle_admin_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 管理员指令\n"
        "***\n"
        "**🔧 物品**\n"
        f"{cmd('发物品 UID 物品名 数量', '发物品 ')} | {cmd('发装备 UID 装备名 数量', '发装备 ')} | {cmd('发诡烛 UID 数量', '发诡烛 ')}\n"
        f"{cmd('转移物品 UID1 UID2 物品名 数量', '转移物品 ')}\n"
        "***\n"
        "**🎁 抽奖**\n"
        f"{cmd('发起抽奖 物品名 中奖人数 每人数量', '发起抽奖 ')}\n"
        f"{cmd('开奖 抽奖ID', '开奖 ')} 仅发起人 | {cmd('抽奖详情 抽奖ID', '抽奖详情 ')}\n"
        f"{cmd('取消抽奖 抽奖ID', '取消抽奖 ')} 取消并退还奖品\n"
        "***\n"
        "**📊 统计**\n"
        f"{cmd('材料统计')} 全服材料分布 | {cmd('材料详情 材料名', '材料详情 ')}\n"
        "***\n"
        "**🔍 日志**\n"
        f"{cmd('查看报错', '查看报错 ')} | {cmd('最近报错')} | {cmd('最近活动', '最近活动 ')} 全服动态\n"
        "***\n"
        "**💾 备份**\n"
        f"{cmd('手动备份')} 立即备份MySQL | {cmd('备份状态')} 备份列表\n"
        f"{cmd('恢复备份 序号/文件名', '恢复备份 ')} 从备份恢复。每天凌晨4:00自动备份\n"
        "***\n"
        "**🖼️ 物品图片**\n"
        f"{cmd('设置物品图片 物品名 图片URL', '设置物品图片 ')} | {cmd('删除物品图片 物品名', '删除物品图片 ')} | {cmd('物品图片列表')}\n"
        "***\n"
        f"**🛠️ 工坊** {cmd('刷新工坊清单')} 覆盖更新所有城镇锻造清单\n"
        "***\n"
        "**💹 气运**\n"
        f"{cmd('初始化气运')} | {cmd('更新气运价格')} | {cmd('触发黑天鹅')}\n"
        "***\n"
        "**🚫 封禁**\n"
        f"{cmd('禁言 UID 原因 时长', '禁言 ')} | {cmd('解禁 UID', '解禁 ')} | {cmd('黑名单')} | {cmd('删除留言 留言ID', '删除留言 ')}\n"
        f"{cmd('封禁 UID 原因 时长', '封禁 ')} 全局封禁 | {cmd('解封 UID', '解封 ')} | {cmd('封禁列表')} | {cmd('封禁信息 UID', '封禁信息 ')}\n"
        "时长格式：3d、24h、永久\n"
        "***\n"
        f"**🏰 公会** {cmd('删除公会 公会ID', '删除公会 ')} 连带删除所有数据，不可逆\n"
        "***\n"
        f"**🎆 活动** {cmd('开启活动', '开启活动 ')} | {cmd('关闭活动')} 除夕叩门\n"
        "***\n"
        f"**🐢 海龟汤** {cmd('结束海龟汤')} 提前结束并公开汤底\n"
        "***\n"
        "**🤖 AI数据库**\n"
        f"{cmd('管理员要求 需求描述', '管理员要求 ')} 自然语言查询/修改数据库\n"
        "仅支持SELECT和UPDATE，禁止DELETE、DROP等危险操作\n"
        f"> {cmd('帮助', '帮助')} 返回"
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
        "🕯️ 赞助\n"
        "━━━━━━━━━━━━━\n"
        "月卡：\n"
        "· 基础月卡 88诡烛/30天\n"
        "  修炼闭关效率+20%，闭关上限9小时\n"
        "  突破失败损失-5%，背包+5格\n"
        "  签到得月卡宝箱×1，咒抗+5\n"
        "  一键献祭、一键修复装备\n"
        "· 高级月卡 288诡烛/30天\n"
        "  修炼闭关效率+50%，闭关上限12小时\n"
        "  突破失败损失-10%，背包+20格\n"
        "  签到得月卡宝箱×3，咒抗+5\n"
        "  副本自动采集、一键修理、一键献祭\n"
        "━━━━━━━━━━━━━\n"
        "道具：\n"
        "· 背包永久扩容1格 10诡烛\n"
        "· 棺材钉 50诡烛（修炼效率+0.5%/枚，上限50%）\n"
        "· 哭坟帽 20诡烛（使用得1w怨念）\n"
        "· 改名卡 10诡烛 | 自定义称号 500诡烛\n"
        "· 重启符 1000诡烛（重置属性点重新分配，各类加成保留）\n"
        "· 绑定小号 200诡烛/个（需目标小号确认）\n"
        "━━━━━━━━━━━━━\n"
        "宠物饰品，购买发【买饰品 名称】：\n"
        "· 紫色 150诡烛：虚空锁链/诡纹和服\n"
        "· 橙色 300诡烛：星辰发冠/银铃璎珞/流光羽衣\n"
        "━━━━━━━━━━━━━\n"
        "特权 180诡烛/月：\n"
        "· 闭关无上限 【购买闭关特权】\n"
        "· 远程仓库 【购买远程仓库】随地存取阴宅仓库\n"
        "· 鱼竿特权 【购买鱼竿特权】每次多钓2条\n"
        "· 全视之眼 【购买全视之眼】俯瞰诡域全图\n"
        "━━━━━━━━━━━━━\n"
        "兑换比例 1元=10诡烛，服务在【赞助商店】购买\n"
        "支付时请备注UID（联系方式可选）\n"
        "当前权益发【月卡】查询"
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
        "【挂牌详情 订单ID】 【估价 名称】 【税率】",
    ]),
    ("打工系统", "#22c55e", [
        "【打工】 【打工 工作名】 【收工】",
        "【工作状态】 【工作地点】",
        "【打工记录】 【打工统计】",
    ]),
    ("公会系统", "#ec4899", [
        "【我的公会】 【公会列表】",
        "【加入公会 ID】 【退会】",
        "【公会建筑】 【建造 建筑名】 【移动建筑】",
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
        "【恶魔轮盘帮助】 【斗兽棋】 【试炼列表】",
        "【已通关试炼】 【斗兽棋下注 玩家 金币】",
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
        "【购买绑定小号 UID】 200诡烛/个，需小号确认",
        "【确认绑定小号 验证码】 小号拥有者确认",
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
