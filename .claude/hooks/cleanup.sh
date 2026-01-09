#!/bin/bash
# Cleanup script to stop Playwright Docker containers on Claude Code exit
# This prevents the user data directory from remaining locked

# Stop all Playwright MCP containers
docker ps -q --filter "ancestor=mcr.microsoft.com/playwright/mcp" | xargs -r docker stop

exit 0
