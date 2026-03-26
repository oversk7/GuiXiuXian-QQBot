"""
QQ原生Markdown语法测试指令
测试官方开放的原生markdown能力，包括链接、标题、加粗等语法
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown


GROUP_LINK = (
    "https://qun.qq.com/universal-share/share?"
    "ac=1&authKey=fBfQXvfkDK92gotOtEFTjwLD4R3qKy%2BV79jJCyMLKqTWKmazq23NO3miCxBir7aL"
    "&busi_data=eyJncm91cENvZGUiOiI5NjI0OTQ2NzkiLCJ0b2tlbiI6IjdSUURicDczVGpFclVUUDRF"
    "RFh4R1lYaXdzMmtyTEgvU040UlJyUkhjVUxXUGZyb0NHR3Iwa1VIZnAranpqQTQiLCJ1aW4iOiIy"
    "Njk4NTk1MTE1In0%3D"
    "&data=lTl1gOtgo5gvdmyaAmJGiAZBK6oI7nGH1jr_AuHfsltlCDUTpIdA7qvXh5k5Yj0uidZilU_o"
    "g4nQXsr8cflTzA&svctype=4&tempid=h5_group_info"
)

md_native_test = on_command("原生md测试", aliases={"原生markdown测试"}, priority=4, block=True)


@md_native_test.handle()
async def handle_md_native_test(event: MessageEvent):
    """测试QQ原生Markdown语法"""
    content = (
        "# 诡修仙 · 原生Markdown测试\r"
        "**这是一条原生Markdown消息**\r"
        "***\r"
        "[点击加入群聊【꧁༺诡修仙༻꧂】]"
        f"({GROUP_LINK})\r"
        "***\r"
        "> 如果你能看到可点击的链接，说明原生Markdown已生效"
    )
    markdown = MessageMarkdown(content=content)
    await md_native_test.finish(MessageSegment.markdown(markdown))
