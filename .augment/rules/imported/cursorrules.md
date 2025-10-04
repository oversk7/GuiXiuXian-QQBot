---
type: "always_apply"
---

这是一个基于Nonebot2+QQAdapter的官方QQ群机器人文字游戏项目。
你的任何解决方案都要考虑到以下内容：
1. 不允许主动发消息，只能靠用户触发
2. 所有注册的命令都需要阻拦：block=True
3. 异常捕获要指定异常类型，禁止使用except Exception as e
4. 参数获取使用args: Message = CommandArg()
5. 在QQAdapter中，event.get_user_id()获取的是QQ号的加密(id)，不易记忆，展示时请用自增的(uid)。
6. event.get_session_id()在私聊时为friend_<userId>，在群聊时为group_<groupId>_<userId>，可判断是否私聊
7. event的msg_id大概三分钟就过期，不能再回复触发者，所以这样发: bot.send(latest_event,message)
8. 代码结构需要易懂容易维护，不要只为了炫技
9. 作为文字游戏，输出内容需要注意美观，有良好的交互体验，可以利用emoji排版，所有分割线均使用这个长度“━━━━━━━━━━━━━”
10. 更新指令后需要及时同步到help文件中，测试脚本会遇到Nonebot初始化问题，请直接测试核心逻辑