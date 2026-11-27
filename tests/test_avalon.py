import random
import time

import pytest

from avalon import agents, prompts
from avalon.app import create_app, user_view
from avalon.constants import EVIL, GOOD, MERLIN, MORDRED, MORGANA, OBERON, PERCIVAL
from avalon.engine import Engine
from avalon.game import ASSASSINATION, GAME_OVER, MISSION, PROPOSE, SPEAKING, VOTING, Game, GameError
from avalon.parsing import clean_speech, find_field, parse_binary, parse_names

NAMES = ["我", "A", "B", "C", "D", "E", "F", "G", "H", "I"]


def make(n=5, seed=0, **kw):
    return Game(NAMES[:n], "我", rng=random.Random(seed), **kw)


def play_round(g, team=None, approve=True):
    """让当前队长提名并完成发言、投票。"""
    leader, _ = g.pending()
    team = team or g.players[:g.team_size]
    g.propose(leader, team)
    while g.phase == SPEAKING:
        p, _ = g.pending()
        g.speak(p, "发言")
    if g.phase == VOTING:
        while g.phase == VOTING:
            p, _ = g.pending()
            g.vote(p, approve)


def run_mission(g, fail=False):
    while g.phase == MISSION:
        p, _ = g.pending()
        g.play_card(p, not (fail and g.sides[p] == EVIL))


# ── 规则 ────────────────────────────────────────────────────

@pytest.mark.parametrize("n", range(5, 11))
def test_night_knowledge(n):
    g = make(n, seed=n)
    for p, k in g.knowledge.items():
        r = k["role"]
        if r == MERLIN:
            assert set(k["sees_evil"]) == {e for e in g.evil_players() if g.roles[e] != MORDRED}
        elif r == PERCIVAL:
            assert {g.roles[q] for q in k["sees_merlin_morgana"]} == {MERLIN, MORGANA}
        elif r == OBERON:
            assert k["evil_teammates"] == []
        elif k["side"] == EVIL:
            assert p not in k["evil_teammates"]
            assert all(g.roles[t] != OBERON for t in k["evil_teammates"])


def test_force_role_and_validation():
    for seed in range(10):
        assert make(seed=seed, force_role=MERLIN).roles["我"] == MERLIN
    with pytest.raises(GameError):
        Game(["我", "A", "A", "B", "C"], "我")
    with pytest.raises(GameError):
        Game(["我", "A", "B", "C"], "我")


def test_wrong_turn_and_wrong_action_rejected():
    g = make()
    leader, action = g.pending()
    other = next(p for p in g.players if p != leader)
    with pytest.raises(GameError):
        g.propose(other, g.players[:2])
    with pytest.raises(GameError):
        g.vote(leader, True)  # 旧版：等待用户时任何动作都被接受，投票阶段可直接发刺杀结束游戏
    with pytest.raises(GameError):
        g.propose(leader, [g.players[0], g.players[0]])  # 重复玩家


def test_tie_vote_rejects_and_leader_rotates():
    g = make(6)
    first = g.leader
    leader, _ = g.pending()
    g.propose(leader, g.players[:2])
    while g.phase == SPEAKING:
        g.speak(g.pending()[0], "x")
    for i in range(6):
        g.vote(g.pending()[0], i % 2 == 0)  # 3:3
    assert g.phase == PROPOSE and g.consecutive_rejections == 1
    assert g.leader != first


def test_fifth_proposal_is_forced():
    g = make()
    for _ in range(4):
        play_round(g, approve=False)
    assert g.consecutive_rejections == 4
    play_round(g)
    assert g.phase == MISSION and g.consecutive_rejections == 0


def test_double_fail_round_four():
    # 7人局第4轮放一个坏人，只出1张失败牌 → 仍然成功
    g2 = make(7, seed=3)
    g2.mission_idx = 3
    evil = g2.evil_players()[0]
    good = [p for p in g2.players if g2.sides[p] == GOOD][:3]
    play_round(g2, team=[evil] + good)
    run_mission(g2, fail=True)
    assert g2.mission_results[-1]["success"] and g2.mission_results[-1]["fail_count"] == 1


def test_good_card_must_succeed():
    g = make()
    good = [p for p in g.players if g.sides[p] == GOOD][:2]
    play_round(g, team=good)
    with pytest.raises(GameError):
        g.play_card(g.pending()[0], False)


def test_assassination_flow():
    g = make(seed=1)
    good = [p for p in g.players if g.sides[p] == GOOD]
    while g.phase != ASSASSINATION:
        play_round(g, team=good[:g.team_size])
        run_mission(g)
        while g.phase == "discussion":
            g.discuss(g.pending()[0], "x")
    assert g.roles[g.assassin] != OBERON
    while g.pending()[1] == "assassin_discuss":
        g.assassin_discuss(g.pending()[0], "x")
    with pytest.raises(GameError):
        g.assassinate(g.assassin, g.evil_players()[0])
    g.assassinate(g.assassin, g.merlin)
    assert g.phase == GAME_OVER and g.winner == "evil"


# ── 提示词不泄露身份 ───────────────────────────────────────

