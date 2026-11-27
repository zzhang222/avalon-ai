# Avalon AI

多 AI Agent 阿瓦隆（The Resistance: Avalon）桌游模拟。你作为玩家加入，其余座位由 AI 填充，每个 AI 拥有随机分配的独特人格。默认使用 Claude API（**claude-opus-5-5**），也支持本地 Ollama。

> **关于 AI 质量（2026/03）：** 本地大模型目前玩阿瓦隆的逻辑推理能力一般，适合体验和娱乐。如果想要 AI 真正有策略地博弈（隐藏身份、逻辑推理、欺骗伪装），需要连接 Claude API（默认 claude-opus-5-5），缺点是 API 费用较高。随着开源模型持续迭代，本地模型的效果会越来越好。

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 选择 LLM 后端

默认使用 Claude API（Opus 5.5）。后端通过环境变量切换，无需改代码：

```bash
python server.py                          # Claude API（默认）
AVALON_BACKEND=ollama python server.py    # 本地 Ollama
```

---

#### 方案 A：Claude API（默认，推荐）

设置 API Key 环境变量：

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

API Key 在 [Anthropic Console](https://console.anthropic.com/) 获取。

---

#### 方案 B：本地 Ollama（免费）

[Ollama](https://ollama.com) 让你在自己电脑上运行大模型，无需联网或 API Key。

**安装 Ollama：**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows — 从 https://ollama.com/download 下载安装包
```

**拉取模型并启动：**

```bash
ollama serve              # 启动服务（如已运行可跳过）
ollama pull qwen3.5:35b   # 拉取模型（约 20GB）
```

> 显存/内存不够？换小模型：
> ```bash
> ollama pull qwen3:8b
> ```
> 然后启动时指定：`AVALON_BACKEND=ollama OLLAMA_MODEL=qwen3:8b python server.py`

---

### 3. 启动游戏

```bash
python server.py
```

浏览器打开 http://localhost:8888 即可游戏。

## 游戏说明

- 支持 5~10 人局，你占一个席位，其余为 AI
- 完整阿瓦隆规则：梅林、派西维尔、莫德雷德、莫甘娜、奥伯龙等角色
- 每局 AI 随机分配不同人格（分析型、领袖型、怀疑型等），发言风格各异
- 对局记录自动保存在 `game_logs/` 目录

## 项目结构

```
server.py              # 启动入口
avalon/
  config.py            # 配置（全部可用环境变量覆盖）
  constants.py         # 角色配置、任务人数、AI 人格
  game.py              # 纯规则层：状态与状态转移（不依赖 LLM，可单测）
  prompts.py           # 构造 AI 提示词（规则块可缓存；绝不泄露他人身份）
  parsing.py           # 宽容地解析模型回复
  agents.py            # AI 动作：提示词 → 回复 → 合法动作（解析失败有兜底）
  llm.py               # Claude / Ollama 后端
  engine.py            # 后台单线程推进 AI 回合
  app.py               # Flask 路由
static/index.html      # 前端页面
agent_context.md       # AI 的游戏规则提示词（热更新，改了即时生效）
tests/                 # pytest 测试，含用假模型跑完整对局
```

## 配置

| 环境变量 | 说明 | 默认值 |
|------|------|--------|
| `AVALON_BACKEND` | LLM 后端：`api` 或 `ollama` | `api` |
| `AVALON_MODEL` | Claude 模型名 | `claude-opus-5-5` |
| `AVALON_EFFORT` | 思考深度：`low` / `medium` / `high` / `xhigh` / `max` | `medium` |
| `AVALON_MAX_TOKENS` | 单次回复上限（含思考） | `16000` |
| `OLLAMA_URL` | Ollama API 地址 | `http://localhost:11434/api/chat` |
| `OLLAMA_MODEL` | Ollama 模型名 | `qwen3.5:35b` |
| `AVALON_HISTORY_LIMIT` | 提示词中保留的历史条数，`0` 为全部（小模型可调小） | `0` |
| `AVALON_AI_DELAY` | AI 每次行动前的停顿（秒） | `0.5` |
| `AVALON_PORT` | 服务端口 | `8888` |

## 测试

```bash
pip install -r requirements.txt
python -m pytest -q
```
