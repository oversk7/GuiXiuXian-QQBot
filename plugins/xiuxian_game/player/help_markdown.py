"""
优化的Markdown交互式帮助系统
使用QQ官方Markdown模版提供更好的用户体验
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg


# ==================== 帮助菜单 (使用物品列表模版) ====================
help_md_cmd = on_command("帮助md", aliases={"菜单md", "help_md"}, priority=5, block=True)

@help_md_cmd.handle()
async def handle_help_md(event: MessageEvent, args: Message = CommandArg()):
    """
    使用Markdown模版的帮助菜单
    模版ID: 102499345_1769177949 (物品列表类)
    """
    # 构建10个快捷按钮
    buttons = [
        "修炼系统",
        "玩家系统",
        "背包系统",
        "装备系统",
        "战斗系统",
        "探索系统",
        "经济系统",
        "公会系统",
        "社交系统",
        "娱乐系统"
    ]

    # 构建模版参数
    template_params = [
        MessageMarkdownParams(key=f"btn{i+1}", values=[btn])
        for i, btn in enumerate(buttons)
    ]

    # 创建Markdown消息
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177949",
        params=template_params
    )

    # 发送带说明的消息
    msg = Message("✨ 欢迎使用诡修仙帮助系统 ✨\n"
                 "━━━━━━━━━━━━━\n"
                 "🎮 点击下方按钮查看对应系统详情\n"
                 "💡 发送【问 你的问题】使用AI助手\n"
                 "💡 发送/邀请码 邀请好友获得奖励\n"
                 "━━━━━━━━━━━━━")
    msg.append(MessageSegment.markdown(markdown))

    await help_md_cmd.finish(msg)


# ==================== 修炼系统 (使用反馈类模版) ====================
xiulian_md_cmd = on_command("修炼系统md", aliases={"修炼帮助md"}, priority=4, block=True)

@xiulian_md_cmd.handle()
async def handle_xiulian_md(event: MessageEvent, args: Message = CommandArg()):
    """
    使用Markdown模版的修炼系统帮助
    模版ID: 102499345_1769177016 (反馈类)
    """
    # 标题和内容
    title = "✨ 修炼系统"
    result = (
        "突破境界获得属性点，献祭材料获取怨念保驾护航\n\n"
        "━━━━━━━━━━━━━\n"
        "【修炼】 获取经验，冷却5分钟\n"
        "【闭关】 闭关修炼，挂机升级\n"
        "【出关】 出关后可继续修炼\n"
        "【突破】 突破境界，可消耗怨念确保成功\n"
        "【加点 属性 点数】 分配属性点\n"
        "【献祭 材料 数量】 献祭材料获取怨念\n"
        "━━━━━━━━━━━━━\n"
        "💡 突破失败会损失部分修为\n"
        "💡 发送【加点帮助】查看详细指南"
    )

    # 8个快捷按钮
    buttons = [
        "修炼",
        "闭关",
        "突破",
        "面板",
        "加点帮助",
        "战力",
        "背包",
        "帮助"
    ]

    # 构建模版参数
    template_params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="result", values=[result])
    ]
    template_params.extend([
        MessageMarkdownParams(key=f"btn{i+1}", values=[btn])
        for i, btn in enumerate(buttons)
    ])

    # 创建Markdown消息
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177016",
        params=template_params
    )

    await xiulian_md_cmd.finish(MessageSegment.markdown(markdown))


# ==================== 背包系统 (使用物品列表模版) ====================
bag_md_cmd = on_command("背包系统md", aliases={"背包帮助md"}, priority=4, block=True)

@bag_md_cmd.handle()
async def handle_bag_md(event: MessageEvent, args: Message = CommandArg()):
    """
    使用Markdown模版的背包系统帮助
    模版ID: 102499345_1769177949 (物品列表类)
    """
    # 10个快捷按钮
    buttons = [
        "背包",
        "背包 消耗品",
        "背包 材料",
        "背包 装备",
        "使用 回春散 1",
        "一键嗑药",
        "图鉴",
        "耐药性",
        "整理背包",
        "帮助"
    ]

    # 构建模版参数
    template_params = [
        MessageMarkdownParams(key=f"btn{i+1}", values=[btn])
        for i, btn in enumerate(buttons)
    ]

    # 创建Markdown消息
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177949",
        params=template_params
    )

    # 发送带说明的消息
    msg = Message("✨ 背包系统 ✨\n"
                 "━━━━━━━━━━━━━\n"
                 "管理物品，使用道具，查看图鉴\n"
                 "💡 装备不占用背包容量\n"
                 "💡 点击下方按钮快速操作\n"
                 "━━━━━━━━━━━━━")
    msg.append(MessageSegment.markdown(markdown))

    await bag_md_cmd.finish(msg)


# ==================== 快捷操作面板 (使用连续按钮模版) ====================
quick_panel_cmd = on_command("快捷面板", aliases={"快捷操作", "qp"}, priority=5, block=True)

@quick_panel_cmd.handle()
async def handle_quick_panel(event: MessageEvent, args: Message = CommandArg()):
    """
    快捷操作面板 - 最常用的10个指令
    模版ID: 102499345_1768473387 (连续按钮)
    """
    # 10个最常用的指令
    quick_commands = [
        "修炼",
        "突破",
        "面板",
        "背包",
        "装备栏",
        "战力",
        "签到",
        "探索",
        "市集",
        "帮助"
    ]

    # 构建模版参数
    template_params = [
        MessageMarkdownParams(key=f"t{i+1}", values=[cmd])
        for i, cmd in enumerate(quick_commands)
    ]

    # 创建Markdown消息
    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    msg = Message("⚡ 快捷操作面板\n点击下方按钮快速执行指令")
    msg.append(MessageSegment.markdown(markdown))

    await quick_panel_cmd.finish(msg)


# ==================== 经济系统 (使用反馈类模版) ====================
economy_md_cmd = on_command("经济系统md", aliases={"经济帮助md"}, priority=5, block=True)

@economy_md_cmd.handle()
async def handle_economy_md(event: MessageEvent, args: Message = CommandArg()):
    """
    使用Markdown模版的经济系统帮助
    模版ID: 102499345_1769177016 (反馈类)
    """
    title = "✨ 经济系统"
    result = (
        "管理金币、跑商赚钱、银行理财\n\n"
        "━━━━━━━━━━━━━\n"
        "💰 银行系统：\n"
        "【存 金额】 存入冥行\n"
        "【取 金额】 从冥行取出\n"
        "【余额】 查询存款\n"
        "【转账 UID 金额】 银行转账\n\n"
        "🏪 跑商系统：\n"
        "【市集】 查看当前市场\n"
        "【购买 物品 数量】 购买商品\n"
        "【出售 物品 数量】 出售商品\n"
        "【跑商推荐】 查看盈利路线\n\n"
        "💡 跑商是新手快速赚钱的方式"
    )

    buttons = [
        "市集",
        "余额",
        "跑商推荐",
        "市集列表",
        "黑市",
        "理财产品",
        "我的理财",
        "帮助"
    ]

    template_params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="result", values=[result])
    ]
    template_params.extend([
        MessageMarkdownParams(key=f"btn{i+1}", values=[btn])
        for i, btn in enumerate(buttons)
    ])

    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177016",
        params=template_params
    )

    await economy_md_cmd.finish(MessageSegment.markdown(markdown))


# ==================== 战斗系统 (使用反馈类模版) ====================
battle_md_cmd = on_command("战斗系统md", aliases={"战斗帮助md", "PVP系统md"}, priority=4, block=True)

@battle_md_cmd.handle()
async def handle_battle_md(event: MessageEvent, args: Message = CommandArg()):
    """
    使用Markdown模版的战斗系统帮助
    模版ID: 102499345_1769177016 (反馈类)
    """
    title = "✨ 战斗系统"
    result = (
        "玩家对战、NPC战斗、世界BOSS挑战\n\n"
        "━━━━━━━━━━━━━\n"
        "⚔️ 玩家对战：\n"
        "【切磋 UID】 友好切磋，无损失\n"
        "【攻击 UID/NPC】 攻击目标\n"
        "  • 城镇安全区：友好切磋\n"
        "  • 荒野/诡域：真实死斗\n\n"
        "🌟 世界BOSS：\n"
        "【世界BOSS】 查看BOSS信息\n"
        "【讨伐BOSS】 攻击BOSS(每日3次)\n"
        "【BOSS排行】 查看伤害排行\n\n"
        "💡 敏捷高的玩家更容易先手"
    )

    buttons = [
        "战力",
        "战力说明",
        "世界BOSS",
        "讨伐BOSS",
        "BOSS排行",
        "死斗日志",
        "加点帮助",
        "帮助"
    ]

    template_params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="result", values=[result])
    ]
    template_params.extend([
        MessageMarkdownParams(key=f"btn{i+1}", values=[btn])
        for i, btn in enumerate(buttons)
    ])

    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177016",
        params=template_params
    )

    await battle_md_cmd.finish(MessageSegment.markdown(markdown))
