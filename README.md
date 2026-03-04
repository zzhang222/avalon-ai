# Avalon AI

多 AI Agent 阿瓦隆（The Resistance: Avalon）桌游模拟。你作为玩家加入，其余座位由 AI 填充，每个 AI 拥有随机分配的独特人格。支持两种 LLM 后端：本地 Ollama 或 Claude API。

> **关于 AI 质量（2026/03）：** 本地大模型目前玩阿瓦隆的逻辑推理能力一般，适合体验和娱乐。如果想要 AI 真正有策略地博弈（隐藏身份、逻辑推理、欺骗伪装），需要连接 Claude API（claude-opus-4-6），缺点是 API 费用较高。随着开源模型持续迭代，本地模型的效果会越来越好。

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 选择 LLM 后端

打开 `server.py` 顶部，切换 `BACKEND` 变量：

```python
BACKEND = "ollama"   # 本地模型（默认，免费）
# BACKEND = "api"    # Claude API（效果好，需付费）
```

---

#### 方案 A：本地 Ollama（免费）

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
> 然后修改 `server.py` 中 `OLLAMA_MODEL = "qwen3:8b"`

---

#### 方案 B：Claude API（推荐体验）

设置 API Key 环境变量：

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

然后将 `server.py` 中 `BACKEND` 改为 `"api"` 即可。

API Key 在 [Anthropic Console](https://console.anthropic.com/) 获取。

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
server.py          # 游戏服务器 + AI Agent 逻辑
static/index.html  # 前端页面
agent_context.md   # AI Agent 的游戏规则提示词
requirements.txt   # Python 依赖
```

## 配置

`server.py` 顶部可修改：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BACKEND` | LLM 后端 | `"ollama"` |
| `OLLAMA_URL` | Ollama API 地址 | `http://localhost:11434/api/chat` |
| `OLLAMA_MODEL` | Ollama 模型名 | `qwen3.5:35b` |
| `API_MODEL` | Claude 模型名 | `claude-opus-4-6` |
