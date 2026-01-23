# Markdown模版测试指令说明

## 功能介绍

这是一个用于测试QQ官方平台Markdown模版的指令,模版ID为 `102499345_1768473387`。

## 模版信息

- **模版ID**: 102499345_1768473387
- **模版源码**:
```
<qqbot-cmd-input text="{{.t1}}" />
<qqbot-cmd-input text="{{.t2}}" />
<qqbot-cmd-input text="{{.t3}}" />
<qqbot-cmd-input text="{{.t4}}" />
<qqbot-cmd-input text="{{.t5}}" />
<qqbot-cmd-input text="{{.t6}}" />
<qqbot-cmd-input text="{{.t7}}" />
<qqbot-cmd-input text="{{.t8}}" />
<qqbot-cmd-input text="{{.t9}}" />
<qqbot-cmd-input text="{{.t10}}" />
```

- **支持参数**: t1-t10 (10个文本输入框)
- **传参示例**:
```json
{
  "key": "t1",
  "values": ["签到"]
}
```

## 使用指令

### 1. 基础测试指令

- `/md测试` - 使用默认值测试模版
- `/md测试 参数1 参数2 ...` - 自定义参数测试

### 2. 帮助指令

- `/md测试帮助` - 查看测试帮助信息
- `/markdown测试帮助` - 同上
- `/模版测试帮助` - 同上

## 使用示例

### 示例1: 使用默认值
```
/md测试
```
**输出**: 使用10个默认值 ["签到", "修炼", "突破", "背包", "装备", "战斗", "探索", "社交", "公会", "娱乐"]

### 示例2: 自定义部分参数
```
/md测试 签到 修炼 突破
```
**输出**:
- t1: "签到"
- t2: "修炼"
- t3: "突破"
- t4-t10: 使用默认值

### 示例3: 自定义所有参数
```
/md测试 测试1 测试2 测试3 测试4 测试5 测试6 测试7 测试8 测试9 测试10
```
**输出**: 使用用户提供的10个参数

## 代码结构

### 文件位置
`plugins/xiuxian_game/player/markdown_template_test.py`

### 主要函数

1. `handle_markdown_template_test()` - 处理测试指令
   - 解析用户输入的参数
   - 构建模版参数数组
   - 发送Markdown模版消息

2. `handle_md_test_help()` - 显示帮助信息

## 技术细节

### MessageMarkdown使用
```python
from nonebot.adapters.qq.message import MessageMarkdown

markdown = MessageMarkdown(
    template_id=102499345_1768473387,
    params=template_params  # List[Dict] 格式
)
```

### 参数格式
```python
template_params = [
    {"key": "t1", "values": ["值1"]},
    {"key": "t2", "values": ["值2"]},
    # ... 最多10个参数
]
```

## 注意事项

1. **平台限制**: 仅支持QQ官方平台,其他平台可能无法正常显示
2. **参数数量**: 最多支持10个参数(t1-t10),超出部分会被忽略
3. **参数分隔**: 使用空格分隔各个参数
4. **参数处理**: 如果用户提供的参数不足10个,剩余位置使用默认值填充

## 测试建议

1. 首先使用 `/md测试` 测试模版是否正常加载
2. 然后使用 `/md测试 参数1 参数2 参数3` 测试自定义参数
3. 最后测试边界情况(空参数、超长参数、特殊字符等)

## 后续扩展

可以考虑添加的功能:
- 支持从配置文件读取默认值
- 支持保存常用参数组合
- 支持批量测试多个模版
- 添加参数验证和错误提示
