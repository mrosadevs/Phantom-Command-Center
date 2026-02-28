<div align="center">

# 👻 Phantom Command Center

### ⚡ Your Personal AI Agent — Always On, Always Learning ⚡

**A fully autonomous AI system that learns about you, builds tools while you sleep, researches what matters to you, and surfaces everything through Discord and a live dashboard.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Discord.py](https://img.shields.io/badge/Discord.py-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-Dashboard-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Claude](https://img.shields.io/badge/Claude-Max-D97757?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)

---

🤖 **Smart Model Routing** · 🌙 **Overnight Agents** · 🧠 **Persistent Memory** · 📊 **Live Dashboard** · 💬 **Discord Interface**

---

</div>

## 🎬 What is Phantom Command Center?

Phantom Command Center is a **personal AI agent system** that runs 24/7 on your machine. It routes your requests through the smartest model for the job, remembers everything you tell it, researches topics while you sleep, and even builds surprise tools overnight — all controllable through Discord DMs or a local cyberpunk-themed dashboard.

No cloud dependencies for core inference. No subscriptions you don't already have. Just a personal AI that gets smarter every day.

---

## 🚀 Features

### 🧠 Smart Model Router

| Model | Role | Cost |
|-------|------|------|
| 🖥️ **LM Studio** | 70-80% of requests — simple Q&A, drafts, formatting | Free (local) |
| 🔮 **Claude Code** | Complex reasoning, code generation, multi-step tasks | Max subscription |
| ⚡ **Groq** | Vision analysis, audio transcription | Free tier |

> Requests are automatically routed based on complexity scoring and keyword detection — no manual switching needed.

### 🌙 Overnight Agents

| Time | Agent | What It Does |
|------|-------|--------------|
| 🌅 6:00 AM | **Morning Briefing** | Sends a daily summary to Discord |
| 🧹 10:00 PM | **Memory Sync** | Consolidates and organizes memory |
| 🔍 11:00 PM | **Researcher** | Runs queued research with Brave Search |
| 🔨 2:00 AM | **Builder** | Proactively builds surprise tools and apps |

### 💬 Discord Interface

Talk naturally in DMs or `#phantom-commands`:

| What You Say | What Happens |
|---|---|
| `status` | System health check |
| `learn https://...` | Install a skill from URL |
| `install brave search` | Install an MCP server |
| `remember [fact]` | Save fact to memory |
| `forget [keyword]` | Remove from memory |
| `research [topic] tonight` | Queue for tonight's research |
| `build me [description]` | Build something now |
| `what did you build last night` | Show overnight surprises |
| anything else | Natural language chat (auto-routed) |

### 📊 Live Dashboard

- 🌐 Runs at `localhost:3000`
- ✨ Animated particles, glitch logo, neon glows
- 🖱️ Ripple click effects
- 🌙 Dark mode (default) + ☀️ Light mode
- 💓 Real-time heartbeat status (updates every 2 min)

### 🧠 Persistent Memory

- 📝 Remembers facts, preferences, and context across sessions
- 🔄 Automatic memory consolidation every night
- 💓 Heartbeat system — writes to disk every 2 min, DMs you every 6 hours
- 📦 Skills system — learn new capabilities from GitHub URLs

---

## 🛠️ Tech Stack

| Technology | Purpose |
|------------|---------|
| 🐍 Python 3.10+ | Core runtime |
| 🤖 discord.py | Discord bot interface |
| ⚡ FastAPI + Uvicorn | Web dashboard server |
| 🕐 APScheduler | Overnight agent scheduling |
| 🖥️ LM Studio | Local LLM inference (free) |
| 🔮 Claude Code SDK | Complex reasoning tasks |
| ⚡ Groq SDK | Vision and speech processing |
| 🔍 Brave Search API | Real web research results |
| 🖼️ CustomTkinter | Desktop launcher app |

---

## 📂 Project Structure

```
phantom-command-center/
├── 📋 CLAUDE.md               # Agent's persistent memory
├── ⚙️ config/                  # Config files (no secrets)
├── 🧠 memory/                  # Markdown memory files + heartbeat
├── 🎯 skills/                  # Downloaded skill files
├── 🎁 surprises/               # Proactively built apps
├── 📜 scripts/                 # Cron & utility scripts
├── 🚀 launcher.py              # Desktop launcher app
└── src/
    ├── 🧠 core/                # Router, memory, scheduler, config
    ├── 🤖 agents/              # Builder, researcher, orchestrator, skill manager
    ├── 💬 interfaces/          # Discord bot + webhook sender
    ├── 📊 dashboard/           # FastAPI server + HTML dashboard
    └── 🔧 utils/               # LM Studio, Groq, Claude, GitHub clients
```

---

## 🔌 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (for Claude Code CLI)
- [Claude Code CLI](https://docs.anthropic.com/claude-code) (`npm install -g @anthropic-ai/claude-code`)
- LM Studio running at `localhost:1234` with a model loaded
- Discord bot token + server ID
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Installation

```bash
# Clone the repo
git clone https://github.com/mrosadevs/Phantom-Command-Center.git
cd Phantom-Command-Center

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your keys
```

### Environment Variables (`.env`)

```env
PHANTOM_DISCORD_TOKEN=your_discord_bot_token
PHANTOM_GUILD_ID=your_server_id
GROQ_API_KEY=your_groq_key
BRAVE_API_KEY=your_brave_key
GITHUB_TOKEN=your_github_token          # optional
```

### Run

```bash
# Terminal 1 — Web Dashboard
python src/dashboard/server.py
# Open http://localhost:3000

# Terminal 2 — Discord Bot
python src/interfaces/discord_bot.py
```

---

## 🔒 Security

- 🚫 No third-party autonomous agent frameworks
- 👁️ All code is readable and auditable
- 🔐 Secrets in `.env` only — never in code
- 🏖️ Claude Code runs in its own sandbox
- 🖥️ LM Studio is fully local — no network for inference

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built for [mrosadevs](https://github.com/mrosadevs) by Phantom 👻**

</div>
