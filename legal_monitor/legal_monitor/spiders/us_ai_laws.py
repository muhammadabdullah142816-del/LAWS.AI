import scrapy
from scrapy_playwright.page import PageMethod

class UsAiLawsSpider(scrapy.Spider):
    name = "us_ai_laws"
    
    # 1. California AB 2013 (Training Data Transparency)
    # 2. Colorado SB 24-205 (Consumer Protection in AI)
    # 3. FTC Section 5 Guidance on AI Deception
    start_urls = [
        "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240AB2013",
        "https://leg.colorado.gov/bills/sb24-205",
        "https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check"
    ]

    def start_requests(self):
        """
        Generates initial requests for the US spider using Playwright to render dynamically loaded bills.
        """
        for url in self.start_urls:
            self.logger.info(f"🚀 NATIVE BACKPASS ACTIVATED FOR US TARGET: {url}")
            
            # Use metadata mapping based on the URL
            sub_jurisdiction = "Federal"
            document_type = "Statute"
            
            if "ca.gov" in url:
                sub_jurisdiction = "California"
            elif "co.gov" in url:
                sub_jurisdiction = "Colorado"
            
            if "ftc.gov" in url:
                document_type = "Regulation"
                
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_load_state", "networkidle"),
                        PageMethod("wait_for_timeout", 5000), 
                    ],
                    "sub_jurisdiction": sub_jurisdiction,
                    "document_type": document_type
                },
                dont_filter=True
            )

    async def parse(self, response):
        self.logger.info(f"🎯 ENGINE CONNECTED TO US PARSE METHOD! ({response.url})")
        
        try:
            page_size = len(response.body)
            self.logger.info(f"✅ Downloaded US Rendered Page Size: {page_size} bytes.")

            raw_text = response.css("body ::text").getall()
            clean_text = " ".join([t.strip() for t in raw_text if t.strip()])

            yield {
                "jurisdiction": "United States",
                "sub_jurisdiction": response.meta.get("sub_jurisdiction"),
                "document_type": response.meta.get("document_type"),
                "source_url": response.url,
                "raw_text": clean_text
            }
            
        except Exception as e:
            self.logger.error(f"💥 Critical error processing US page content: {str(e)}")

    def handle_error(self, failure):
        self.logger.error(f"🛑 Downloader Request Failure (US Spider): {repr(failure)}")
