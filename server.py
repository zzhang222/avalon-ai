import os
import json
import logging
import random
import threading
import time
from datetime import datetime
import re
import requests as http_requests
from flask import Flask, jsonify, request, send_from_directory
import anthropic

# 屏蔽 werkzeug 每次请求的访问日志
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__, static_folder="static")

# ── LLM 后端配置 ─────────────────────────────────────────────────
# BACKEND = "api"    # 使用 Claude API（效果好，需设置 ANTHROPIC_API_KEY 环境变量）
BACKEND = "ollama"   # 使用本地 Ollama（免费，效果取决于模型）

# Ollama 配置
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3.5:35b"  # 按实际 ollama 中的模型名修改

# API 配置
API_MODEL = "claude-opus-4-6"

_api_client = None
def get_api_client():
    global _api_client
    if _api_client is None:
        _api_client = anthropic.Anthropic()
    return _api_client

# ── 常量 ────────────────────────────────────────────────────────
ROLE_CONFIGS = {
    5: {"good": ["梅林", "派西维尔", "忠臣"], "evil": ["莫德雷德", "莫甘娜"]},
    6: {"good": ["梅林", "派西维尔", "忠臣", "忠臣"], "evil": ["莫德雷德", "莫甘娜"]},
    7: {"good": ["梅林", "派西维尔", "忠臣", "忠臣"], "evil": ["莫德雷德", "莫甘娜", "爪牙"]},
    8: {"good": ["梅林", "派西维尔", "忠臣", "忠臣", "忠臣"], "evil": ["莫德雷德", "莫甘娜", "爪牙"]},
    9: {"good": ["梅林", "派西维尔", "忠臣", "忠臣", "忠臣", "忠臣"], "evil": ["莫德雷德", "莫甘娜", "爪牙"]},
    10: {"good": ["梅林", "派西维尔", "忠臣", "忠臣", "忠臣", "忠臣"], "evil": ["莫德雷德", "莫甘娜", "爪牙", "奥伯龙"]},
}
MISSION_SIZES = {
    5: [2, 3, 2, 3, 3],
    6: [2, 3, 4, 3, 4],
    7: [2, 3, 3, 4, 4],
    8: [3, 4, 4, 5, 5],
    9: [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
}
GOOD_ROLES = {"梅林", "派西维尔", "忠臣"}
EVIL_ROLES = {"莫德雷德", "莫甘娜", "爪牙", "奥伯龙"}

PERSONALITIES = [
    {"name": "反驳型(ENTP)", "prompt": "你喜欢挑战别人的观点，善于找出逻辑漏洞。你说话犀利直接，常用反问句质疑他人，不怕得罪人。你享受辩论的快感，经常故意唱反调来试探他人反应。"},
    {"name": "分析型(INTJ)", "prompt": "你冷静理性，极度注重推理链条和逻辑证据。你言简意赅，从不废话，每句话都有明确目的。你习惯用编号列出论据，对情绪化的发言不屑一顾。"},
    {"name": "领袖型(ENTJ)", "prompt": "你强势主导，喜欢带节奏推动决策。你立场坚定，一旦做出判断就很难被说服。你倾向于直接给出结论并要求大家跟随，说话有命令感。"},
    {"name": "调和型(ENFJ)", "prompt": "你善于整合不同意见，语气温和但有自己的立场。你会先肯定别人再提出不同看法，喜欢用'我们'来拉近关系。你擅长化解冲突，但该坚持时也不退让。"},
    {"name": "怀疑型(ISTP)", "prompt": "你惜字如金，不轻信任何人的说辞。你的发言极简但一针见血，经常用短句表达质疑。你更相信行为和数据而非言语，对夸夸其谈的人天然警惕。"},
    {"name": "表演型(ESFP)", "prompt": "你情绪化，戏剧感强，善于渲染气氛。你说话夸张生动，喜欢用感叹号和比喻。你容易被情绪带动，也善于用情绪影响他人判断，是场上的气氛担当。"},
    {"name": "思考型(INTP)", "prompt": "你沉浸在自己的逻辑世界里，喜欢提出独到的假设和推演。你说话慢条斯理，经常用'如果…那么…'的句式推导可能性。你不在乎社交压力，只关心逻辑是否自洽，有时会提出让人意想不到的角度。"},
    {"name": "理想型(INFP)", "prompt": "你重视直觉和感受，喜欢从动机和人性角度分析问题。你说话柔和但坚定，常用'我感觉…'来表达判断。你对虚伪和欺骗特别敏感，一旦觉得某人不真诚就会执着追问。"},
]

# ── 游戏状态 ─────────────────────────────────────────────────────
G = {}

def log(player, text, t="speech"):
    G["log"].append({"player": player, "text": text, "type": t})

def cur_leader():
    return G["players"][G["leader_idx"] % len(G["players"])]

def propose_speaking_order(proposer):
    """其他人按座位顺序 + 队长总结（队长的提名发言即开场）"""
    ps = G["players"]
    idx = ps.index(proposer)
    others = ps[idx+1:] + ps[:idx]
    return others + [proposer]

def after_propose(team):
    """提名后：若第5次提名则强制执行，否则进入发言阶段。"""
    if G["consecutive_rejections"] >= 4:
        log("主持人", "⚠️ 第5次提名，队伍自动执行！", "system")
        G["consecutive_rejections"] = 0
        G["mission_cards"] = {}
        G["mission_queue"] = team[:]
        G["mission_q_idx"] = 0
        G["phase"] = "mission"
        log("主持人", f"队伍出发执行任务：{'、'.join(team)}", "system")
    else:
        leader = cur_leader()
        G["speak_order"] = propose_speaking_order(leader)
        G["speak_idx"] = 0
        G["phase"] = "speaking"

def init_game(players, user, force_role=None):
    global G
    n = len(players)
    cfg = ROLE_CONFIGS[n]
    roles_list = cfg["good"] + cfg["evil"]

    if force_role and force_role in roles_list:
        roles_list.remove(force_role)
        random.shuffle(roles_list)
        roles_list.insert(players.index(user), force_role)
        roles = dict(zip(players, roles_list))
    else:
        random.shuffle(roles_list)
        roles = dict(zip(players, roles_list))
    sides = {p: ("好人" if r in GOOD_ROLES else "坏人") for p, r in roles.items()}

    evil_all = [p for p, s in sides.items() if s == "坏人"]
    pk = {}
    for p in players:
        r = roles[p]
        if r == "梅林":
            sees = [e for e in evil_all if roles[e] != "莫德雷德"]
            pk[p] = {"role": r, "side": "好人", "sees_evil": sees}
        elif r == "派西维尔":
            sees = [q for q, rr in roles.items() if rr in {"梅林", "莫甘娜"}]
            pk[p] = {"role": r, "side": "好人", "sees_merlin_morgana": sees}
        elif r in {"莫德雷德", "莫甘娜", "爪牙"}:
            teammates = [e for e in evil_all if e != p and roles[e] != "奥伯龙"]
            pk[p] = {"role": r, "side": "坏人", "evil_teammates": teammates}
        elif r == "奥伯龙":
            pk[p] = {"role": r, "side": "坏人", "evil_teammates": []}
        else:
            pk[p] = {"role": r, "side": "好人"}

    double_fail_idx = 3 if n >= 7 else None

    G = {
        "players": players, "user": user,
        "roles": roles, "sides": sides, "pk": pk,
        "n": n, "mission_sizes": MISSION_SIZES[n],
        "double_fail_idx": double_fail_idx,
        "mission_idx": 0, "good_wins": 0, "evil_wins": 0,
        "mission_results": [],
        "phase": "propose",
        "leader_idx": 0, "consecutive_rejections": 0,
        "proposed_team": [],
        "speak_order": [], "speak_idx": 0,
        "ai_votes": {}, "all_votes": {},
        "mission_cards": {}, "mission_queue": [], "mission_q_idx": 0,
        "discuss_order": [], "discuss_idx": 0,
        "assassin": None, "assassin_order": [], "assassin_idx": 0,
        "processing": False,
        "waiting_user": False, "user_action": None,
        "winner": None,
        "log": [],
    }
    # 给AI玩家随机分配人格
    ai_players = [p for p in players if p != user]
    sampled = random.sample(PERSONALITIES, len(ai_players)) if len(ai_players) <= len(PERSONALITIES) else random.choices(PERSONALITIES, k=len(ai_players))
    G["personalities"] = {p: s for p, s in zip(ai_players, sampled)}

    log("主持人", f"游戏开始！{n}人局，角色已随机分配。", "system")
    log("主持人", f"第1轮任务，需要{MISSION_SIZES[n][0]}人出任。队长：{players[0]}", "system")

# ── Agent 上下文生成（严禁泄露其他人角色）─────────────────────────

def agent_private_ctx(player):
    pk = G["pk"][player]
    r = pk["role"]
    lines = [f"你的角色：{r}（{'好人' if pk['side']=='好人' else '坏人'}）"]
    if r == "梅林":
        evil_str = "、".join(pk["sees_evil"]) if pk["sees_evil"] else "无"
        lines.append(f"你在闭眼环节看到的坏人：{evil_str}")
        lines.append("警告：你必须隐藏自己是梅林，否则好人赢后你会被刺杀。")
    elif r == "派西维尔":
        names = "、".join(pk["sees_merlin_morgana"])
        lines.append(f"你在闭眼环节看到的梅林候选人（梅林或莫甘娜，无法区分）：{names}")
    elif r in {"莫德雷德", "莫甘娜", "爪牙"}:
        t = "、".join(pk["evil_teammates"]) if pk["evil_teammates"] else "无"
        lines.append(f"你的坏人队友：{t}")
        if r == "莫德雷德":
            lines.append("你的特殊能力：梅林看不见你是坏人。")
        elif r == "莫甘娜":
            lines.append("你的特殊能力：在派西维尔眼中你和梅林一样，他无法区分。")
    elif r == "奥伯龙":
        lines.append("你不知道其他坏人是谁，他们也不知道你。梅林能看见你。")
    return "\n".join(lines)

def public_ctx():
    ms = G["mission_sizes"]
    mi = G["mission_idx"]
    good_wins = G["good_wins"]
    evil_wins = G["evil_wins"]

    history = []
    for r in G["mission_results"]:
        s = "✅成功" if r["success"] else f"❌失败({r['fail_count']}张失败牌)"
        history.append(f"第{r['mission']}轮{s}，出任:{','.join(r['team'])}")

    # 明确说明已完成几轮、还差几轮
    good_need = 3 - good_wins
    evil_need = 3 - evil_wins
    if good_wins >= 3:
        score_line = (f"【比分】好人已赢{good_wins}轮，任务阶段结束！"
                      f"现在进入刺杀阶段，坏人尝试刺杀梅林。")
    elif evil_wins >= 3:
        score_line = (f"【比分】坏人已赢{evil_wins}轮，坏人获胜！")
    else:
        score_line = (f"【比分】好人已赢{good_wins}轮（还需{good_need}轮获胜），"
                      f"坏人已赢{evil_wins}轮（还需{evil_need}轮获胜）。"
                      f"游戏进行中，任何一方都尚未获胜。")

    recent_speeches = [e for e in G["log"] if e["type"] == "speech"]
    speech_lines = [f"  {e['player']}：{e['text']}" for e in recent_speeches[-25:]]

    phase = G["phase"]
    if phase == "discussion":
        round_line = (f"当前阶段：任务后讨论（刚完成第{mi}轮任务，"
                      f"第{mi+1}轮即将开始，需{ms[mi]}人出任）")
    elif phase in ("assassination", "game_over"):
        round_line = f"当前阶段：{'刺杀阶段' if phase == 'assassination' else '游戏结束'}"
    else:
        phase_labels = {
            "propose": "提名阶段", "speaking": "发言阶段", "voting": "投票阶段",
            "mission": "执行任务中",
        }
        pname = phase_labels.get(phase, phase)
        round_line = f"当前阶段：{pname}，第{mi+1}轮任务（共5轮），本轮需{ms[mi]}人出任"

    lines = [
        f"玩家（座位顺序）：{'、'.join(G['players'])}",
        f"当前队长：{cur_leader()}",
        score_line,
        round_line,
        f"连续否决：{G['consecutive_rejections']}次（达到4次后第5位队长强制执行）",
    ]
    if G["proposed_team"]:
        lines.append(f"本轮提名队伍：{'、'.join(G['proposed_team'])}")
    if history:
        lines.append("已完成任务：" + "；".join(history))
    if speech_lines:
        lines.append("近期发言：\n" + "\n".join(speech_lines))
    return "\n".join(lines)

def load_agent_context():
    """读取 agent_context.md，热更新——每次调用都重新读，改文件即时生效。"""
    ctx_path = os.path.join(os.path.dirname(__file__), "agent_context.md")
    try:
        with open(ctx_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

def call_agent(player, task):
    personality_block = ""
    p_info = G.get("personalities", {}).get(player)
    if p_info:
        personality_block = f"\n\n【你的性格】\n{p_info['prompt']}"

    system = f"""你正在参与阿瓦隆桌游，扮演玩家「{player}」。

【你的私密信息】
{agent_private_ctx(player)}{personality_block}

【公开游戏状态】
{public_ctx()}

【游戏规则与行为准则】
{load_agent_context()}"""
    if BACKEND == "api":
        resp = get_api_client().messages.create(
            model=API_MODEL,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": task}],
        )
        return resp.content[0].text.strip()
    else:
        resp = http_requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": task},
            ],
            "stream": False,
        }, timeout=120)
        text = resp.json()["message"]["content"].strip()
        # 去掉 Qwen3 的 <think>...</think> 思考块
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        return text

