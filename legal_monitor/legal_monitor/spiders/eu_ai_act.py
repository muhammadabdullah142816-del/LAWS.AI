import scrapy
from scrapy_playwright.page import PageMethod

class EuAiActSpider(scrapy.Spider):
    name = "eu_ai_act"
    allowed_domains = ["eur-lex.europa.eu"]
    
    # Force execution via Scrapy's internal iterative array parser
    start_urls = ["https://eur-lex.europa.eu/eli/reg/2024/1689/oj"]

    def start_requests(self):
        """
        Generates initial requests for the spider, ensuring Playwright is activated.
        """
        for url in self.start_urls:
            self.logger.info(f"🚀 NATIVE BACKPASS ACTIVATED FOR TARGET: {url}")
            
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_load_state", "networkidle"),
                        PageMethod("wait_for_timeout", 6000), 
                    ],
                },
                dont_filter=True
            )

    async def parse(self, response):
        self.logger.info("🎯 ENGINE CONNECTED TO PARSE METHOD!")
        
        try:
            page_size = len(response.body)
            self.logger.info(f"✅ Downloaded Rendered Page Size: {page_size} bytes.")

            raw_text = response.css("body ::text").getall()
            clean_text = " ".join([t.strip() for t in raw_text if t.strip()])

            yield {
                "jurisdiction": "European Union",
                "sub_jurisdiction": "European Union",
                "document_type": "Regulation",
                "source_url": response.url,
                "raw_text": clean_text
            }
            
        except Exception as e:
            self.logger.error(f"💥 Critical error processing page content: {str(e)}")

    def handle_error(self, failure):
        self.logger.error(f"🛑 Downloader Request Failure: {repr(failure)}")