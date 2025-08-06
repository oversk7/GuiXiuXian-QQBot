from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
import hashlib
from datetime import datetime

# 抽签功能
fortune_telling = on_command("抽签", aliases={"求签", "灵签"}, priority=5, block=True)

# 签文数据 - 基于中国传统观音灵签
FORTUNE_SIGNS = {
    1: {
        "name": "第一签 宋太祖黄袍加身",
        "level": "上上签",
        "poem": "天开地辟结良缘\n日吉时良万事全\n若得此签非小可\n人行忠正帝王宣",
        "meaning": "此签大吉，如天地初开，万象更新。凡事顺遂，贵人相助，前程似锦。",
        "advice": "行事正直，把握时机，必有贵人扶持，前途光明。",
        "fortune": "🌟 大吉大利",
        "emoji": "👑"
    },
    2: {
        "name": "第二签 姜太公遇文王",
        "level": "上上签", 
        "poem": "鲲鹏展翅九万里\n风云际会正此时\n一朝得遇明主赏\n高飞远举任东西",
        "meaning": "如鲲鹏展翅，遇风云际会。时机已到，将遇贵人提携，大展宏图。",
        "advice": "耐心等待，机会即将到来，要有远大志向，准备迎接转机。",
        "fortune": "🌟 大吉大利",
        "emoji": "🦅"
    },
    3: {
        "name": "第三签 董永遇仙",
        "level": "上签",
        "poem": "临风冉冉去如飞\n金榜题名遂所期\n若问求谋并出入\n定保平安得所归",
        "meaning": "如临风而飞，金榜题名在望。所求之事将会成功，出入平安。",
        "advice": "努力学习，积极进取，成功在望，但需脚踏实地。",
        "fortune": "🎯 吉利",
        "emoji": "📚"
    },
    4: {
        "name": "第四签 玉兔望月",
        "level": "中签",
        "poem": "玉兔当空照九州\n常娥有意下凡游\n全凭一点真诚意\n守得云开见日头",
        "meaning": "如玉兔望月，虽有美好愿望，但需耐心等待时机成熟。",
        "advice": "保持真诚之心，耐心等待，云开雾散之时便是成功之日。",
        "fortune": "⭐ 平吉",
        "emoji": "🌙"
    },
    5: {
        "name": "第五签 关公赴会",
        "level": "中签",
        "poem": "一舟行过大江心\n风浪滔滔欲损人\n幸得船中有好客\n相扶相助过风波",
        "meaning": "如行舟遇风浪，虽有困难，但有贵人相助，终能化险为夷。",
        "advice": "遇到困难不要慌张，寻求朋友帮助，团结协作可渡难关。",
        "fortune": "⭐ 平吉",
        "emoji": "⛵"
    },
    6: {
        "name": "第六签 包公审案",
        "level": "上签",
        "poem": "何须问我是和非\n皎皎明月正当时\n直须守正心无愧\n此意投君君必知",
        "meaning": "如明月当空，光明正大。只要心正行直，自有公道，无需担忧。",
        "advice": "坚持正义，问心无愧，真相自会大白，正义终将得到伸张。",
        "fortune": "🎯 吉利",
        "emoji": "⚖️"
    },
    7: {
        "name": "第七签 苏秦刺股",
        "level": "中签",
        "poem": "十年窗下苦功深\n有志竟成不负心\n一旦时来当得意\n望前程事事如心",
        "meaning": "十年寒窗苦读，有志者事竟成。时机一到，必能如愿以偿。",
        "advice": "持之以恒，刻苦努力，机会总是留给有准备的人。",
        "fortune": "⭐ 平吉",
        "emoji": "📖"
    },
    8: {
        "name": "第八签 八仙过海",
        "level": "上签",
        "poem": "八仙过海显神通\n各有妙法度苍穹\n若问前程何所似\n前途万里任西东",
        "meaning": "如八仙过海，各显神通。前程似锦，可任意驰骋天下。",
        "advice": "发挥自己的特长，勇敢追求理想，前途无量。",
        "fortune": "🎯 吉利",
        "emoji": "🌊"
    },
    9: {
        "name": "第九签 孟母三迁",
        "level": "中签",
        "poem": "望子成龙母心切\n三迁择邻为教育\n环境造就人品格\n近朱者赤近墨黑",
        "meaning": "如孟母三迁，环境对人影响深远。选择良好环境，方能成就大业。",
        "advice": "注重环境选择，亲近良师益友，远离不良影响。",
        "fortune": "⭐ 平吉",
        "emoji": "🏠"
    },
    10: {
        "name": "第十签 卧薪尝胆",
        "level": "中下签",
        "poem": "卧薪尝胆志不移\n十年生聚十年教\n一朝雪耻酬壮志\n苦尽甘来福自来",
        "meaning": "如越王勾践，虽遭挫折，但能忍辱负重，终能雪耻成功。",
        "advice": "暂时的困难是成功的垫脚石，坚持不懈，终将苦尽甘来。",
        "fortune": "⚠️ 需忍耐",
        "emoji": "🗡️"
    },
    11: {
        "name": "第十一签 桃园结义",
        "level": "上签",
        "poem": "桃园结义情如海\n三人同心力断金\n若遇困难相扶助\n患难与共见真心",
        "meaning": "如桃园三结义，情深如海。朋友相助，同心协力，无往不胜。",
        "advice": "珍惜友情，团结合作，患难见真情，共同面对挑战。",
        "fortune": "🎯 吉利",
        "emoji": "🤝"
    },
    12: {
        "name": "第十二签 昭君出塞",
        "level": "中签",
        "poem": "昭君出塞为和亲\n舍小家为大家安\n虽然离别心中苦\n换得边疆百年宁",
        "meaning": "如昭君出塞，虽有牺牲，但为大局着想。暂时的离别换来长久的安宁。",
        "advice": "有时需要做出牺牲，为了更大的利益，暂时的痛苦是值得的。",
        "fortune": "⭐ 平吉",
        "emoji": "🎭"
    },
    13: {
        "name": "第十三签 孔明借箭",
        "level": "上签",
        "poem": "草船借箭显奇谋\n三日之内箭如雨\n智者千虑必有得\n借力使力事半功",
        "meaning": "如孔明草船借箭，智谋过人。善用外力，巧妙解决难题。",
        "advice": "运用智慧，借助外力，巧妙解决问题，事半功倍。",
        "fortune": "🎯 吉利",
        "emoji": "🏹"
    },
    14: {
        "name": "第十四签 嫦娥奔月",
        "level": "中签",
        "poem": "嫦娥奔月离人间\n独居广寒宫中寒\n虽得长生不老药\n孤单寂寞谁人怜",
        "meaning": "如嫦娥奔月，虽得所求，但也有失落。得失之间需要权衡。",
        "advice": "追求理想时要考虑代价，有得必有失，需要做好心理准备。",
        "fortune": "⭐ 平吉",
        "emoji": "🌕"
    },
    15: {
        "name": "第十五签 精卫填海",
        "level": "中下签",
        "poem": "精卫填海志不移\n日复一日不言疲\n虽然大海深无底\n精神可嘉天地知",
        "meaning": "如精卫填海，虽然目标遥远，但精神可嘉。坚持不懈，终有所成。",
        "advice": "目标虽然遥远，但要坚持不懈，精神的力量终将感动天地。",
        "fortune": "⚠️ 需坚持",
        "emoji": "🐦"
    },
    16: {
        "name": "第十六签 愚公移山",
        "level": "中签",
        "poem": "愚公移山志如钢\n子子孙孙无穷尽\n山不加增何患焉\n诚心所至金石开",
        "meaning": "如愚公移山，虽然困难重重，但有恒心毅力，终能成功。",
        "advice": "面对困难要有恒心，持之以恒，诚心所至，金石为开。",
        "fortune": "⭐ 平吉",
        "emoji": "⛰️"
    },
    17: {
        "name": "第十七签 司马光砸缸",
        "level": "上签",
        "poem": "司马光砸缸救友\n急中生智显身手\n不拘常理敢创新\n救人一命胜造塔",
        "meaning": "如司马光砸缸，急中生智，不拘常理。创新思维能解决大问题。",
        "advice": "遇到紧急情况要冷静思考，敢于创新，不拘泥于常规。",
        "fortune": "🎯 吉利",
        "emoji": "🏺"
    },
    18: {
        "name": "第十八签 岳飞精忠",
        "level": "上签",
        "poem": "精忠报国志如山\n直捣黄龙不畏难\n虽遭奸佞暗中害\n忠心耿耿照汗青",
        "meaning": "如岳飞精忠报国，忠心耿耿。虽遭小人陷害，但忠义之名永垂不朽。",
        "advice": "坚持正义，忠于理想，即使遭遇挫折也不改初心。",
        "fortune": "🎯 吉利",
        "emoji": "🛡️"
    },
    19: {
        "name": "第十九签 木兰从军",
        "level": "上签",
        "poem": "木兰从军代父征\n巾帼不让须眉英\n十二年来无人识\n归来仍是女儿身",
        "meaning": "如花木兰代父从军，巾帼不让须眉。勇敢承担责任，终获成功。",
        "advice": "勇于承担责任，不要被外在条件限制，内在品质更重要。",
        "fortune": "🎯 吉利",
        "emoji": "⚔️"
    },
    20: {
        "name": "第二十签 大禹治水",
        "level": "上上签",
        "poem": "大禹治水为苍生\n三过家门而不入\n疏导江河归大海\n功德无量万世名",
        "meaning": "如大禹治水，为民造福，功德无量。舍小家为大家，必获成功。",
        "advice": "要有为民服务的精神，舍己为人，功德无量，必获成功。",
        "fortune": "🌟 大吉大利",
        "emoji": "🌊"
    },
    21: {
        "name": "第二十一签 项羽乌江",
        "level": "下签",
        "poem": "力拔山兮气盖世\n时不利兮骓不逝\n骓不逝兮可奈何\n虞兮虞兮奈若何",
        "meaning": "如项羽乌江自刎，虽有盖世之才，但时运不济，英雄末路。",
        "advice": "时运不佳时要懂得退让，保存实力，等待时机再起。",
        "fortune": "❌ 不利",
        "emoji": "⚔️"
    },
    22: {
        "name": "第二十二签 孟姜女哭长城",
        "level": "下签",
        "poem": "孟姜女哭倒长城\n夫君不归泪如雨\n千里寻夫到边关\n只见白骨不见人",
        "meaning": "如孟姜女哭长城，思君不见，徒增悲伤。所求之事恐难如愿。",
        "advice": "不要过分执着于不可能的事情，学会放下，寻找新的方向。",
        "fortune": "❌ 不利",
        "emoji": "😢"
    },
    23: {
        "name": "第二十三签 范蠡泛舟",
        "level": "上签",
        "poem": "范蠡泛舟五湖游\n功成身退不恋权\n明哲保身知进退\n逍遥自在乐悠悠",
        "meaning": "如范蠡功成身退，明哲保身。知道进退之道，能够逍遥自在。",
        "advice": "要懂得适时退让，功成身退，明哲保身，方能长久。",
        "fortune": "🎯 吉利",
        "emoji": "🚣"
    },
    24: {
        "name": "第二十四签 伯牙摔琴",
        "level": "中下签",
        "poem": "伯牙摔琴谢知音\n子期不在为谁弹\n高山流水无人赏\n琴断弦绝心亦寒",
        "meaning": "如伯牙摔琴，失去知音，心灰意冷。缺少理解和支持。",
        "advice": "要珍惜身边的知音好友，失去后要学会重新开始。",
        "fortune": "⚠️ 需调整",
        "emoji": "🎵"
    },
    25: {
        "name": "第二十五签 商汤祷雨",
        "level": "上签",
        "poem": "商汤祷雨为民忧\n以身作则感苍天\n甘露普降润大地\n德政感化万民心",
        "meaning": "如商汤祷雨，心系百姓，以身作则。德政感化，必获成功。",
        "advice": "要有仁爱之心，以身作则，德行感化他人，必获成功。",
        "fortune": "🎯 吉利",
        "emoji": "🌧️"
    },
    26: {
        "name": "第二十六签 杨贵妃醉酒",
        "level": "中下签",
        "poem": "贵妃醉酒误朝政\n红颜祸水古来有\n沉迷享乐忘根本\n繁华过后是空虚",
        "meaning": "如杨贵妃醉酒，沉迷享乐，忘记根本。繁华过后终是空虚。",
        "advice": "不要沉迷于享乐，要脚踏实地，注重内在修养。",
        "fortune": "⚠️ 需警醒",
        "emoji": "🍷"
    },
    27: {
        "name": "第二十七签 陶渊明归隐",
        "level": "中签",
        "poem": "不为五斗米折腰\n归隐田园乐逍遥\n采菊东篱下悠然\n见南山处心境高",
        "meaning": "如陶渊明归隐，不为名利折腰。虽然清贫，但心境高远。",
        "advice": "要保持高尚品格，不为名利所累，内心的平静更珍贵。",
        "fortune": "⭐ 平吉",
        "emoji": "🌻"
    },
    28: {
        "name": "第二十八签 屈原投江",
        "level": "下下签",
        "poem": "屈原投江殉理想\n忠君爱国无人懂\n举世皆浊我独清\n宁死不与世同流",
        "meaning": "如屈原投江，虽有高尚理想，但不被理解，孤独无助。",
        "advice": "理想虽好，但要考虑现实，适当妥协，保存自己才能实现理想。",
        "fortune": "💀 大凶",
        "emoji": "🌊"
    },
    29: {
        "name": "第二十九签 文姬归汉",
        "level": "中签",
        "poem": "文姬归汉别胡儿\n十二年来梦故乡\n虽然骨肉难分离\n终得回归汉家邦",
        "meaning": "如蔡文姬归汉，虽有离别之苦，但终能回归故土。",
        "advice": "虽然过程艰难，但要坚持初心，终能达成心愿。",
        "fortune": "⭐ 平吉",
        "emoji": "🏠"
    },
    30: {
        "name": "第三十签 李白醉酒",
        "level": "中签",
        "poem": "李白醉酒诗百篇\n才华横溢震九天\n虽然仕途多坎坷\n诗名千古永流传",
        "meaning": "如李白醉酒作诗，才华横溢。虽然仕途不顺，但才名永存。",
        "advice": "要发挥自己的才华，即使遇到挫折也不要放弃理想。",
        "fortune": "⭐ 平吉",
        "emoji": "🍶"
    }
}