# ── AI动作 ────────────────────────────────────────────────────────

def ai_propose(player):
    n_need = G["mission_sizes"][G["mission_idx"]]
    all_p = "、".join(G["players"])
    task = (f"你是本轮队长，从以下玩家中提名{n_need}人执行任务：{all_p}\n"
            f"请给出提名名单和公开理由。\n"
            f"严格按格式回复：\n提名：玩家A、玩家B（用顿号分隔，共{n_need}人）\n理由：xxx")
    resp = call_agent(player, task)
    team, reason = [], "综合判断后提名这几位。"
    for line in resp.splitlines():
        if line.startswith("提名："):
            names = [x.strip() for x in line[3:].split("、")]
            team = [x for x in names if x in G["players"]]
        elif line.startswith("理由："):
            reason = line[3:].strip()
    if len(team) != n_need:
        team = G["players"][:n_need]
    return team, reason

def ai_speak(player, is_summary=False):
    team_str = "、".join(G["proposed_team"])
    if is_summary:
        n_need = G["mission_sizes"][G["mission_idx"]]
        all_p = "、".join(G["players"])
        task = (f"你是本轮队长，原提名队伍：{team_str}。\n"
                f"你已听完所有人的意见，现在请做总结发言（2-3句），可回应质疑。\n"
                f"你可以保持原队伍，或更换部分成员（共需{n_need}人，可从{all_p}中选）。\n"
                f"若要更换队伍，在发言末尾另起一行写：新提名：玩家A、玩家B\n"
                f"若维持原队伍，无需此行。\n"
                f"只输出发言内容（含可选的新提名行），不要加其他前缀或标签。")
    else:
        task = (f"本轮提名队伍：{team_str}。\n"
                f"请给出你对这次提名的看法（1-2句），可以支持、质疑或表达观察。\n"
                f"根据你的角色利益决定立场，注意不要暴露你的真实身份。\n"
                f"只输出发言内容，不要加前缀或标签。")
    return call_agent(player, task)

