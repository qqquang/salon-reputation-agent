#!/bin/bash

# Navigate to project directory
cd /Users/quangnguyen/Desktop/getbizsonar/salon-reputation-agent

# Activate virtual environment and run agent once
# Recommended Cron Schedule (Every 3 Days): 0 9 */3 * * /Users/quangnguyen/Desktop/getbizsonar/salon-reputation-agent/run_agent.sh
./venv/bin/python src/main.py --once
