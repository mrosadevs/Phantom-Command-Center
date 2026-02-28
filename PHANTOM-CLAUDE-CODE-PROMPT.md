# 🔮 PHANTOM COMMAND CENTER — Claude Code Build Prompt

> **Copy this entire prompt and paste it into Claude Code to begin building your system.**
> Run this from your main projects directory (e.g., `~/projects/phantom/`)

---

## THE PROMPT

```
You are building the "Phantom Command Center" — a secure, autonomous AI agent system for Manuel (GitHub: mrosadevs). This is NOT an accounting-specific tool. It is a personal AI command center that learns about Manuel, adapts to his life, proactively builds tools he needs, does research while he sleeps, learns new skills on command, and manages itself — all through a Discord interface and a local web dashboard.

## CORE PRINCIPLES — READ THESE FIRST

1. **SECURITY FIRST**: We do NOT use OpenClaw, OpenCode, or any third-party autonomous agent framework. The only trusted execution environments are: Claude Code (Anthropic, sandboxed), Claude Desktop + Cowork (Anthropic, VM-sandboxed), LM Studio (local, no network), Groq API (stateless calls), and code that Manuel writes/reviews himself.

2. **SUBSCRIPTION-SMART**: Manuel has Claude Max ($100/mo), ChatGPT Pro, Gemini Pro, and Groq free tier. Claude Code rides the Max subscription. LM Studio is free local inference. The system must route tasks intelligently to preserve Claude Max weekly quota — 70-80% of tasks should hit LM Studio (free), only complex reasoning/coding goes to Claude Code.

3. **PERSONALITY**: This is Manuel's personal agent. It learns about HIM — his projects, interests, habits, software he's built, repos he maintains. It does NOT start as an accounting bot. It starts blank and learns. If it later discovers he needs accounting help, it offers that proactively.

4. **PROACTIVE**: The killer feature is that this agent surprises Manuel. Every night it analyzes his projects, identifies needs, builds tools/apps, does research on topics that matter to him, and presents surprises in the morning via Discord. It might add a cool feature to one of his existing GitHub repos. It might build a utility he didn't know he needed. It might research a technology he'd find useful.

## WHAT TO BUILD — COMPLETE PROJECT STRUCTURE

Build the following project at ~/projects/phantom/:

```
phantom/
├── CLAUDE.md                          # Agent's persistent memory about Manuel
├── README.md                          # Project documentation
├── package.json                       # Node.js dependencies
├── docker-compose.yml                 # Optional: containerized services
│
├── config/
│   ├── phantom.config.json            # Master configuration
│   ├── routes.json                    # Model routing rules
│   ├── schedules.json                 # Cron task definitions
│   └── mcp-servers.json               # MCP server registry
│
├── src/
│   ├── core/
│   │   ├── router.py                  # Smart model router (Claude vs LM Studio vs Groq)
│   │   ├── memory.py                  # Memory manager (read/write CLAUDE.md + docs/)
│   │   ├── scheduler.py               # Task scheduler (wraps cron/Cowork)
│   │   └── config.py                  # Configuration loader
│   │
│   ├── agents/
│   │   ├── orchestrator.py            # Main agent brain — decides what to do
│   │   ├── builder.py                 # Proactive app builder (overnight surprises)
│   │   ├── researcher.py              # Overnight research agent
│   │   ├── skill_manager.py           # Downloads and installs skills + MCPs
│   │   └── repo_watcher.py            # Monitors Manuel's GitHub repos for improvement ideas
│   │
│   ├── interfaces/
│   │   ├── discord_bot.py             # Discord bot — Manuel's primary interface
│   │   ├── discord_commands.py        # All Discord command handlers
│   │   └── webhook_sender.py          # Sends rich embeds to Discord channels
│   │
│   ├── dashboard/
│   │   ├── server.py                  # FastAPI backend for web dashboard
│   │   ├── static/                    # Frontend assets
│   │   └── templates/
│   │       └── index.html             # Single-page dashboard app
│   │
│   └── utils/
│       ├── claude_code_sdk.py         # Wrapper for Claude Code subprocess calls
│       ├── lm_studio_client.py        # LM Studio API client (localhost:1234)
│       ├── groq_client.py             # Groq API client
│       └── github_client.py           # GitHub API for repo monitoring
│
├── memory/
│   ├── about-manuel.md                # Who Manuel is, his interests, preferences
│   ├── projects.md                    # His active projects and repos
│   ├── skills-learned.md              # Registry of installed skills
│   ├── mcps-installed.md              # Registry of installed MCP servers
│   ├── research-log.md                # Past research topics and findings
│   └── surprises-log.md              # Log of all apps/tools built proactively
│
├── skills/                            # Downloaded skill files live here
│   └── .gitkeep
│
├── surprises/                         # Proactively built apps stored here
│   └── .gitkeep
│
└── scripts/
    ├── morning_briefing.py            # Cron: generates morning briefing
    ├── nightly_research.py            # Cron: autonomous research
    ├── nightly_build.py               # Cron: proactive app building
    ├── memory_sync.py                 # Cron: memory consolidation
    └── setup.sh                       # One-command setup script