def ai_vote(player):
    task = (f"本轮提名队伍：{'、'.join(G['proposed_team'])}。\n"
            f"所有人已发言完毕，现在投票。\n"
            f"严格按格式回复：投票：同意 或 投票：反对")
    resp = call_agent(player, task)
    return "反对" not in resp

def ai_play_card(player):
    if G["sides"][player] == "好人":
        return True
    task = (f"你在任务队伍中，现在秘密打出任务牌。\n"
            f"当前局势：好人{G['good_wins']}胜，坏人{G['evil_wins']}胜，第{G['mission_idx']+1}轮。\n"
            f"严格按格式回复：出牌：成功 或 出牌：失败")
    resp = call_agent(player, task)
    return "失败" not in resp

def ai_discuss(player):
    last = G["mission_results"][-1] if G["mission_results"] else {}
    result_str = "成功" if last.get("success") else f"失败（{last.get('fail_count',0)}张失败牌）"
    task = (f"刚才的任务结果：{result_str}，出任队伍：{'、'.join(last.get('team',[]))}。\n"
            f"请发表你的看法（1-2句），分析局势或表达观点。\n"
            f"只输出发言内容，不要加前缀或标签。")
    return call_agent(player, task)

def ai_assassin_discuss(player):
    good = [p for p, s in G["sides"].items() if s == "好人"]
    good_str = "、".join(good)
    task = (f"好人完成了3轮任务，现在是刺杀阶段的讨论环节。\n"
            f"你是坏人方，正在和队友讨论刺杀目标。\n"
            f"好人玩家有：{good_str}（梅林藏在其中）\n"
            f"回顾整场游戏的发言和投票模式，分析谁最可能是梅林（1-2句）。\n"
            f"只输出发言内容，不要加前缀或标签。")
    return call_agent(player, task)

