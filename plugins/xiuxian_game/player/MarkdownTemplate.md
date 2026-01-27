### 图鉴类模版
模版ID：102499345_1769178984
```
#{{.title}}
*{{.desc}}*

![img #{{.width}}px #{{.height}}px]({{.imgurl}})
***
>{{.hint}}
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


### 注意
模版参数中不能包含markdown语法，换行符必须使用\r而不是\n
玩家头像获取链接：https://thirdqq.qlogo.cn/qqapp/102499345/玩家在QQ官方的id/0