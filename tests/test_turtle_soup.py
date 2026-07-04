"""海龟汤纯函数与状态流转测试（不触发 LLM/网络）。"""

import pytest

from plugins.xiuxian_game.entertainment import turtle_soup as ts


# ---------------- JSON 提取 ----------------


def test_extract_json_plain():
    data = ts._extract_json('{"verdict": "是", "hint": "注意白烟"}')
    assert data == {"verdict": "是", "hint": "注意白烟"}


def test_extract_json_with_fence_and_think():
    raw = '<think>推理过程</think>```json\n{"hit": [1, 3], "solved": false, "comment": "接近了"}\n```'
    data = ts._extract_json(raw)
    assert data["hit"] == [1, 3]
    assert data["solved"] is False


def test_extract_json_fixes_raw_newlines_in_string():
    raw = '{"hint": "第一行\n第二行"}'
    data = ts._extract_json(raw)
    assert data["hint"] == "第一行\n第二行"


def test_extract_json_rejects_garbage():
    with pytest.raises(ts.SoupLLMError):
        ts._extract_json("这不是JSON")
    with pytest.raises(ts.SoupLLMError):
        ts._extract_json('["数组不是对象"]')


# ---------------- 类型关键词解析 ----------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("猎奇 悬疑", ["猎奇", "悬疑"]),
        ("恐怖 脑洞 反转", ["恐怖", "脑洞", "反转"]),
        ("猎奇　悬疑", ["猎奇", "悬疑"]),  # 全角空格也算分隔
    ],
)
def test_parse_theme_keywords_accepts(text, expected):
    assert ts._parse_theme_keywords(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "猎奇",  # 单个词无空格分隔，视为普通聊天
        "今天上班好累啊",  # 日常聊天
        "这个 谜题类型我想要特别长的描述 哈哈",  # 单词过长
        "a b c d e f g",  # 词数过多
    ],
)
def test_parse_theme_keywords_rejects(text):
    assert ts._parse_theme_keywords(text) == []


# ---------------- 游戏内消息正则 ----------------


@pytest.mark.parametrize(
    "text,action,content",
    [
        ("#提问 咖啡重要吗", "提问", "咖啡重要吗"),
        ("＃提问 全角井号", "提问", "全角井号"),
        ("#猜汤底 凶手是丈夫", "猜汤底", "凶手是丈夫"),
        ("# 提问 带空格", "提问", "带空格"),
    ],
)
def test_action_regex_matches(text, action, content):
    m = ts._ACTION_RE.match(text)
    assert m is not None
    assert m.group(1) == action
    assert m.group(2).strip() == content


@pytest.mark.parametrize("text", ["提问 没有井号", "#提示 xx", "普通聊天"])
def test_action_regex_ignores(text):
    assert ts._ACTION_RE.match(text) is None


# ---------------- 卡片文案 ----------------


def _make_active_session() -> ts.SoupSession:
    session = ts.SoupSession(group_id="g1", host_id="u1")
    session.players["u1"] = ts.SoupPlayer("u1", "甲", score=2)
    session.players["u2"] = ts.SoupPlayer("u2", "乙", score=0)
    session.status = ts.SoupStatus.ACTIVE
    session.puzzle = {
        "title": "倒放的烟",
        "surface": "汤面内容",
        "truth": "汤底内容",
        "key_points": ["要点一", "要点二", "要点三"],
        "difficulty": "中等",
    }
    session.hit_points = {1, 2}
    session.question_count = 5
    return session


def test_puzzle_card_contains_surface_not_truth():
    session = _make_active_session()
    card = ts._puzzle_card(session, 20)
    assert "汤面内容" in card
    assert "汤底内容" not in card
    assert "甲 2分" in card


def test_reveal_card_ranks_players_and_shows_truth():
    session = _make_active_session()
    card = ts._reveal_card(session, timeout=True)
    assert "汤底内容" in card
    assert "2/3" in card
    assert card.index("甲") < card.index("乙")  # 按分数排序
    assert "无人猜出正确答案" in card


def test_reveal_card_solved():
    session = _make_active_session()
    session.solved_by = "甲"
    card = ts._reveal_card(session, timeout=False)
    assert "甲 还原了真相" in card


def _make_qa(i: int) -> dict:
    return {"name": "甲", "q": f"问题{i}", "verdict": "是", "hint": f"提示{i}"}


def test_question_card_latest_on_top_history_in_block():
    qa_log = [_make_qa(1), _make_qa(2), _make_qa(3)]
    card = ts._question_card(qa_log)
    assert "第 3 问" in card
    assert "问题3" in card
    # 历史（最新在前）在代码块中
    block = card[card.index("```text") :]
    assert block.index("问题2") < block.index("问题1")
    assert "提示1" in block
    # 最新一条不重复出现在历史块里
    assert "问题3" not in block


def test_question_card_no_history_no_block():
    card = ts._question_card([_make_qa(1)])
    assert "```" not in card


def test_question_card_truncates_old_history():
    qa_log = [_make_qa(i) for i in range(1, 20)]  # 19 条，历史 18 条
    card = ts._question_card(qa_log)
    assert "问题18" in card  # 最近的历史保留
    assert "问题1 " not in card and "［是］问题1 —" not in card
    assert "更早的 3 条已省略" in card