def ai_assassinate():
    good = [p for p, s in G["sides"].items() if s == "好人"]
    assassin = G["assassin"]
    good_str = "、".join(good)
    task = (f"刺杀讨论结束。你是刺客，现在做最终决定。\n"
            f"好人玩家有：{good_str}（梅林藏在其中）\n"
            f"综合队友的分析和你自己的判断，选择刺杀目标。\n"
            f"严格按格式回复：\n刺杀：玩家名\n理由：xxx")
    resp = call_agent(assassin, task)
    target = None
    for line in resp.splitlines():
        if line.startswith("刺杀："):
            name = line[3:].strip()
            if name in good:
                target = name
    if not target:
        target = random.choice(good)
    return assassin, target

# ── 游戏流程 ──────────────────────────────────────────────────────

def reveal_votes():
    yes = sum(1 for v in G["all_votes"].values() if v)
    no = len(G["all_votes"]) - yes
    approved = yes > no
    lines = []
    for p in G["players"]:
        v = G["all_votes"].get(p)
        if v is not None:
            lines.append(f"{p}:{'✅同意' if v else '❌反对'}")
    log("主持人", f"投票揭示 → {'、'.join(lines)}", "vote")
    log("主持人", f"结果：{yes}票同意，{no}票反对 → {'✅提名通过' if approved else '❌提名被否决'}", "result")
    return approved

