# 鱼类配图说明

## 📁 文件夹用途
此文件夹用于存放鱼类物品的配图，当玩家使用【图鉴 鱼类名称】命令查询鱼类时，如果该鱼类有配图，将使用Markdown模板展示带图片的精美图鉴。

## 🖼️ 图片命名规则
图片文件名必须与物品ID完全一致（不含扩展名）。

### 鱼类物品ID列表

#### 白色品质（普通鱼类）
- `common_carp` - 鲤鱼
- `crucian_carp` - 鲫鱼
- `grass_carp` - 草鱼
- `silver_carp` - 鲢鱼
- `catfish` - 鲶鱼

#### 绿色品质
- `bass` - 鲈鱼
- `mandarin_fish` - 桂鱼
- `yellow_croaker` - 黄花鱼
- `pomfret` - 鲳鱼
- `snapper` - 鲷鱼

#### 蓝色品质
- `salmon` - 三文鱼
- `tuna` - 金枪鱼
- `grouper` - 石斑鱼
- `eel` - 鳗鱼
- `turbot` - 多宝鱼

#### 紫色品质（稀有）
- `chinese_sturgeon` - 中华鲟
- `arowana` - 龙鱼
- `giant_catfish` - 巨型鲶鱼
- `bluefin_tuna` - 蓝鳍金枪鱼

#### 橙色品质（传说）
- `golden_dragon_fish` - 金龙鱼
- `phoenix_fish` - 凤凰鱼
- `void_fish` - 虚空鱼

## 📝 命名示例
```
common_carp.png      ✅ 正确
common_carp.jpg      ✅ 正确
鲤鱼.png             ❌ 错误（应使用物品ID）
CommonCarp.png       ❌ 错误（大小写不匹配）
```

## 🎨 支持的图片格式
- `.png` (推荐)
- `.jpg` / `.jpeg`
- `.gif`
- `.webp`

## 📐 图片建议
- 推荐尺寸：200x200 像素或更大
- 推荐格式：PNG（支持透明背景）
- 文件大小：建议不超过500KB

## 🔧 使用方法
1. 将图片文件放入此文件夹
2. 确保文件名与物品ID完全一致
3. 玩家使用【图鉴 鱼类名称】即可查看带配图的图鉴

## ⚠️ 注意事项
- 图片URL目前使用占位符，实际使用时需要上传到QQ官方图床
- 修改 `plugins/xiuxian_game/item/catalog.py` 中的 `_get_fish_image_url` 函数，将占位URL替换为真实图床URL
- 如果图片不存在，将使用普通文本格式展示图鉴信息

## 🌐 图床配置
当前图片URL格式：`https://example.com/fish/{item_id}{ext}`

需要将图片上传到QQ官方图床或其他可访问的图床，然后修改代码中的URL模板。
