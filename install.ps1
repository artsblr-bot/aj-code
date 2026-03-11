# AJax Code Windows Installer
$ErrorActionPreference = "Stop"

Write-Host "AJax Code Installer v1.0.0" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pyver = python --version 2>&1
    Write-Host "OK Python: $pyver" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python 3.8+ required. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# Check / install Ollama
if (!(Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Ollama via winget..." -ForegroundColor Yellow
    winget install Ollama.Ollama
}

# Start Ollama
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3

# Install Python deps
Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
pip install rich prompt-toolkit pyfiglet ollama duckduckgo-search `
    gitpython chromadb psutil requests pathspec tiktoken

# Install aj-code
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
pip install -e $scriptDir

# Pull model
Write-Host "Pulling qwen2.5-coder:1.5b..." -ForegroundColor Cyan
ollama pull qwen2.5-coder:1.5b

$response = Read-Host "Pull deepseek-coder:6.7b too? (better quality, ~4GB) [y/N]"
if ($response -eq "y" -or $response -eq "Y") {
    ollama pull deepseek-coder:6.7b
}

Write-Host ""
Write-Host "AJax Code installed! Run: aj-code" -ForegroundColor Green