def start_next_propose():
    G["phase"] = "propose"
    G["proposed_team"] = []
    G["ai_votes"] = {}
    G["all_votes"] = {}
    mi = G["mission_idx"]
    log("主持人", f"第{mi+1}轮任务，需{G['mission_sizes'][mi]}人出任。队长：{cur_leader()}", "system")

def resolve_mission():
    cards = list(G["mission_cards"].values())
    fail_count = cards.count(False)
    mi = G["mission_idx"]
    success = fail_count == 0 or (G["double_fail_idx"] == mi and fail_count < 2)
    G["mission_results"].append({
        "mission": mi + 1, "team": G["proposed_team"][:],
        "success": success, "fail_count": fail_count,
    })
    if success:
        G["good_wins"] += 1
        log("主持人", f"第{mi+1}轮任务✅成功！（失败牌：{fail_count}张）", "result")
    else:
        G["evil_wins"] += 1
        log("主持人", f"第{mi+1}轮任务❌失败！（失败牌：{fail_count}张）", "result")

    if G["good_wins"] >= 3:
        evil = [p for p, s in G["sides"].items() if s == "坏人"]
        G["assassin"] = evil[0]
        G["assassin_order"] = evil
        G["assassin_idx"] = 0
        log("主持人", f"好人完成3轮任务！进入刺杀阶段，坏人方开始讨论（刺客：{evil[0]}）……", "system")
        G["phase"] = "assassination"
        return
    if G["evil_wins"] >= 3:
        log("主持人", "坏人搞砸3轮任务！坏人获胜！", "result")
        end_game("evil")
        return

    G["mission_idx"] += 1
    G["leader_idx"] = (G["leader_idx"] + 1) % len(G["players"])
    new_leader = cur_leader()
    # Discussion phase: all players once, starting from new leader
    li = G["players"].index(new_leader)
    G["discuss_order"] = G["players"][li:] + G["players"][:li]
    G["discuss_idx"] = 0
    G["phase"] = "discussion"
    log("主持人", f"任务结束，进入讨论。第{G['mission_idx']+1}轮新队长：{new_leader}", "system")

