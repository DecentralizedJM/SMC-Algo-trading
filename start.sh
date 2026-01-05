#!/bin/bash
# SMC Trading Bot Starter

# Set path to Mudrex SDK
export PYTHONPATH="/Users/jm/.gemini/antigravity/scratch/mudrex-api-trading-python-sdk:$PYTHONPATH"

cd /Users/jm/.gemini/antigravity/scratch/smc-trading-bot

echo "🧠 Starting SMC Trading Bot..."
echo "   Config: config.json"
echo "   Mode: $(grep -o '"dry_run": [a-z]*' config.json)"
echo ""

# Run bot (use caffeinate to prevent sleep)
caffeinate -i python3 bot.py
