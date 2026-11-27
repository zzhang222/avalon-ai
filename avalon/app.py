"""HTTP 层：只做参数转发与视图裁剪，规则都在 game.py。"""
import logging

from flask import Flask, jsonify, request, send_from_directory

from . import config, llm
from .engine import Engine
from .game import ASSASSINATION, GAME_OVER, VOTING, GameError


def user_view(engine):
    """用户能看到的状态。绝不包含其他人的身份（游戏结束前）。"""
    g = engine.game
    if g is None:
        return {"phase": "setup", "backend": llm.describe()}
    with g.lock:
        k = g.knowledge[g.user]
        pend = g.pending()
        waiting = pend is not None and pend[0] == g.user
        out = {
            "phase": g.phase,
            "players": g.players,
            "user": g.user,
            "user_role": k["role"],
            "user_side": k["side"],
            "user_sees": {
                "sees_evil": k.get("sees_evil"),
                "sees_merlin_morgana": k.get("sees_merlin_morgana"),
                "evil_teammates": k.get("evil_teammates"),
            },
            "mission_idx": g.mission_idx,
            "good_wins": g.good_wins,
            "evil_wins": g.evil_wins,
            "mission_sizes": g.mission_sizes,
            "double_fail_idx": g.double_fail_idx,
            "mission_results": g.mission_results,
            "leader": g.leader,
            "consecutive_rejections": g.consecutive_rejections,
            "proposed_team": g.proposed_team,
            "speak_order": g.speak_order,
            "speak_idx": g.speak_idx,
            "processing": not waiting and g.phase != GAME_OVER,
            "waiting_user": waiting,
            "user_action": pend[1] if waiting else None,
            "current_actor": pend[0] if pend else None,
            "winner": g.winner,
            "log": list(g.log),
            "backend": llm.describe(),
            "error": engine.last_error,
        }
        if g.phase == VOTING:
            out["ai_votes_count"] = sum(1 for p in g.votes if p != g.user)
            out["total_ai"] = g.n - 1
        if g.phase == ASSASSINATION:
            out["assassin_candidates"] = g.assassin_candidates()
        if g.phase == GAME_OVER:
            out["roles"] = g.roles
        return out


def create_app(engine=None):
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # 屏蔽每次轮询的访问日志
    app = Flask(__name__, static_folder=config.STATIC_DIR)
    if engine is None:
        engine = Engine(llm.make_backend())
    app.config["ENGINE"] = engine

    @app.route("/")
    def index():
        return send_from_directory(config.STATIC_DIR, "index.html")

    @app.route("/api/start", methods=["POST"])
    def start():
        data = request.get_json(silent=True) or {}
        players = [str(p).strip() for p in data.get("players", [])]
        user = str(data.get("user", "")).strip()
        try:
            engine.new_game(players, user, data.get("force_role") or None)
        except GameError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.route("/api/state")
    def state():
        return jsonify(user_view(engine))

    @app.route("/api/action", methods=["POST"])
    def action():
        data = request.get_json(silent=True) or {}
        try:
            engine.user_action(data.get("action"), data)
        except GameError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    return app