```

## DETAILED IMPLEMENTATION INSTRUCTIONS

### 1. config/phantom.config.json
```json
{
  "name": "Phantom Command Center",
  "owner": "Manuel",
  "github": "mrosadevs",
  "version": "1.0.0",
  "models": {
    "heavy": {
      "provider": "claude-code",
      "model": "sonnet-4.5",
      "use_for": ["complex reasoning", "code generation", "architecture", "multi-step tasks"],
      "cost": "max-subscription"
    },
    "light": {
      "provider": "lm-studio",
      "endpoint": "http://localhost:1234/v1",
      "model": "openai/gpt-oss-20b",
      "use_for": ["simple Q&A", "formatting", "data cleaning", "routing decisions", "drafts"],
      "cost": "free"
    },
    "vision": {
      "provider": "groq",
      "model": "llava-v1.5-7b-4096-preview",
      "use_for": ["image analysis", "screenshot reading"],
      "cost": "free-tier"
    },
    "speech": {
      "provider": "groq",
      "model": "whisper-large-v3",
      "use_for": ["transcription", "voice commands"],
      "cost": "free-tier"
    }
  },
  "discord": {
    "bot_token_env": "PHANTOM_DISCORD_TOKEN",
    "guild_id_env": "PHANTOM_GUILD_ID",
    "channels": {
      "briefing": "morning-briefing",
      "surprises": "overnight-surprises",
      "research": "research-feed",
      "commands": "phantom-commands",
      "alerts": "alerts"
    }
  },
  "schedule": {
    "morning_briefing": "0 6 * * *",
    "memory_sync": "0 22 * * *",
    "nightly_research": "0 23 * * *",
    "nightly_build": "0 2 * * *"
  },
  "dashboard": {
    "host": "0.0.0.0",
    "port": 3000
  },
  "repos_to_watch": [
    "mrosadevs/The-Ultimate-AI-Stack"
  ]
}
```

### 2. src/core/router.py — Smart Model Router

This is the brain that decides which model handles each task. The routing logic should:
- Check task complexity using keyword analysis and length heuristics
- Route simple/short tasks to LM Studio (free)
- Route complex reasoning, coding, multi-file operations to Claude Code (Max sub)
- Route vision tasks to Groq
- Route speech/transcription to Groq
- Track quota usage estimates and warn when running low
- Log every routing decision for the dashboard to display

The router should expose a simple function:
```python
async def route_task(task: str, context: dict = None) -> dict:
    """Returns {provider, model, reason, estimated_tokens}"""
```

### 3. src/agents/skill_manager.py — Skill & MCP Installer

When Manuel says "learn [url]" or "install [mcp name]", this agent:
- For skills: Downloads the SKILL.md and supporting files from the URL, saves to phantom/skills/, registers in memory/skills-learned.md, and tells Claude Code to add it to its skill registry
- For MCPs: Looks up the MCP server package name, adds it to claude_desktop_config.json, stores any API keys securely in .env, tests the connection, and registers in memory/mcps-installed.md
- Reports back to Discord with what was installed and what new capabilities are available

Common MCP servers it should know how to install by name:
- "brave search" → @anthropic/mcp-server-brave-search
- "github" → @modelcontextprotocol/server-github
- "filesystem" → @modelcontextprotocol/server-filesystem
- "sqlite" → @modelcontextprotocol/server-sqlite
- "google calendar" → @anthropic/mcp-server-google-calendar
- "gmail" → @anthropic/mcp-server-gmail
- "discord" → discord-mcp

### 4. src/agents/builder.py — Proactive App Builder (The Surprise Engine)

This is the magic feature. Every night at 2 AM, this agent:
1. Reads Manuel's memory files (about-manuel.md, projects.md)
2. Reads his recent Discord messages and research findings
3. Asks LM Studio: "Based on everything you know about Manuel, what tool, app, or automation would make his life easier that he hasn't asked for? Consider his current projects, recent activities, and workflow pain points. Propose ONE specific, buildable thing."
4. LM Studio proposes something (e.g., "A client intake form generator because he's onboarding new clients")
5. The builder evaluates: Is this useful? Is it buildable in one session? Does it overlap with something that already exists?
6. If approved, it delegates to Claude Code to actually build the app in phantom/surprises/[date]-[name]/
7. When done, it sends a rich Discord embed to #overnight-surprises showing what was built, why, and how to use it
8. Logs it in memory/surprises-log.md

The builder should also occasionally look at Manuel's existing GitHub repos and propose improvements or new features. For example: "I noticed your The-Ultimate-AI-Stack repo doesn't have a search feature on the guide page. Want me to add one?"

### 5. src/agents/researcher.py — Overnight Research Agent

Every night at 11 PM:
1. Reads Manuel's memory and recent conversations
2. Asks LM Studio to identify 2-3 topics worth researching tonight
3. Uses Brave Search MCP (if installed) or web search to find articles
4. Summarizes findings using LM Studio (saves Claude quota)
5. Saves full reports to memory/research/[date]-[topic].md
6. Sends summaries to Discord #research-feed
7. If it finds something urgent (security vulnerability in his stack, breaking API change, etc.), it pings #alerts instead

### 6. src/interfaces/discord_bot.py — The Discord Interface

Manuel's primary way to talk to Phantom. The bot should:
- Listen for messages in #phantom-commands
- Parse natural language (not rigid command syntax)
- Route through the smart router
- Display rich embeds with routing info (which model handled it)
- Support these natural language patterns:
  - "learn [url]" / "learn [skill name]" → skill_manager
  - "install [mcp name]" → skill_manager
  - "status" → system health check
  - "research [topic] tonight" → queue for researcher
  - "build me [description]" → queue for builder (or do immediately)
  - "remember [fact]" → update memory
  - "forget [fact]" → remove from memory
  - "schedule [task] at [time]" → add to scheduler
  - "set [setting] to [value]" → update config
  - "what did you build last night" → show surprises
  - "what did you research" → show research
  - Any other message → general chat routed through router

### 7. src/dashboard/server.py + templates/index.html — Web Dashboard

A FastAPI server at localhost:3000 serving a single-page React-style dashboard. Sections:
- **Overview**: Stats (apps built, research done, memory items, quota remaining), service status
- **Surprises**: Gallery of proactively built apps with descriptions and "Open" buttons
- **Schedule**: All cron tasks with status (completed/scheduled/failed)
- **Research**: Feed of overnight research with summaries
- **Memory**: Browsable/editable memory bank organized by category
- **Chat**: Web-based chat that mirrors the Discord interface
- **Settings**: Edit config, manage skills/MCPs, adjust routing rules

Use the same dark theme from the mockups I showed earlier. The dashboard is informational — Discord remains the primary interface.

### 8. CLAUDE.md — Persistent Memory Seed

Start with this and let it grow:
```markdown
# Phantom Command Center — Memory Bank