def get_fortune_by_seed(player_id: str, date_hour: str) -> dict:
    """根据玩家ID和时辰生成固定的签文"""
    # 将玩家ID和日期时辰组合作为种子
    seed_str = f"{player_id}_{date_hour}"
    # 使用MD5生成哈希值
    hash_obj = hashlib.md5(seed_str.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    # 取前8位转为整数，然后模运算得到签号
    hash_int = int(hash_hex[:8], 16)
    sign_number = (hash_int % len(FORTUNE_SIGNS)) + 1
    
    return FORTUNE_SIGNS[sign_number]

def get_current_date_hour() -> str:
    """获取当前日期和时辰"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    
    # 中国传统时辰对应表
    hour = now.hour
    if 23 <= hour or hour < 1:
        time_period = "子时"
    elif 1 <= hour < 3:
        time_period = "丑时"
    elif 3 <= hour < 5:
        time_period = "寅时"
    elif 5 <= hour < 7:
        time_period = "卯时"
    elif 7 <= hour < 9:
        time_period = "辰时"
    elif 9 <= hour < 11:
        time_period = "巳时"
    elif 11 <= hour < 13:
        time_period = "午时"
    elif 13 <= hour < 15:
        time_period = "未时"
    elif 15 <= hour < 17:
        time_period = "申时"
    elif 17 <= hour < 19:
        time_period = "酉时"
    elif 19 <= hour < 21:
        time_period = "戌时"
    else:  # 21 <= hour < 23
        time_period = "亥时"
    
    return f"{date_str}_{time_period}"

@fortune_telling.handle()
async def handle_fortune_telling(event: MessageEvent):
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await session.get(Player, user_id)
        if not player:
            await fortune_telling.finish("您还没有创建角色，请先注册。")
        
        # 获取当前日期和时辰
        date_hour = get_current_date_hour()
        
        # 根据玩家ID和时辰获取固定签文
        sign_data = get_fortune_by_seed(user_id, date_hour)
        
        # 构建签文消息
        msg = (
            f"🏮 ═══ 观音灵签 ═══ 🏮\n"
            f"\n"
            f"{sign_data['emoji']} {sign_data['name']}\n"
            f"📜 签别：{sign_data['level']}\n"
            f"\n"
            f"📝 签诗：\n"
            f"{sign_data['poem']}\n"
            f"\n"
            f"🔮 签意：\n"
            f"{sign_data['meaning']}\n"
            f"\n"
            f"💡 建议：\n"
            f"{sign_data['advice']}\n"
            f"\n"
            f"🎯 运势：{sign_data['fortune']}\n"
            f"\n"
            f"⏰ 此签在{date_hour.split('_')[1]}内有效\n"
            f"🙏 心诚则灵，仅供娱乐参考"
        )
        
        await fortune_telling.finish(message_add_head(msg, event))
