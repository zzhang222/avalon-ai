"""LLM 后端。接口统一：complete(system_blocks, user_text) -> str。"""
import logging

from . import config
from .parsing import strip_think

log = logging.getLogger("avalon.llm")


class ClaudeBackend:
    """Claude API（默认 claude-opus-5-5）。

    - Opus 5.5 的思考始终开启，用 effort 控制深度；思考会占用 max_tokens，所以上限要给足。
    - 规则块打 cache_control，所有玩家共享缓存，大幅降低重复输入的费用。
    - 开启服务端 fallbacks：若安全分类器误拒（例如把"欺骗队友"当成有害），自动换模型重试。
    """

    def __init__(self, model=None, effort=None, max_tokens=None):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model or config.API_MODEL
        self.effort = effort or config.API_EFFORT
        self.max_tokens = max_tokens or config.API_MAX_TOKENS

    def complete(self, system_blocks, user_text):
        system = []
        for text, cacheable in system_blocks:
            block = {"type": "text", "text": text}
            if cacheable:
                block["cache_control"] = {"type": "ephemeral"}
            system.append(block)

        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            log.warning("模型拒绝回答（%s），使用默认动作", getattr(resp.stop_details, "category", None))
            return ""
        if resp.stop_reason == "max_tokens":
            log.warning("回复因 max_tokens 被截断，可调大 AVALON_MAX_TOKENS")
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class OllamaBackend:
    def __init__(self, url=None, model=None):
        import requests
        self.session = requests.Session()
        self.url = url or config.OLLAMA_URL
        self.model = model or config.OLLAMA_MODEL

    def complete(self, system_blocks, user_text):
        system = "\n\n".join(text for text, _ in reversed(system_blocks))
        resp = self.session.post(self.url, json={
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
        }, timeout=config.OLLAMA_TIMEOUT)
        resp.raise_for_status()
        return strip_think(resp.json()["message"]["content"])


def make_backend(name=None):
    name = (name or config.BACKEND).lower()
    if name == "api":
        return ClaudeBackend()
    if name == "ollama":
        return OllamaBackend()
    raise ValueError(f"未知后端：{name}（可选 api / ollama）")


def describe():
    if config.BACKEND == "ollama":
        return f"Ollama · {config.OLLAMA_MODEL}"
    return f"Claude API · {config.API_MODEL} (effort={config.API_EFFORT})"
