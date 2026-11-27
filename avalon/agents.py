"""AI 玩家：把待办动作翻译成提示词，再把模型回复解析成合法动作。

解析失败时总有一个合法的兜底动作，保证游戏不会卡死。
"""
import logging

from . import prompts
from .constants import GOOD
from .parsing import clean_speech, find_field, parse_binary, parse_names, remove_field_lines

log = logging.getLogger("avalon.agents")

TASKS = {
    "propose": prompts.task_propose,
    "speak": prompts.task_speak,
    "speak_summary": prompts.task_summary,
    "vote": prompts.task_vote,
    "card": prompts.task_card,
    "discuss": prompts.task_discuss,
    "assassin_discuss": prompts.task_assassin_discuss,
    "assassinate": prompts.task_assassinate,
}

FALLBACK_SPEECH = "我先听听大家的看法。"


def needs_llm(game, player, action):
    # 好人只能出成功牌，没有可选项，不必调用模型
    return not (action == "card" and game.sides[player] == GOOD)


def task_for(game, player, action):
    return TASKS[action](game)


def apply(game, player, action, text):
    """解析回复并执行动作。text 为空表示模型调用失败或被拒绝。"""
    text = text or ""

    if action == "propose":
        n = game.team_size
        team = parse_names(find_field(text, "提名", "提名名单", "队伍"), game.players)
        if len(team) != n:
            log.info("%s 的提名无法解析，使用兜底队伍：%r", player, text[:200])
            others = [p for p in game.players if p != player]
            team = [player] + game.rng.sample(others, n - 1)
        reason = find_field(text, "理由") or "综合判断后提名这几位。"
        game.propose(player, team, reason)

    elif action == "speak":
        game.speak(player, clean_speech(text, player) or FALLBACK_SPEECH)

    elif action == "speak_summary":
        new_team = parse_names(find_field(text, "新提名"), game.players)
        if len(new_team) != game.team_size:
            new_team = None
        speech = clean_speech(remove_field_lines(text, "新提名"), player) or "维持原队伍。"
        game.speak(player, speech, new_team)

    elif action == "vote":
        v = parse_binary(text, "投票", "同意", "反对")
        if v is None:
            log.info("%s 的投票无法解析，默认同意：%r", player, text[:200])
            v = True
        game.vote(player, v)

    elif action == "card":
        if game.sides[player] == GOOD:
            game.play_card(player, True)
        else:
            v = parse_binary(text, "出牌", "成功", "失败")
            game.play_card(player, True if v is None else v)

    elif action == "discuss":
        game.discuss(player, clean_speech(text, player) or FALLBACK_SPEECH)

    elif action == "assassin_discuss":
        game.assassin_discuss(player, clean_speech(text, player) or "我还没想好。")

    elif action == "assassinate":
        candidates = game.assassin_candidates()
        picked = parse_names(find_field(text, "刺杀", "目标"), candidates)
        target = picked[0] if picked else game.rng.choice(candidates)
        game.assassinate(player, target)

    else:
        raise ValueError(f"未知动作：{action}")