@pytest.mark.parametrize("seed", range(5))
def test_prompts_do_not_leak_roles(seed):
    g = make(10, seed=seed)
    for p in g.players:
        system, user = prompts.build(g, p, "任务")
        text = system[1][0] + user
        k = g.knowledge[p]
        known = set(k.get("sees_evil") or []) | set(k.get("evil_teammates") or []) | set(k.get("sees_merlin_morgana") or [])
        for other in g.players:
            if other in (p, *known):
                continue
            assert f"{other}={g.roles[other]}" not in text
            assert f"{other}（{g.roles[other]}" not in text
    assert "roles" not in user_view(type("E", (), {"game": g, "last_error": None})())


# ── 解析 ────────────────────────────────────────────────────

def test_parsing():
    ps = ["艾丽斯", "鲍勃", "查理", "AI1", "AI10"]
    assert parse_names(find_field("**提名:** 艾丽斯, 鲍勃\n理由：x", "提名"), ps) == ["艾丽斯", "鲍勃"]
    assert parse_names("艾丽斯和查理", ps) == ["艾丽斯", "查理"]
    assert parse_names("AI10、AI1、AI1", ps) == ["AI10", "AI1"]
    assert parse_binary("投票：反对", "投票", "同意", "反对") is False
    assert parse_binary("我想了想\n**投票：** 同意", "投票", "同意", "反对") is True
    # 旧版用 "失败" not in resp 判断，这句会被误判成出失败牌
    assert parse_binary("出牌：成功（这轮不能失败）", "出牌", "成功", "失败") is True
    assert parse_binary("随便", "投票", "同意", "反对") is None
    assert clean_speech("艾丽斯：「我觉得可以」", "艾丽斯") == "我觉得可以"


def test_agent_fallbacks_keep_game_valid():
    g = make()
    leader = g.leader
    agents.apply(g, leader, "propose", "乱七八糟")
    assert len(g.proposed_team) == g.team_size and leader in g.proposed_team


# ── 端到端：假模型跑完整局 ─────────────────────────────────

class FakeBackend:
    """总是给出格式正确的随机回复，偶尔抛异常模拟网络错误。"""

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.calls % 37 == 0:
            raise RuntimeError("模拟网络错误")
        task = user.split("【现在轮到你】")[1]
        names = task.split("：")[1].split("\n")[0].split("（")[0].split("、") if "：" in task else []
        if "提名" in task and "严格按以下格式" in task:
            n = int(task.split("提名")[1].split("人")[0])
            return f"提名：{'、'.join(self.rng.sample(names, n))}\n理由：直觉"
        if "投票：同意" in task:
            return f"投票：{self.rng.choice(['同意', '同意', '反对'])}"
        if "出牌：成功" in task:
            return f"出牌：{self.rng.choice(['成功', '失败'])}"
        if "刺杀：玩家名" in task:
            cands = task.split("候选人（梅林在其中）：")[1].split("\n")[0].split("、")
            return f"刺杀：{self.rng.choice(cands)}\n理由：猜的"
        return "我觉得这个队伍还行。"


def drive_user(client, rng, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get("/api/state").get_json()
        if s["phase"] == GAME_OVER:
            return s
        if not s["waiting_user"]:
            time.sleep(0.005)
            continue
        act, ps = s["user_action"], s["players"]
        n = s["mission_sizes"][s["mission_idx"]]
        body = {"action": act}
        if act == "propose":
            body.update(team=rng.sample(ps, n), reason="")
        elif act in ("speak", "discuss", "assassin_discuss"):
            body["text"] = "嗯"
        elif act == "speak_summary":
            body.update(text="就这样", team=s["proposed_team"])
        elif act == "vote":
            body["vote"] = rng.random() < 0.6
        elif act == "card":
            body["card"] = s["user_side"] == GOOD or rng.random() < 0.5
        elif act == "assassinate":
            body["target"] = rng.choice(s["assassin_candidates"])
        r = client.post("/api/action", json=body)
        assert r.status_code == 200, r.get_json()
    raise AssertionError("游戏卡住了")


@pytest.mark.parametrize("seed", range(12))
def test_full_game_via_http(seed, tmp_path, monkeypatch):
    monkeypatch.setattr("avalon.config.LOG_DIR", str(tmp_path))
    monkeypatch.setattr("avalon.engine.LLM_RETRIES", 0)
    engine = Engine(FakeBackend(seed), ai_delay=0)
    client = create_app(engine).test_client()
    n = 5 + seed % 6
    r = client.post("/api/start", json={"players": NAMES[:n], "user": "我"})
    assert r.status_code == 200
    s = drive_user(client, random.Random(seed))
    assert s["winner"] in ("good", "evil") and set(s["roles"]) == set(NAMES[:n])
    for _ in range(200):
        if list(tmp_path.glob("game_*.json")):
            break
        time.sleep(0.01)
    assert len(list(tmp_path.glob("game_*.json"))) == 1


def test_action_out_of_turn_is_rejected():
    engine = Engine(FakeBackend(), ai_delay=0)
    client = create_app(engine).test_client()
    client.post("/api/start", json={"players": NAMES[:5], "user": "我"})
    for _ in range(500):
        s = client.get("/api/state").get_json()
        if s["waiting_user"]:
            break
        time.sleep(0.005)
    wrong = "assassinate" if s["user_action"] != "assassinate" else "vote"
    r = client.post("/api/action", json={"action": wrong, "target": "A"})
    assert r.status_code == 400


def test_parse_negation():
    assert parse_binary("投票：不同意", "投票", "同意", "反对") is False
