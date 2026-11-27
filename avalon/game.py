"""纯规则层：游戏状态与状态转移。不涉及 LLM、线程或 HTTP，便于单元测试。

所有玩家（人类或 AI）都通过同一组方法行动；`pending()` 告诉调用方现在轮到谁、做什么。
"""
import random
import threading

from .constants import (
    DOUBLE_FAIL_MISSION, EVIL, EVIL_ROLES, GOOD, MAX_REJECTIONS, MERLIN,
    MISSION_SIZES, MORDRED, MORGANA, OBERON, PERCIVAL, PERSONALITIES, ROLE_CONFIGS,
    WINS_NEEDED,
)

# 阶段
SETUP = "setup"
PROPOSE = "propose"
SPEAKING = "speaking"
VOTING = "voting"
MISSION = "mission"
DISCUSSION = "discussion"
ASSASSINATION = "assassination"
GAME_OVER = "game_over"

HOST = "主持人"
GOOD_WIN, EVIL_WIN = "good", "evil"


class GameError(ValueError):
    """非法操作（错误的阶段、错误的玩家、无效的参数）。"""


class Game:
    def __init__(self, players, user, force_role=None, rng=None):
        n = len(players)
        if n not in ROLE_CONFIGS:
            raise GameError("玩家数量需在5~10之间")
        if len(set(players)) != n:
            raise GameError("玩家名字不能重复")
        if any(not p or p == HOST for p in players):
            raise GameError(f"玩家名字不能为空或为「{HOST}」")
        if user not in players:
            raise GameError("用户名必须在玩家列表中")

        self.rng = rng or random.Random()
        self.lock = threading.RLock()
        self.players = list(players)
        self.user = user
        self.n = n
        self.mission_sizes = MISSION_SIZES[n]
        self.double_fail_idx = DOUBLE_FAIL_MISSION if n >= 7 else None

        self.roles = self._deal_roles(force_role)
        self.sides = {p: (GOOD if r not in EVIL_ROLES else EVIL) for p, r in self.roles.items()}
        self.knowledge = self._night_phase()

        ai_players = [p for p in self.players if p != user]
        if len(ai_players) <= len(PERSONALITIES):
            sampled = self.rng.sample(PERSONALITIES, len(ai_players))
        else:
            sampled = self.rng.choices(PERSONALITIES, k=len(ai_players))
        self.personalities = dict(zip(ai_players, sampled))

        self.phase = PROPOSE
        self.mission_idx = 0
        self.good_wins = 0
        self.evil_wins = 0
        self.mission_results = []
        self.leader_idx = self.rng.randrange(n)
        self.consecutive_rejections = 0
        self.proposed_team = []
        self.speak_order, self.speak_idx = [], 0
        self.votes = {}
        self.vote_history = []
        self.mission_queue, self.mission_cards = [], {}
        self.discuss_order, self.discuss_idx = [], 0
        self.assassin = None
        self.assassin_order, self.assassin_idx = [], 0
        self.winner = None
        self.log = []
        self.saved_log = None

        self.host(f"游戏开始！{n}人局，角色已随机分配。")
        self._announce_round()

    # ── 初始化 ────────────────────────────────────────────────
    def _deal_roles(self, force_role):
        cfg = ROLE_CONFIGS[self.n]
        roles = cfg["good"] + cfg["evil"]
        self.rng.shuffle(roles)
        if force_role and force_role in roles:
            # 把指定角色换到用户的座位上
            i, j = self.players.index(self.user), roles.index(force_role)
            roles[i], roles[j] = roles[j], roles[i]
        return dict(zip(self.players, roles))

    def _night_phase(self):
        """闭眼环节：每个人知道什么。"""
        evil = [p for p in self.players if self.sides[p] == EVIL]
        info = {}
        for p in self.players:
            r = self.roles[p]
            k = {"role": r, "side": self.sides[p]}
            if r == MERLIN:
                k["sees_evil"] = [e for e in evil if self.roles[e] != MORDRED]
            elif r == PERCIVAL:
                k["sees_merlin_morgana"] = [q for q in self.players if self.roles[q] in (MERLIN, MORGANA)]
            elif r == OBERON:
                k["evil_teammates"] = []
            elif r in EVIL_ROLES:
                k["evil_teammates"] = [e for e in evil if e != p and self.roles[e] != OBERON]
            info[p] = k
        return info

    # ── 工具 ──────────────────────────────────────────────────
    def add_log(self, player, text, kind="speech"):
        self.log.append({"player": player, "text": text, "type": kind})

    def host(self, text, kind="system"):
        self.add_log(HOST, text, kind)

    @property
    def leader(self):
        return self.players[self.leader_idx]

    @property
    def team_size(self):
        return self.mission_sizes[self.mission_idx]

    @property
    def merlin(self):
        return next(p for p, r in self.roles.items() if r == MERLIN)

    def evil_players(self):
        return [p for p in self.players if self.sides[p] == EVIL]

    def assassin_candidates(self):
        """刺杀阶段坏人公开亮明身份，目标只能是好人方玩家。"""
        return [p for p in self.players if self.sides[p] == GOOD]

    def _seat_order_from(self, player):
        i = self.players.index(player)
        return self.players[i:] + self.players[:i]

    def _validate_team(self, team):
        if not isinstance(team, list) or len(team) != self.team_size:
            raise GameError(f"需要提名{self.team_size}人")
        if len(set(team)) != len(team):
            raise GameError("队伍中有重复玩家")
        if not all(p in self.players for p in team):
            raise GameError("包含无效玩家名")
        # 按座位顺序排列，避免名单顺序透露信息
        return [p for p in self.players if p in team]

    def _announce_round(self):
        self.host(f"第{self.mission_idx + 1}轮任务，需{self.team_size}人出任。队长：{self.leader}")

    def _advance_leader(self):
        self.leader_idx = (self.leader_idx + 1) % self.n

    # ── 当前待办 ──────────────────────────────────────────────
    def pending(self):
        """返回 (玩家, 动作) —— 现在需要谁做什么。游戏结束返回 None。"""
        ph = self.phase
        if ph == PROPOSE:
            return self.leader, "propose"
        if ph == SPEAKING:
            last = self.speak_idx == len(self.speak_order) - 1
            return self.speak_order[self.speak_idx], ("speak_summary" if last else "speak")
        if ph == VOTING:
            # 投票是同时的：未揭晓前谁都看不到别人的票。AI 先投，用户最后，便于前端展示进度。
            for p in self.players:
                if p != self.user and p not in self.votes:
                    return p, "vote"
            return self.user, "vote"
        if ph == MISSION:
            return self.mission_queue[len(self.mission_cards)], "card"
        if ph == DISCUSSION:
            return self.discuss_order[self.discuss_idx], "discuss"
        if ph == ASSASSINATION:
            if self.assassin_idx < len(self.assassin_order):
                return self.assassin_order[self.assassin_idx], "assassin_discuss"
            return self.assassin, "assassinate"
        return None

    def _expect(self, player, *actions):
        pend = self.pending()
        if pend is None or pend[0] != player or pend[1] not in actions:
            raise GameError("不是你的回合")
        return pend[1]

    # ── 动作 ──────────────────────────────────────────────────
    def propose(self, player, team, reason=""):
        self._expect(player, "propose")
        team = self._validate_team(team)
        self.proposed_team = team
        reason = (reason or "").strip() or "这是我的提名。"
        self.add_log(player, f"我提名：{'、'.join(team)}。{reason}")

        if self.consecutive_rejections >= MAX_REJECTIONS:
            self.host(f"⚠️ 第{MAX_REJECTIONS + 1}次提名，队伍自动执行！")
            self._start_mission()
        else:
            others = self._seat_order_from(player)[1:]
            self.speak_order = others + [player]  # 队长的提名即开场，最后再做总结
            self.speak_idx = 0
            self.phase = SPEAKING

    def speak(self, player, text, new_team=None):
        action = self._expect(player, "speak", "speak_summary")
        text = (text or "").strip()
        if not text:
            raise GameError("发言不能为空")
        if action == "speak_summary" and new_team:
            new_team = self._validate_team(new_team)
            if new_team != self.proposed_team:
                self.proposed_team = new_team
                text = f"{text}（调整队伍为：{'、'.join(new_team)}）"
        self.add_log(player, text)
        self.speak_idx += 1
        if self.speak_idx >= len(self.speak_order):
            self.phase = VOTING
            self.votes = {}

    def vote(self, player, approve):
        self._expect(player, "vote")
        self.votes[player] = bool(approve)
        if len(self.votes) == self.n:
            self._resolve_vote()

    def _resolve_vote(self):
        yes = sum(self.votes.values())
        no = self.n - yes
        approved = yes > no
        detail = "、".join(f"{p}:{'✅同意' if self.votes[p] else '❌反对'}" for p in self.players)
        self.add_log(HOST, f"投票揭示 → {detail}", "vote")
        self.add_log(HOST, f"结果：{yes}票同意，{no}票反对 → "
                           f"{'✅提名通过' if approved else '❌提名被否决'}", "result")
        self.vote_history.append({
            "mission": self.mission_idx + 1, "leader": self.leader,
            "team": self.proposed_team[:], "votes": dict(self.votes), "approved": approved,
        })
        if approved:
            self._start_mission()
        else:
            self.consecutive_rejections += 1
            if self.consecutive_rejections >= MAX_REJECTIONS:
                self.host(f"⚠️ 连续{MAX_REJECTIONS}次否决！下一位队长的提名将强制执行。")
            self._advance_leader()
            self._start_propose()

    def _start_propose(self):
        self.phase = PROPOSE
        self.proposed_team = []
        self.votes = {}
        self._announce_round()

    def _start_mission(self):
        self.consecutive_rejections = 0
        self.mission_queue = self.proposed_team[:]
        self.mission_cards = {}
        self.phase = MISSION
        self.host(f"队伍出发执行任务：{'、'.join(self.mission_queue)}")

    def play_card(self, player, success):
        self._expect(player, "card")
        success = bool(success)
        if self.sides[player] == GOOD and not success:
            raise GameError("好人只能出成功牌")
        self.mission_cards[player] = success
        self.add_log(player, "🃏 已打出任务牌", "system")
        if len(self.mission_cards) == len(self.mission_queue):
            self._resolve_mission()

    def _resolve_mission(self):
        fails = list(self.mission_cards.values()).count(False)
        mi = self.mission_idx
        needed = 2 if self.double_fail_idx == mi else 1
        success = fails < needed
        self.mission_results.append({
            "mission": mi + 1, "team": self.mission_queue[:],
            "success": success, "fail_count": fails,
        })
        if success:
            self.good_wins += 1
            self.host(f"第{mi + 1}轮任务✅成功！（失败牌：{fails}张）", "result")
        else:
            self.evil_wins += 1
            self.host(f"第{mi + 1}轮任务❌失败！（失败牌：{fails}张）", "result")

        if self.good_wins >= WINS_NEEDED:
            evil = self.evil_players()
            # 刺客优先由知道队友的坏人担任（奥伯龙不知道队友）
            self.assassin = next((e for e in evil if self.roles[e] != OBERON), evil[0])
            self.assassin_order = [e for e in evil if e != self.assassin] + [self.assassin]
            self.assassin_idx = 0
            self.phase = ASSASSINATION
            self.host(f"好人完成{WINS_NEEDED}轮任务！进入刺杀阶段，坏人亮明身份并讨论"
                      f"（坏人：{'、'.join(evil)}；刺客：{self.assassin}）……")
            return
        if self.evil_wins >= WINS_NEEDED:
            self.host(f"坏人搞砸{WINS_NEEDED}轮任务！坏人获胜！", "result")
            self._end(EVIL_WIN)
            return

        self.mission_idx += 1
        self._advance_leader()
        self.discuss_order = self._seat_order_from(self.leader)
        self.discuss_idx = 0
        self.phase = DISCUSSION
        self.host(f"任务结束，进入讨论。第{self.mission_idx + 1}轮新队长：{self.leader}")

    def discuss(self, player, text):
        self._expect(player, "discuss")
        text = (text or "").strip()
        if not text:
            raise GameError("发言不能为空")
        self.add_log(player, text)
        self.discuss_idx += 1
        if self.discuss_idx >= len(self.discuss_order):
            self._start_propose()

    def assassin_discuss(self, player, text):
        self._expect(player, "assassin_discuss")
        text = (text or "").strip()
        if not text:
            raise GameError("发言不能为空")
        self.add_log(player, text)
        self.assassin_idx += 1

    def assassinate(self, player, target):
        self._expect(player, "assassinate")
        if target not in self.assassin_candidates():
            raise GameError("请选择一位好人方玩家")
        self.host(f"{player}决定刺杀：{target}")
        if target == self.merlin:
            self.host(f"💀 {target} 正是梅林！坏人获胜！", "result")
            self._end(EVIL_WIN)
        else:
            self.host(f"✨ {target} 不是梅林！好人获胜！", "result")
            self._end(GOOD_WIN)

    def _end(self, winner):
        self.winner = winner
        self.phase = GAME_OVER
        self.host("【角色揭晓】" + "；".join(f"{p}={self.roles[p]}" for p in self.players), "result")

    # ── 导出 ──────────────────────────────────────────────────
    def record(self):
        """完整对局记录（含所有身份），仅用于保存复盘。"""
        return {
            "winner": self.winner, "players": self.players, "user": self.user,
            "roles": self.roles, "sides": self.sides, "n_players": self.n,
            "mission_results": self.mission_results, "vote_history": self.vote_history,
            "good_wins": self.good_wins, "evil_wins": self.evil_wins,
            "personalities": {p: info["name"] for p, info in self.personalities.items()},
            "log": self.log,
        }