## About Manuel
- GitHub: mrosadevs
- Location: Brandon, Florida
- Building web portal for mother's accounting business (Accuracy Consulting Group)
- Handles data processing: bank statements → Excel → QuickBooks → reconciliation
- Mother handles accounting and tax prep
- Has RTX 5080 desktop (16GB VRAM), WSL Ubuntu on Windows
- Subscriptions: Claude Max, ChatGPT Pro, Gemini Pro, Groq free
- Interested in AI tools, autonomous agents, software development
- Bilingual: English and Spanish
- Repos: The-Ultimate-AI-Stack (GitHub Pages site)

## Active Projects
- Accuracy Consulting Group web portal (replacing Karbon)
- The Ultimate AI Stack guide (lmstudio.mrosadev.online)
- Phantom Command Center (this system)

## Preferences
- Dark UI themes
- Wants proactive overnight builds
- Values security — no third-party agents with system access
- Prefers natural language over rigid command syntax
- Likes being surprised with useful tools

## System State
- LM Studio: GPT-OSS 20B loaded
- Claude Code: Sonnet 4.5 via Max subscription
- Groq: Free tier connected
- Discord bot: Active

## Skills Learned
(populated as skills are installed)

## MCPs Installed
(populated as MCPs are installed)
```

### 9. scripts/setup.sh — One-Command Setup

Create a bash script that:
1. Checks prerequisites (Python 3.10+, Node.js 18+, npm, pip)
2. Creates a Python virtual environment
3. Installs Python deps: discord.py, fastapi, uvicorn, httpx, openai, python-crontab, pyyaml, rich
4. Installs Node deps (if any MCP servers need npm)
5. Creates the directory structure
6. Copies config templates
7. Prompts for Discord bot token, Groq API key
8. Stores secrets in .env
9. Sets up cron jobs for the scheduled tasks
10. Starts the Discord bot and dashboard
11. Prints a welcome message with next steps

## IMPORTANT IMPLEMENTATION NOTES

- Use Python 3.10+ with async/await throughout
- Use the `openai` Python library to talk to LM Studio (it's OpenAI-compatible at localhost:1234)
- Use `subprocess` to invoke Claude Code CLI for complex tasks (claude --message "...")
- Use `discord.py` for the Discord bot
- Use `FastAPI` for the dashboard backend
- All secrets go in .env, NEVER in code or config files
- Every file should have clear comments explaining what it does
- The system should gracefully handle services being offline (LM Studio not running, etc.)
- Include error handling and logging throughout
- The dashboard frontend should be a single index.html with embedded CSS/JS (no build step)

## BUILD ORDER

1. First: Create the directory structure and config files
2. Second: Build the core modules (router, memory, config)
3. Third: Build the LM Studio and Groq clients
4. Fourth: Build the Discord bot with basic chat
5. Fifth: Build the skill manager
6. Sixth: Build the overnight agents (researcher, builder)
7. Seventh: Build the dashboard
8. Eighth: Build the setup script
9. Ninth: Write CLAUDE.md and README.md
10. Last: Test everything end-to-end

Start building now. Create all files with full implementations, not stubs. This should be a working system when you're done.
```
