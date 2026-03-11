#!/bin/bash
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "  █████╗      ██╗ █████╗ ██╗  ██╗    ██████╗ ██████╗ ██████╗ ███████╗"
echo "  ██╔══██╗     ██║██╔══██╗╚██╗██╔╝   ██╔════╝██╔═══██╗██╔══██╗██╔════╝"
echo "  ███████║     ██║███████║ ╚███╔╝    ██║     ██║   ██║██║  ██║█████╗  "
echo "  ██╔══██║██   ██║██╔══██║ ██╔██╗    ██║     ██║   ██║██║  ██║██╔══╝  "
echo "  ██║  ██║╚█████╔╝██║  ██║██╔╝ ██╗   ╚██████╗╚██████╔╝██████╔╝███████╗"
echo "  ╚═╝  ╚═╝ ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝    ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝"
echo -e "${RESET}"
echo -e "${BOLD}AJax Code Installer v1.0.0${RESET}"
echo ""

# Detect OS
OS=""
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${RESET}"
    exit 1
fi
echo -e "${GREEN}✓ OS detected: $OS${RESET}"

# Check Python 3.8+
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3.8+ is required. Please install it first.${RESET}"
    exit 1
fi
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✓ Python $PYVER detected${RESET}"

# Check / install Ollama
if ! command -v ollama &>/dev/null; then
    echo -e "${YELLOW}Ollama not found. Installing...${RESET}"
    curl -fsSL https://ollama.ai/install.sh | sh
else
    echo -e "${GREEN}✓ Ollama detected${RESET}"
fi

# Start Ollama if not running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo -e "${YELLOW}Starting Ollama server...${RESET}"
    ollama serve &>/dev/null &
    sleep 3
fi

# Install Python deps
echo ""
echo -e "${CYAN}Installing Python dependencies...${RESET}"
pip3 install rich prompt-toolkit pyfiglet ollama duckduckgo-search \
    gitpython chromadb psutil requests pathspec tiktoken \
    --break-system-packages --quiet

# Install aj-code from local directory (or pip when published)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/setup.py" ]; then
    echo -e "${CYAN}Installing aj-code from source...${RESET}"
    pip3 install -e "$SCRIPT_DIR" --break-system-packages --quiet
fi

# Pull smallest model automatically
echo ""
echo -e "${CYAN}Pulling qwen2.5-coder:1.5b (fastest model)...${RESET}"
ollama pull qwen2.5-coder:1.5b

# Ask about larger model
echo ""
echo -e "${CYAN}Optional: Pull deepseek-coder:6.7b for better quality (~4GB)?${RESET}"
echo -e "Run later: ${BOLD}ollama pull deepseek-coder:6.7b${RESET}"

echo ""
echo -e "${GREEN}${BOLD}✅ AJax Code installed successfully!${RESET}"
echo ""
echo -e "  Start with: ${CYAN}aj-code${RESET}"
echo -e "  Or:         ${CYAN}python3 -m aj_code.main${RESET}"
echo ""
