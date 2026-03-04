# Avalon AI

多 AI Agent 阿瓦隆（The Resistance: Avalon）桌游模拟。你作为玩家加入，其余座位由 AI 填充，每个 AI 拥有随机分配的独特人格，通过本地大模型（Ollama）驱动推理和对话。

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装并启动 Ollama

> 如果你已经装好了 Ollama 并拉取了模型，跳到第 3 步。

[Ollama](https://ollama.com) 是一个本地大模型运行工具，让你无需 API 即可在自己电脑上跑 LLM。

**安装：**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# 从 https://ollama.com/download 下载安装包
```

**启动服务并拉取模型：**

```bash
ollama serve          # 启动 Ollama 服务（后台运行）
ollama pull qwen3:32b # 拉取模型（约 20GB，需耐心等待）
```

> 如果显存/内存不够跑 32B，可以换小模型：
> ```bash
> ollama pull qwen3:8b
> ```
> 然后修改 `server.py` 顶部的 `OLLAMA_MODEL = "qwen3:8b"`

### 3. 启动游戏

```bash
python server.py
```

浏览器打开 http://localhost:8888 即可开始游戏。

## 游戏说明

- 支持 5~10 人局，你占一个席位，其余为 AI
- 包含完整阿瓦隆规则：梅林、派西维尔、莫德雷德、莫甘娜、奥伯龙等角色
- 每局 AI 会被随机分配不同人格（分析型、领袖型、怀疑型等），发言风格各异
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
| `OLLAMA_URL` | Ollama API 地址 | `http://localhost:11434/api/chat` |
| `OLLAMA_MODEL` | 使用的模型 | `qwen3.5:35b` |
