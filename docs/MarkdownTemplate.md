### 长文字展示模版(代码块展示长文字，用户可以点击进行展开)
模板ID：102499345_1771611841
```
# {{.title}}
```
{{.desc}}
```
***
> {{.hint}} <qqbot-cmd-input text="{{.t1}}" /> <qqbot-cmd-input text="{{.t2}}" /> <qqbot-cmd-input text="{{.t3}}" />
```

### 文字展示模版
模板ID：102499345_1770890617
```
#{{.title}}
{{.desc}}
***
><qqbot-cmd-input text="{{.t1}}" /> <qqbot-cmd-input text="{{.t2}}" /> <qqbot-cmd-input text="{{.t3}}" /> <qqbot-cmd-input text="{{.t4}}" />
```
### 图鉴类模版
模版ID：102499345_1769178984
```
#{{.title}}
*{{.desc}}*

![img #{{.width}}px #{{.height}}px]({{.imgurl}})
***
>{{.hint}}
```

### 带按钮的图鉴类模版
模板ID：102499345_1770445216
```
#{{.title}}
*{{.desc}}*
​
![img #{{.width}}px #{{.height}}px]({{.imgurl}})
***
>{{.hint}} <qqbot-cmd-input text="{{.t1}}" /> <qqbot-cmd-input text="{{.t2}}" /> <qqbot-cmd-input text="{{.t3}}" /> <qqbot-cmd-input text="{{.t4}}" />
```

### 物品列表类模版
模版ID：102499345_1769177949
```
***
1. <qqbot-cmd-input text="{{.btn1}}" />
2. <qqbot-cmd-input text="{{.btn2}}" />
3. <qqbot-cmd-input text="{{.btn3}}" />
4. <qqbot-cmd-input text="{{.btn4}}" />
5. <qqbot-cmd-input text="{{.btn5}}" />
6. <qqbot-cmd-input text="{{.btn6}}" />
7. <qqbot-cmd-input text="{{.btn7}}" />
8. <qqbot-cmd-input text="{{.btn8}}" />
9. <qqbot-cmd-input text="{{.btn9}}" />
10. <qqbot-cmd-input text="{{.btn10}}" />
***
```

### 反馈类模版
模版ID：102499345_1769177016
```
# {{.title}}

{{.result}}

***

<qqbot-cmd-input text="{{.btn1}}" />
<qqbot-cmd-input text="{{.btn2}}" />
<qqbot-cmd-input text="{{.btn3}}" />
<qqbot-cmd-input text="{{.btn4}}" />

***

<qqbot-cmd-input text="{{.btn5}}" />
<qqbot-cmd-input text="{{.btn6}}" />
<qqbot-cmd-input text="{{.btn7}}" />
<qqbot-cmd-input text="{{.btn8}}" />
```

### 无换行的连续按钮
模版ID：102499345_1768473387
```
<qqbot-cmd-input text="{{.t1}}" /><qqbot-cmd-input text="{{.t2}}" /><qqbot-cmd-input text="{{.t3}}" /><qqbot-cmd-input text="{{.t4}}" /><qqbot-cmd-input text="{{.t5}}" /><qqbot-cmd-input text="{{.t6}}" /><qqbot-cmd-input text="{{.t7}}" /><qqbot-cmd-input text="{{.t8}}" /><qqbot-cmd-input text="{{.t9}}" /><qqbot-cmd-input text="{{.t10}}" />
```

---

## 高级技巧：通过参数注入实现110个按钮

### 原理说明

QQ Markdown模板引擎支持一个占位符对应**多个values**，这些values会被**依次拼接**到占位符位置。
利用这个特性，可以通过巧妙的字符串拆分，将10个占位符扩展成110个按钮。

### 核心机制

1. **模板定义**：10个占位符（t1-t10）
2. **参数注入**：每个占位符对应一个values数组，包含10个字符串片段
3. **字符串拼接**：模板引擎将values数组中的所有字符串依次拼接到占位符位置
4. **标签拆分**：通过在合适位置拆分XML标签，使拼接后形成完整的按钮序列

### 实现示例

#### 模板结构
使用"无换行的连续按钮"模板（ID: 102499345_1768473387）

