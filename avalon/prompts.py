"""构造发给 AI 玩家的提示词。严禁把其他人的身份写进任何玩家的上下文。

结构（利于 Prompt Caching）：
  system[0] 规则与行为准则 —— 所有玩家、所有回合都相同，可缓存
  system[1] 你是谁 + 私密信息 + 性格 —— 每个玩家固定
  user      当前公开局势 + 本次任务 —— 每次都变
"""
import os

from . import config
from .constants import EVIL, MAX_REJECTIONS, MERLIN, MORDRED, MORGANA, OBERON, PERCIVAL, WINS_NEEDED
from .game import ASSASSINATION, DISCUSSION, GAME_OVER

HISTORY_LIMIT = int(os.environ.get("AVALON_HISTORY_LIMIT", "0"))  # 0 = 完整历史

PHASE_LABELS = {
    "propose": "提名阶段", "speaking": "发言阶段", "voting": "投票阶段",
    "mission": "执行任务中", "discussion": "任务后讨论", "assassination": "刺杀阶段",
    "game_over": "游戏结束",
}


def load_rules():
    """读取 agent_context.md。每次调用都重新读，改文件即时生效。"""
    try:
        with open(config.AGENT_CONTEXT_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def rules_block():
    return ("你正在参与阿瓦隆桌游，扮演其中一名玩家。下面是游戏规则与行为准则。\n\n"
            "【游戏规则与行为准则】\n" + load_rules())


def private_block(game, player):
    k = game.knowledge[player]
    r = k["role"]
    lines = [f"你扮演玩家「{player}」。", "", "【你的私密信息】", f"你的角色：{r}（{k['side']}）"]
    if r == MERLIN:
        lines.append(f"你在闭眼环节看到的坏人：{'、'.join(k['sees_evil']) or '无'}"
                     "（莫德雷德对你隐身，可能还有你看不到的坏人）")
        lines.append("警告：你必须隐藏自己是梅林，否则好人赢后你会被刺杀。")
    elif r == PERCIVAL:
        lines.append(f"你在闭眼环节看到的梅林候选人（梅林或莫甘娜，无法区分）：{'、'.join(k['sees_merlin_morgana'])}")
    elif r == OBERON:
        lines.append("你不知道其他坏人是谁，他们也不知道你。梅林能看见你。")
    elif k["side"] == EVIL:
        lines.append(f"你的坏人队友：{'、'.join(k['evil_teammates']) or '无'}")
        if r == MORDRED:
            lines.append("你的特殊能力：梅林看不见你是坏人。")
        elif r == MORGANA:
            lines.append("你的特殊能力：在派西维尔眼中你和梅林一样，他无法区分。")
    persona = game.personalities.get(player)
    if persona:
        lines += ["", "【你的性格】", persona["prompt"]]
    return "\n".join(lines)


def public_block(game):
    g = game
    if g.good_wins >= WINS_NEEDED:
        score = f"【比分】好人已赢{g.good_wins}轮，任务阶段结束，现在是刺杀阶段。"
    elif g.evil_wins >= WINS_NEEDED:
        score = f"【比分】坏人已赢{g.evil_wins}轮，坏人获胜。"
    else:
        score = (f"【比分】好人已赢{g.good_wins}轮（还需{WINS_NEEDED - g.good_wins}轮），"
                 f"坏人已赢{g.evil_wins}轮（还需{WINS_NEEDED - g.evil_wins}轮）。任何一方都尚未获胜。")

    if g.phase == DISCUSSION:
        rnd = (f"当前阶段：任务后讨论（刚完成第{g.mission_idx}轮，"
               f"第{g.mission_idx + 1}轮即将开始，需{g.team_size}人出任）")
    elif g.phase in (ASSASSINATION, GAME_OVER):
        rnd = f"当前阶段：{PHASE_LABELS[g.phase]}"
    else:
        rnd = f"当前阶段：{PHASE_LABELS[g.phase]}，第{g.mission_idx + 1}轮任务（共5轮），本轮需{g.team_size}人出任"

    double = (f"第{g.double_fail_idx + 1}轮任务需要2张失败牌才算失败。"
              if g.double_fail_idx is not None else "")
    lines = [
        "【公开游戏状态】",
        f"玩家（座位顺序）：{'、'.join(g.players)}",
        f"各轮出任人数：{'/'.join(map(str, g.mission_sizes))}。{double}",
        f"当前队长：{g.leader}",
        score,
        rnd,
        f"连续否决：{g.consecutive_rejections}次（连续{MAX_REJECTIONS}次否决后，下一次提名强制执行）",
    ]
    if g.proposed_team:
        lines.append(f"本轮提名队伍：{'、'.join(g.proposed_team)}")
    for r in g.mission_results:
        s = "✅成功" if r["success"] else "❌失败"
        lines.append(f"第{r['mission']}轮{s}（{r['fail_count']}张失败牌），出任：{'、'.join(r['team'])}")

    # 完整的公开记录：发言、投票揭示、任务结果。投票模式是推理的关键线索。
    entries = g.log[-HISTORY_LIMIT:] if HISTORY_LIMIT else g.log
    history = [f"  {e['player']}：{e['text']}" for e in entries if e["text"] != "🃏 已打出任务牌"]
    if history:
        lines += ["", "【公开记录（按时间顺序）】", *history]
    return "\n".join(lines)


def build(game, player, task):
    """返回 (system_blocks, user_text)。system_blocks 是 [(text, cacheable)]。"""
    system = [(rules_block(), True), (private_block(game, player), False)]
    user = f"{public_block(game)}\n\n【现在轮到你】\n{task}"
    return system, user


# ── 各动作的任务说明 ───────────────────────────────────────────

def task_propose(game):
    n = game.team_size
    return (f"你是本轮队长，从以下玩家中提名{n}人执行任务：{'、'.join(game.players)}\n"
            f"请给出提名名单和公开理由（理由会被所有人看到）。\n"
            f"严格按以下格式回复，不要输出其他内容：\n"
            f"提名：玩家A、玩家B（用顿号分隔，共{n}人）\n理由：xxx")


def task_speak(game):
    return (f"本轮提名队伍：{'、'.join(game.proposed_team)}。\n"
            f"请给出你对这次提名的看法（1-2句），可以支持、质疑或表达观察。\n"
            f"根据你的角色利益决定立场，注意不要暴露你的真实身份。\n"
            f"只输出发言内容，不要加前缀或标签。")


def task_summary(game):
    n = game.team_size
    return (f"你是本轮队长，原提名队伍：{'、'.join(game.proposed_team)}。\n"
            f"你已听完所有人的意见，现在请做总结发言（2-3句），可回应质疑。\n"
            f"你可以保持原队伍，或更换部分成员（共需{n}人，可从{'、'.join(game.players)}中选）。\n"
            f"若要更换队伍，在发言末尾另起一行写：新提名：玩家A、玩家B\n"
            f"若维持原队伍，无需此行。只输出发言内容（含可选的新提名行），不要加其他前缀或标签。")


def task_vote(game):
    return (f"本轮提名队伍：{'、'.join(game.proposed_team)}。所有人已发言完毕，现在秘密投票。\n"
            f"严格按格式只回复一行：投票：同意 或 投票：反对")


def task_card(game):
    need = 2 if game.double_fail_idx == game.mission_idx else 1
    return (f"你在任务队伍（{'、'.join(game.mission_queue)}）中，现在秘密打出任务牌。\n"
            f"本轮需要{need}张失败牌任务才会失败。"
            f"当前局势：好人{game.good_wins}胜，坏人{game.evil_wins}胜，第{game.mission_idx + 1}轮。\n"
            f"严格按格式只回复一行：出牌：成功 或 出牌：失败")


def task_discuss(game):
    last = game.mission_results[-1]
    result = "成功" if last["success"] else "失败"
    return (f"刚才的任务结果：{result}（{last['fail_count']}张失败牌），出任队伍：{'、'.join(last['team'])}。\n"
            f"请发表你的看法（1-2句），分析局势或表达观点。只输出发言内容，不要加前缀或标签。")


def task_assassin_discuss(game):
    return (f"好人完成了{WINS_NEEDED}轮任务，现在是刺杀阶段，坏人已亮明身份：{'、'.join(game.evil_players())}。\n"
            f"刺客是{game.assassin}。你正在和坏人队友公开讨论刺杀目标。\n"
            f"候选人（梅林在其中）：{'、'.join(game.assassin_candidates())}\n"
            f"回顾整场游戏的发言和投票模式，分析谁最可能是梅林（1-2句）。只输出发言内容，不要加前缀或标签。")


def task_assassinate(game):
    return (f"刺杀讨论结束。你是刺客，现在做最终决定。\n"
            f"候选人（梅林在其中）：{'、'.join(game.assassin_candidates())}\n"
            f"综合队友的分析和你自己的判断，选择刺杀目标。\n"
            f"严格按格式回复：\n刺杀：玩家名\n理由：xxx")
