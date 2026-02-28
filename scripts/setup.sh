#!/bin/bash
# setup.sh — One-command setup for Phantom Command Center
# Run from the phantom project root: bash scripts/setup.sh

set -e

CYAN='\033[0;36m'
PURPLE='\033[0;35m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${PURPLE}╔══════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║    🔮 PHANTOM COMMAND CENTER SETUP 🔮    ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════╝${NC}"
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo -e "${CYAN}Project root:${NC} $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# ── Step 1: Check prerequisites ──
echo ""
echo -e "${CYAN}[1/8] Checking prerequisites...${NC}"

check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} $1 found: $(command -v $1)"
    else
        echo -e "  ${RED}✗${NC} $1 not found — please install it first"
        MISSING=1
    fi
}

MISSING=0
check_command python3
check_command pip3
check_command node
check_command npm

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  Python version: $PYTHON_VERSION"
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo -e "  ${GREEN}✓${NC} Python 3.10+ confirmed"
else
    echo -e "  ${RED}✗${NC} Python 3.10+ required"
    MISSING=1
fi

if [ "$MISSING" -eq "1" ]; then
    echo -e "\n${RED}Fix missing prerequisites and re-run setup.${NC}"
    exit 1
fi

# ── Step 2: Create virtual environment ──
echo ""
echo -e "${CYAN}[2/8] Creating Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "  ${GREEN}✓${NC} Virtual environment created at .venv/"
else
    echo -e "  ${YELLOW}→${NC} Virtual environment already exists"
fi

source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

# ── Step 3: Install Python dependencies ──
echo ""
echo -e "${CYAN}[3/8] Installing Python dependencies...${NC}"
pip install --upgrade pip -q

pip install \
    discord.py \
    fastapi \
    uvicorn[standard] \
    httpx \
    openai \
    groq \
    APScheduler \
    python-dotenv \
    pyyaml \
    rich \
    -q

echo -e "  ${GREEN}✓${NC} Python dependencies installed"

# ── Step 4: Install Claude Code CLI ──
echo ""
echo -e "${CYAN}[4/8] Checking Claude Code CLI...${NC}"
if command -v claude &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Claude Code CLI found"
else
    echo -e "  ${YELLOW}→${NC} Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
fi

# ── Step 5: Ensure directory structure ──
echo ""
echo -e "${CYAN}[5/8] Creating directory structure...${NC}"
mkdir -p memory/research skills surprises config src/core src/agents src/interfaces src/dashboard/templates src/utils scripts
echo -e "  ${GREEN}✓${NC} Directories ready"

# ── Step 6: Initialize memory files ──
echo ""
echo -e "${CYAN}[6/8] Initializing memory files...${NC}"
python3 scripts/memory_sync.py
echo -e "  ${GREEN}✓${NC} Memory files initialized"

# ── Step 7: Configure secrets ──
echo ""
echo -e "${CYAN}[7/8] Configuring secrets...${NC}"

if [ -f ".env" ]; then
    echo -e "  ${YELLOW}→${NC} .env already exists — skipping (edit manually to update)"
else
    echo -e "  We need a few secrets. Press Enter to skip any you don't have yet."
    echo ""

    read -p "  Discord Bot Token (PHANTOM_DISCORD_TOKEN): " DISCORD_TOKEN
    read -p "  Discord Guild/Server ID (PHANTOM_GUILD_ID): " GUILD_ID
    read -p "  Groq API Key (GROQ_API_KEY): " GROQ_KEY
    read -p "  GitHub Token for repo watching (GITHUB_TOKEN, optional): " GITHUB_TOKEN
    read -p "  Discord Webhook for morning briefings (optional): " BRIEFING_WEBHOOK
    read -p "  Discord Webhook for surprises (optional): " SURPRISES_WEBHOOK
    read -p "  Discord Webhook for research (optional): " RESEARCH_WEBHOOK

    cat > .env << EOF
# Phantom Command Center — Secrets
# DO NOT commit this file to git

PHANTOM_DISCORD_TOKEN=${DISCORD_TOKEN}
PHANTOM_GUILD_ID=${GUILD_ID}
GROQ_API_KEY=${GROQ_KEY}
GITHUB_TOKEN=${GITHUB_TOKEN}

# Discord Webhooks (optional — used by overnight agents)
PHANTOM_BRIEFING_WEBHOOK=${BRIEFING_WEBHOOK}
PHANTOM_SURPRISES_WEBHOOK=${SURPRISES_WEBHOOK}
PHANTOM_RESEARCH_WEBHOOK=${RESEARCH_WEBHOOK}
EOF

    echo -e "  ${GREEN}✓${NC} .env created"
fi

# Ensure .env is gitignored
if [ -f ".gitignore" ]; then
    if ! grep -q "\.env" .gitignore; then
        echo ".env" >> .gitignore
    fi
else
    echo ".env" > .gitignore
    echo ".venv/" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
fi

# ── Step 8: Start services ──
echo ""
echo -e "${CYAN}[8/8] Starting Phantom...${NC}"
echo ""
echo -e "${PURPLE}╔══════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║          🔮 PHANTOM IS READY 🔮          ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo -e "  1. Start the dashboard:    ${CYAN}python src/dashboard/server.py${NC}"
echo -e "     Then open:             ${CYAN}http://localhost:3000${NC}"
echo ""
echo -e "  2. Start the Discord bot:  ${CYAN}python src/interfaces/discord_bot.py${NC}"
echo ""
echo -e "  3. In Discord, go to #phantom-commands and type: ${CYAN}status${NC}"
echo ""
echo -e "  4. LM Studio: Load a model and ensure it's running at ${CYAN}localhost:1234${NC}"
echo ""
echo -e "${YELLOW}Scheduled tasks will run automatically once the bot is running.${NC}"
echo -e "${YELLOW}First overnight build: 2 AM | Research: 11 PM | Briefing: 6 AM${NC}"
echo ""