#### 参数构造
```python
"params": [
    {
        "key": "t1",
        "values": [
            r'输入按钮1" show="按钮1" />文本1<qqbot-cmd-input text="输入按钮2" show="按钮2',
            r'" />文本2<qqbot-cmd-input text="输入按钮3" show="按钮3',
            r'" />文本3<qqbot-cmd-input text="输入按钮4" show="按钮4',
            r'" />文本4<qqbot-cmd-input text="输入按钮5" show="按钮5',
            r'" />文本5<qqbot-cmd-input text="输入按钮6" show="按钮6',
            r'" />文本6<qqbot-cmd-input text="输入按钮7" show="按钮7',
            r'" />文本7<qqbot-cmd-input text="输入按钮8" show="按钮8',
            r'" />文本8<qqbot-cmd-input text="输入按钮9" show="按钮9',
            r'" />文本9<qqbot-cmd-input text="输入按钮10" show="按钮10',
            r'" />文本10<qqbot-cmd-input show="按钮11" text="输入按钮11',
        ]
    },
    {
        "key": "t2",
        "values": [
            r'输入按钮12" show="按钮12" />文本11<qqbot-cmd-input text="输入按钮13" show="按钮13',
            r'" />文本12<qqbot-cmd-input text="输入按钮14" show="按钮14',
            r'" />文本13<qqbot-cmd-input text="输入按钮15" show="按钮15',
            r'" />文本14<qqbot-cmd-input text="输入按钮16" show="按钮16',
            r'" />文本15<qqbot-cmd-input text="输入按钮17" show="按钮17',
            r'" />文本16<qqbot-cmd-input text="输入按钮18" show="按钮18',
            r'" />文本17<qqbot-cmd-input text="输入按钮19" show="按钮19',
            r'" />文本18<qqbot-cmd-input text="输入按钮20" show="按钮20',
            r'" />文本19<qqbot-cmd-input text="输入按钮21" show="按钮21',
            r'" />文本20<qqbot-cmd-input show="按钮22" text="输入按钮22',
        ]
    },
    
    # t3-t10 类似结构...
]
```

#### 拼接过程

**模板占位符**：
```
<qqbot-cmd-input text="{{.t1}}" />
```

**拼接后结果**：
```
<qqbot-cmd-input text="输入按钮1" show="按钮1" />文本1
<qqbot-cmd-input text="输入按钮2" show="按钮2" />文本2
<qqbot-cmd-input text="输入按钮3" show="按钮3" />文本3
...
<qqbot-cmd-input text="输入按钮11" show="按钮11" />
```

### 关键技巧

1. **第一个片段**：包含完整的第一个按钮 + 第二个按钮的开始部分
   ```
   输入按钮1" show="按钮1" />文本1<qqbot-cmd-input text="输入按钮2" show="按钮2
   ```

2. **中间片段**：补全上一个按钮 + 开始下一个按钮
   ```
   " />文本2<qqbot-cmd-input text="输入按钮3" show="按钮3
   ```

3. **最后片段**：补全倒数第二个按钮 + 完整的最后一个按钮开始
   ```
   " />文本10<qqbot-cmd-input show="按钮11" text="输入按钮11
   ```

### 拆分点选择

- 在 `"` 和 `/>` 之间拆分，确保拼接后语法正确
- 每个片段都在合适位置断开，形成"不完整标签"
- 拼接时自动补全，形成完整的XML标签序列

### 计算公式

- **10个key** × **每个key生成11个按钮** = **110个按钮**
- 每个key的10个values片段生成11个按钮的原因：
  - 第1个片段包含1个完整按钮 + 1个不完整开始
  - 后续9个片段各补全1个按钮
  - 最后1个片段补全最后1个按钮

### 优势

1. **突破限制**：将10个占位符扩展为110个按钮
2. **灵活性高**：可以自定义每个按钮的文本和命令
3. **无需新模板**：复用已有模板，无需申请新的模板ID

### 注意事项

- 字符串拆分位置必须精确，否则会导致标签不完整
- 需要仔细处理引号和特殊字符的转义
- 建议使用原始字符串（r''）避免转义问题
- 这是一个hack技巧，利用了模板引擎的拼接特性

### 注意
模版参数中不能包含markdown语法，换行符必须使用\r而不是\n
玩家头像获取链接：https://thirdqq.qlogo.cn/qqapp/102499345/玩家在QQ官方的id/0