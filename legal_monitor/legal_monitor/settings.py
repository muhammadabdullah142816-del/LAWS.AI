BOT_NAME = "legal_monitor"

SPIDER_MODULES = ["legal_monitor.spiders"]
NEWSPIDER_MODULE = "legal_monitor.spiders"

# ──────────────────────────────────────────────────────────────────────
# ANTI-BOT BYPASS & CONCURRENCY
# ──────────────────────────────────────────────────────────────────────
# Clean desktop user agent string to blend in with normal organic traffic
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Disable obeying robots.txt to keep aggressive government portals from blind-blocking
ROBOTSTXT_OBEY = False

# Scrape conservatively to creep under firewall rate-limiting thresholds
CONCURRENT_REQUESTS = 1
DOWNLOAD_DELAY = 5.0
RANDOMIZE_DOWNLOAD_DELAY = True

# ──────────────────────────────────────────────────────────────────────
# HTTP CACHING (STORAGE OPTIMIZATION)
# ──────────────────────────────────────────────────────────────────────
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 86400  # 24 hours
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [500, 502, 503, 504, 400, 403, 404, 408]

# ──────────────────────────────────────────────────────────────────────
# PLAYWRIGHT INTEGRATION
# ──────────────────────────────────────────────────────────────────────
# Force Playwright Integration Globally for Windows Async Tasks
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# Playwright specific stealth engine settings
PLAYWRIGHT_BROWSER_TYPE = "chromium"

# FIXED KEY: Using SETTINGS ensures Scrapy registers and executes the arguments
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "timeout": 30000,  # 30 seconds max browser startup
    "args": [
        "--disable-blink-features=AutomationControlled", # Erases the 'window.navigator.webdriver' flag entirely
        "--window-size=1920,1080",
        "--disable-infobars",
    ]
}

# ──────────────────────────────────────────────────────────────────────
# PIPELINES
# ──────────────────────────────────────────────────────────────────────
# Activate the Cloud Routing Data Engine to push scraped items directly
# to Pinecone and Supabase, bypassing local storage entirely.
ITEM_PIPELINES = {
    "legal_monitor.pipelines.LegalCloudRoutingPipeline": 300,
}

# Future-proof core pipeline settings
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
FEED_EXPORT_ENCODING = "utf-8"

# ──────────────────────────────────────────────────────────────────────
# LOGGING (DIAGNOSTIC MODE)
# ──────────────────────────────────────────────────────────────────────
LOG_LEVEL = "DEBUG"
LOG_STDOUT = True