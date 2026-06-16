#!/bin/bash
# run.sh
# Automated execution run loop for the Legal Scraper Pipeline

echo "======================================================"
echo " Starting AI LAW JAILBREAK Data Ingestion Engine"
echo "======================================================"

cd /app/legal_monitor

# Continuous execution loop
while true; do
    echo "[$(date)] Launching spiders..."

    # EU AI Act Spider — EUR-Lex Regulation 2024/1689
    echo "[$(date)] [1/2] Crawling EU AI Act from EUR-Lex..."
    scrapy crawl eu_ai_act --loglevel=INFO 2>&1
    EU_EXIT=$?
    echo "[$(date)] [1/2] EU AI Act spider exited with code: $EU_EXIT"

    # Pakistan MoITT Spider — National AI Policy & Islamabad Declaration
    echo "[$(date)] [2/2] Crawling MoITT Pakistan portal..."
    scrapy crawl moitt_pakistan --loglevel=INFO 2>&1
    PK_EXIT=$?
    echo "[$(date)] [2/2] MoITT Pakistan spider exited with code: $PK_EXIT"

    echo "[$(date)] All spiders finished. EU=$EU_EXIT PK=$PK_EXIT"
    echo "[$(date)] Sleeping for 24 hours before next sweep..."
    sleep 86400
done
