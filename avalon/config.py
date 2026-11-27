"""运行配置。全部可用环境变量覆盖，无需改代码。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# LLM 后端："api"（Claude API，默认）或 "ollama"（本地模型）
BACKEND = os.environ.get("AVALON_BACKEND", "api").lower()

# Claude API 配置
API_MODEL = os.environ.get("AVALON_MODEL", "claude-opus-5-5")
# 思考深度：low / medium / high / xhigh / max。Opus 5.5 默认 medium。
API_EFFORT = os.environ.get("AVALON_EFFORT", "medium")
API_MAX_TOKENS = int(os.environ.get("AVALON_MAX_TOKENS", "16000"))

# Ollama 配置
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:35b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))

# 每次 AI 行动前的停顿（秒），让前端能跟上节奏；测试时设为 0
AI_DELAY = float(os.environ.get("AVALON_AI_DELAY", "0.5"))

PORT = int(os.environ.get("AVALON_PORT", "8888"))

AGENT_CONTEXT_PATH = os.path.join(BASE_DIR, "agent_context.md")
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOG_DIR = os.path.join(BASE_DIR, "game_logs")
