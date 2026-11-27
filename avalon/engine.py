"""驱动层：一个常驻后台线程推进 AI 回合，直到轮到用户或游戏结束。

旧实现每次用户操作都新开线程，并用一个非原子的 processing 标志防重入：
上一个线程刚 return 还没清标志时用户就操作，新线程会直接退出，游戏永久卡住。
这里改成单 worker + Event：任何时候唤醒都不会丢，也不会有两个线程同时推进。
"""
import json
import logging
import os
import threading
import time
from datetime import datetime

from . import agents, config, prompts
from .game import Game, GameError

log = logging.getLogger("avalon.engine")

LLM_RETRIES = 2


class Engine:
    def __init__(self, backend, ai_delay=None):
        self.backend = backend
        self.ai_delay = config.AI_DELAY if ai_delay is None else ai_delay
        self.game = None
        self.busy = False
        self.last_error = None
        self._wake = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="avalon-engine")
        self._worker.start()

    # ── 外部接口 ──────────────────────────────────────────────
    def new_game(self, players, user, force_role=None):
        self.game = Game(players, user, force_role)  # 旧对局的线程只会写旧对象，互不干扰
        self.last_error = None
        self._wake.set()
        return self.game

    def user_action(self, action, data):
        game = self.game
        if game is None:
            raise GameError("游戏尚未开始")
        u = game.user
        with game.lock:
            pend = game.pending()
            if pend is None or pend[0] != u:
                raise GameError("不是你的回合")
            if pend[1] != action:
                raise GameError(f"当前需要的操作是 {pend[1]}，而不是 {action}")
            if action == "propose":
                game.propose(u, data.get("team"), data.get("reason", ""))
            elif action in ("speak", "speak_summary"):
                game.speak(u, data.get("text"), data.get("team") if action == "speak_summary" else None)
            elif action == "vote":
                game.vote(u, bool(data.get("vote")))
            elif action == "card":
                game.play_card(u, bool(data.get("card")))
            elif action == "discuss":
                game.discuss(u, data.get("text"))
            elif action == "assassin_discuss":
                game.assassin_discuss(u, data.get("text"))
            elif action == "assassinate":
                game.assassinate(u, data.get("target"))
        self._wake.set()

    # ── 后台循环 ──────────────────────────────────────────────
    def _run(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            game = self.game
            if game is None:
                continue
            try:
                self.busy = True
                self._drive(game)
            except Exception as e:  # 不让一次异常杀掉 worker
                log.exception("游戏推进出错")
                self.last_error = str(e)
            finally:
                self.busy = False

    def _drive(self, game):
        while game is self.game:
            with game.lock:
                pend = game.pending()
                if pend is None:
                    if game.saved_log is None:
                        game.saved_log = save_game_log(game)
                    return
                player, action = pend
                if player == game.user:
                    return
                use_llm = agents.needs_llm(game, player, action)
                if use_llm:
                    system, user_text = prompts.build(game, player, agents.task_for(game, player, action))

            if self.ai_delay:
                time.sleep(self.ai_delay)
            text = self._ask(game, player, system, user_text) if use_llm else ""

            with game.lock:
                if game is not self.game or game.pending() != pend:
                    return  # 对局已被重置
                agents.apply(game, player, action, text)

    def _ask(self, game, player, system, user_text):
        for attempt in range(LLM_RETRIES + 1):
            try:
                return self.backend.complete(system, user_text)
            except Exception as e:
                log.warning("%s 调用模型失败（第%d次）：%s", player, attempt + 1, e)
                self.last_error = f"{type(e).__name__}: {e}"
                if attempt < LLM_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        with game.lock:
            game.host(f"⚠️ {player} 的模型调用失败，已使用默认动作。（{self.last_error[:120]}）")
        return ""


def save_game_log(game):
    """保存完整对局记录到 game_logs/，用于复盘。"""
    os.makedirs(config.LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(config.LOG_DIR, f"game_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, **game.record()}, f, ensure_ascii=False, indent=2)
    log.info("对局记录已保存：%s", path)
    return path
