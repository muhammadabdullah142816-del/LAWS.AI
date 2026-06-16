import sys
import os
import asyncio

# Dynamically append the current directory to Python's search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from legal_monitor.spiders.eu_ai_act import EuAiActSpider

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def main():
    settings = get_project_settings()
    
    settings.set("DOWNLOAD_HANDLERS", {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    }, priority="project")
    settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor", priority="project")

    process = CrawlerProcess(settings)
    process.crawl(EuAiActSpider)
    process.start()

if __name__ == "__main__":
    main()
