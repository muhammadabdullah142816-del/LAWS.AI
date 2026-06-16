# Use the official Microsoft Playwright image as the base.
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set non-interactive environment variables to prevent apt prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory inside the container
WORKDIR /app

# ---- LAYER 1: Core Tooling Upgrades ----
RUN pip install --no-cache-dir --upgrade pip

# ---- LAYER 2: FAST CPU TORCH INSTALLATION ----
# This explicitly forces the micro-sized CPU wheel, bypassing gigabytes of CUDA files
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# ---- LAYER 3: Install Remaining Project Dependencies ----
COPY requirements.txt .

# THE CACHE BUSTER: Bump "v1" to "v2" if you ever want to force a clean pip install
ARG REQS_VERSION=v2
RUN echo "Building requirements version: $REQS_VERSION" && \
    pip install --no-cache-dir -r requirements.txt

# ---- LAYER 4: Copy Project Code ----
COPY legal_monitor/ /app/legal_monitor/

# Move into the directory containing your spiders
WORKDIR /app/legal_monitor

# FIX: Automatically generate the missing scrapy.cfg file cleanly
RUN printf "[settings]\ndefault = legal_monitor.settings\n\n[deploy]\nproject = legal_monitor\n" > scrapy.cfg

# ─── ENTRYPOINT: Pure Docker CMD Ingestion Loop ───────
CMD ["sh", "-c", "\
    echo '======================================================' && \
    echo ' Starting AI LAW JAILBREAK Data Ingestion Engine' && \
    echo '======================================================' && \
    while true; do \
    echo \"[$(date)] [1/2] Crawling EU AI Act from EUR-Lex...\" && \
    scrapy crawl eu_ai_act --loglevel=DEBUG 2>&1; \
    EU_EXIT=$?; \
    echo \"[$(date)] [1/2] EU spider exited: $EU_EXIT\"; \
    \
    echo \"[$(date)] [2/2] Crawling MoITT Pakistan portal...\" && \
    scrapy crawl moitt_pakistan --loglevel=DEBUG 2>&1; \
    PK_EXIT=$?; \
    echo \"[$(date)] [2/2] PK spider exited: $PK_EXIT\"; \
    \
    echo \"[$(date)] Sweep complete. EU=$EU_EXIT PK=$PK_EXIT. Sleeping 24h...\"; \
    sleep 86400; \
    done \
    "]