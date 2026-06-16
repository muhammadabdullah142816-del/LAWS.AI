import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class TestSpider(scrapy.Spider):
    name = "test"
    def start_requests(self):
        yield scrapy.Request("https://example.com", meta={"playwright": True, "playwright_include_page": True})
        
    async def parse(self, response):
        page = response.meta.get("playwright_page")
        print(">>> PAGE IS:", page)
        if page:
            await page.close()

settings = get_project_settings()
settings.set("DOWNLOAD_HANDLERS", {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
})
settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor")
process = CrawlerProcess(settings)
process.crawl(TestSpider)
process.start()
