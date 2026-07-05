# QQ 原生 Markdown 参考

QQ 开放平台已对本机器人开放原生 Markdown,**不再使用 custom_template_id 模板**(全部存量已于 2026-07-05 迁移完毕)。

## 构建方式

统一走 `plugins/xiuxian_game/utils_markdown.py`:

```python
from ..utils_markdown import build_markdown, cmd, color_text, color_rarity

content = "\n".join(lines)          # 换行用 \n,build_markdown 内部自动转 \r
await matcher.finish(build_markdown(content))
```

## 支持的语法

| 语法 | 写法 |
|---|---|
| 标题 | `# 一级` / `## 二级` |
| 粗体/斜体 | `**粗**` / `*斜*` |
| 分隔线 | `***` |
| 引用块 | `> 提示文字` |
| 行内代码/代码块 | `` `code` `` / ``` 围栏(战斗日志等长文本等宽展示) |
| 图片 | `![说明 #300px #240px](url)` (宽高必须标注) |
| 蓝字可点击指令 | `cmd(show, text)` → `<qqbot-cmd-input>` |
| 彩色文字 | `color_text(文字, "#RRGGBB")` (KaTeX 实现);品质色用 `color_rarity(文字, "purple")` |

## 排版惯例(全项目统一)

- 大标题带 emoji:`# 🎉 签到成功 · 连续 7 天`
- 区块间用 `***` 分隔;关键数值 `**粗体**` 或彩色
- 提示/氛围文案放 `>` 引用块,不堆叠 💡
- 页脚一行蓝字导航:`cmd('面板') | cmd('背包') | cmd('帮助')`
- 榜单人名可点击:`cmd(nickname, f'面板 {uid}')`

## 注意

- 玩家头像:`https://thirdqq.qlogo.cn/qqapp/{bot.self_id}/{openid}/0`
- 代码块内的日志行需防 ``` 破坏围栏(参见 `battle/battle_markdown.py` 的 `_sanitize_log_line`)
- 怪谈(rule_horror)卡片按文风规范不放图片
