import os
import sys
import asyncio
from dotenv import load_dotenv
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

def run():
    # Load .env from the project root (one level above this script)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_path = os.path.join(project_root, ".env")
    load_dotenv(dotenv_path)
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Force the current directory onto Python's path to resolve modules correctly
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    # Set the environment configuration explicitly
    os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'legal_monitor.settings')
    
    settings = get_project_settings()
    
    # CRITICAL PLAYWRIGHT SETTINGS CHECK
    # If these are missing or overridden in settings.py, Playwright won't spawn!
    settings.set('DOWNLOAD_HANDLERS', {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    }, priority='cmdline')
    
    settings.set('TWISTED_REACTOR', 'twisted.internet.asyncioreactor.AsyncioSelectorReactor', priority='cmdline')

    process = CrawlerProcess(settings)
    
    print("🚀 Triggering Crawler Process for all 5 jurisdiction spiders...")
    process.crawl('eu_ai_act')
    process.crawl('us_ai_laws')
    process.crawl('moitt_pakistan')
    process.crawl('uk_ai_laws')
    process.crawl('canada_ai_laws')
    process.start()

if __name__ == "__main__":
    run()