def end_game(winner):
    G["winner"] = winner
    G["phase"] = "game_over"
    reveal = "【角色揭晓】" + "；".join(f"{p}={r}" for p, r in G["roles"].items())
    log("主持人", reveal, "result")
    save_game_log(winner)

def save_game_log(winner):
    """保存完整对局记录到 game_logs/ 目录，用于复盘和迭代学习。"""
    os.makedirs("game_logs", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    record = {
        "timestamp": ts,
        "winner": winner,
        "players": G["players"],
        "user": G["user"],
        "roles": G["roles"],
        "sides": G["sides"],
        "n_players": G["n"],
        "mission_results": G["mission_results"],
        "good_wins": G["good_wins"],
        "evil_wins": G["evil_wins"],
        "personalities": {p: info["name"] for p, info in G.get("personalities", {}).items()},
        "log": G["log"],
    }
    path = os.path.join("game_logs", f"game_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"[对局记录已保存] {path}")

def process_turn():
    """后台单线程循环：处理所有AI行动，直到需要用户输入为止。
    用循环代替递归spawn，彻底消除race condition。"""
    if G.get("processing"):
        return
    G["processing"] = True
    try:
        _drive_loop()
    except Exception as e:
        print(f"[游戏错误] {e}")
        import traceback; traceback.print_exc()
    finally:
        G["processing"] = False

def _drive_loop():
    user = G["user"]
    while True:
        if G.get("waiting_user") or G["phase"] == "game_over":
            return

        phase = G["phase"]

        if phase == "propose":
            leader = cur_leader()
            if leader == user:
                G["waiting_user"] = True
                G["user_action"] = "propose"
                return
            time.sleep(0.8)
            team, reason = ai_propose(leader)
            G["proposed_team"] = team
            log(leader, f"我提名：{'、'.join(team)}。{reason}")
            after_propose(team)

        elif phase == "speaking":
            order = G["speak_order"]
            idx = G["speak_idx"]
            if idx >= len(order):
                G["phase"] = "voting"
                G["ai_votes"] = {}
                continue
            speaker = order[idx]
            is_summary = (idx == len(order) - 1)
            if speaker == user:
                G["waiting_user"] = True
                G["user_action"] = "speak_summary" if is_summary else "speak"
                return
            time.sleep(0.7)
            speech = ai_speak(speaker, is_summary)
            if is_summary:
                # 解析是否有新提名
                n_need = G["mission_sizes"][G["mission_idx"]]
                new_team = None
                speech_lines_raw = []
                for line in speech.splitlines():
                    if line.startswith("新提名："):
                        names = [x.strip() for x in line[4:].split("、")]
                        valid = [x for x in names if x in G["players"]]
                        if len(valid) == n_need:
                            new_team = valid
                    else:
                        speech_lines_raw.append(line)
                pure = "\n".join(speech_lines_raw).strip()
                if new_team:
                    G["proposed_team"] = new_team
                    log(speaker, f"{pure}（调整队伍为：{'、'.join(new_team)}）")
                else:
                    log(speaker, pure)
            else:
                log(speaker, speech)
            G["speak_idx"] += 1

        elif phase == "voting":
            pending_ai = [p for p in G["players"] if p != user and p not in G["ai_votes"]]
            if pending_ai:
                time.sleep(0.3)
                G["ai_votes"][pending_ai[0]] = ai_vote(pending_ai[0])
            else:
                G["waiting_user"] = True
                G["user_action"] = "vote"
                return

        elif phase == "mission":
            queue = G["mission_queue"]
            qi = G["mission_q_idx"]
            if qi >= len(queue):
                resolve_mission()
                continue
            player = queue[qi]
            if player == user:
                G["waiting_user"] = True
                G["user_action"] = "card"
                return
            time.sleep(0.5)
            card = ai_play_card(player)
            G["mission_cards"][player] = card
            log(player, "🃏 已打出任务牌", "system")
            G["mission_q_idx"] += 1

        elif phase == "discussion":
            order = G["discuss_order"]
            di = G["discuss_idx"]
            if di >= len(order):
                start_next_propose()
                continue
            speaker = order[di]
            if speaker == user:
                G["waiting_user"] = True
                G["user_action"] = "discuss"
                return
            time.sleep(0.7)
            speech = ai_discuss(speaker)
            log(speaker, speech)
            G["discuss_idx"] += 1

        elif phase == "assassination":
            # 阶段1：坏人讨论
            order = G["assassin_order"]
            idx = G["assassin_idx"]
            if idx < len(order):
                speaker = order[idx]
                if speaker == user:
                    G["waiting_user"] = True
                    G["user_action"] = "assassin_discuss"
                    return
                time.sleep(0.7)
                speech = ai_assassin_discuss(speaker)
                log(speaker, speech)
                G["assassin_idx"] += 1
                continue

            # 阶段2：刺客做最终决定
            assassin = G["assassin"]
            if assassin == user:
                G["waiting_user"] = True
                G["user_action"] = "assassinate"
                return
            time.sleep(1.0)
            _, target = ai_assassinate()
            merlin = next(p for p, r in G["roles"].items() if r == "梅林")
            log("主持人", f"{assassin}决定刺杀：{target}", "system")
            if target == merlin:
                log("主持人", f"💀 {target} 正是梅林！坏人获胜！", "result")
                end_game("evil")
            else:
                log("主持人", f"✨ {target} 不是梅林！好人获胜！", "result")
                end_game("good")
            return

        else:
            return  # 未知阶段，退出

def _spawn():
    t = threading.Thread(target=process_turn, daemon=True)
    t.start()

# ── Flask 路由 ────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/start", methods=["POST"])
def start():
    data = request.json
    players = data.get("players", [])
    user = data.get("user", "")
    if not (5 <= len(players) <= 10):
        return jsonify({"error": "玩家数量需在5~10之间"}), 400
    if user not in players:
        return jsonify({"error": "用户名必须在玩家列表中"}), 400
    force_role = data.get("force_role") or None
    init_game(players, user, force_role)
    _spawn()
    return jsonify({"ok": True})

@app.route("/api/state")
def state():
    if not G:
        return jsonify({"phase": "setup"})
    user = G["user"]
    pk = G["pk"].get(user, {})
    out = {
        "phase": G["phase"],
        "players": G["players"],
        "user": user,
        "user_role": pk.get("role", ""),
        "user_side": pk.get("side", ""),
        "user_sees": {
            "sees_evil": pk.get("sees_evil"),
            "sees_merlin_morgana": pk.get("sees_merlin_morgana"),
            "evil_teammates": pk.get("evil_teammates"),
        },
        "mission_idx": G["mission_idx"],
        "good_wins": G["good_wins"],
        "evil_wins": G["evil_wins"],
        "mission_sizes": G["mission_sizes"],
        "mission_results": G["mission_results"],
        "leader": cur_leader(),
        "consecutive_rejections": G["consecutive_rejections"],
        "proposed_team": G["proposed_team"],
        "speak_order": G["speak_order"],
        "speak_idx": G["speak_idx"],
        "discuss_order": G["discuss_order"],
        "discuss_idx": G["discuss_idx"],
        "processing": G["processing"],
        "waiting_user": G["waiting_user"],
        "user_action": G["user_action"],
        "winner": G["winner"],
        "log": G["log"],
    }
    if G["phase"] == "game_over":
        out["roles"] = G["roles"]
    if G["phase"] == "voting":
        out["ai_votes_count"] = len(G["ai_votes"])
        out["total_ai"] = len(G["players"]) - 1
    return jsonify(out)

@app.route("/api/action", methods=["POST"])
def action():
    if not G or not G.get("waiting_user"):
        return jsonify({"error": "不是你的回合"}), 400
    data = request.json
    act = data.get("action")
    user = G["user"]

    if act == "propose":
        team = data.get("team", [])
        n_need = G["mission_sizes"][G["mission_idx"]]
        if len(team) != n_need:
            return jsonify({"error": f"需要提名{n_need}人"}), 400
        if not all(p in G["players"] for p in team):
            return jsonify({"error": "包含无效玩家名"}), 400
        G["proposed_team"] = team
        reason = data.get("reason", "这是我的提名。").strip() or "这是我的提名。"
        log(user, f"我提名：{'、'.join(team)}。{reason}")
        after_propose(team)

    elif act in ("speak", "speak_summary"):
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "发言不能为空"}), 400
        if act == "speak_summary":
            new_team = data.get("team")
            n_need = G["mission_sizes"][G["mission_idx"]]
            if (new_team and isinstance(new_team, list)
                    and len(new_team) == n_need
                    and all(p in G["players"] for p in new_team)):
                if new_team != G["proposed_team"]:
                    G["proposed_team"] = new_team
                    log(user, f"{text}（调整队伍为：{'、'.join(new_team)}）")
                else:
                    log(user, text)
            else:
                log(user, text)
        else:
            log(user, text)
        G["speak_idx"] += 1

    elif act == "vote":
        vote = bool(data.get("vote"))
        G["ai_votes"][user] = vote
        # Merge and reveal
        G["all_votes"] = dict(G["ai_votes"])
        approved = reveal_votes()
        G["consecutive_rejections"] = 0 if approved else G["consecutive_rejections"] + 1
        if approved:
            G["mission_cards"] = {}
            G["mission_queue"] = G["proposed_team"][:]
            G["mission_q_idx"] = 0
            G["phase"] = "mission"
            log("主持人", f"队伍出发执行任务：{'、'.join(G['proposed_team'])}", "system")
        else:
            if G["consecutive_rejections"] >= 4:
                log("主持人", "⚠️ 连续4次否决！第5位队长将强制执行。", "system")
            G["leader_idx"] = (G["leader_idx"] + 1) % len(G["players"])
            start_next_propose()

    elif act == "card":
        card = bool(data.get("card"))
        if G["sides"][user] == "好人" and not card:
            return jsonify({"error": "好人只能出成功牌"}), 400
        G["mission_cards"][user] = card
        log(user, "🃏 已打出任务牌", "system")
        G["mission_q_idx"] += 1

    elif act == "discuss":
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "发言不能为空"}), 400
        log(user, text)
        G["discuss_idx"] += 1

    elif act == "assassin_discuss":
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "发言不能为空"}), 400
        log(user, text)
        G["assassin_idx"] += 1

    elif act == "assassinate":
        target = data.get("target")
        good = [p for p, s in G["sides"].items() if s == "好人"]
        if target not in good:
            return jsonify({"error": "请选择一位好人玩家"}), 400
        merlin = next(p for p, r in G["roles"].items() if r == "梅林")
        log("主持人", f"坏人方刺杀：{target}", "system")
        if target == merlin:
            log("主持人", f"💀 {target} 正是梅林！坏人获胜！", "result")
            end_game("evil")
        else:
            log("主持人", f"✨ {target} 不是梅林！好人获胜！", "result")
            end_game("good")
    else:
        return jsonify({"error": "未知动作"}), 400

    G["waiting_user"] = False
    G["user_action"] = None
    _spawn()
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("阿瓦隆游戏服务器启动 → http://localhost:8888")
    app.run(debug=False, port=8888, threaded=True)
