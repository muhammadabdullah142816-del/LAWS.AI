import scrapy
from scrapy_playwright.page import PageMethod


class CanadaAiLawsSpider(scrapy.Spider):
    """
    SPIDER: Canada AI Regulatory Framework

    Targets:
    1. Artificial Intelligence and Data Act (AIDA) — Bill C-27, Part 3 (parl.ca)
    2. Office of the Privacy Commissioner — AI guidance (priv.gc.ca)
    3. Treasury Board Directive on Automated Decision-Making (tbs-sct.gc.ca)
    4. ISED Voluntary Code of Conduct on Generative AI (ised-isde.canada.ca)
    """

    name = "canada_ai_laws"

    start_urls = [
        # Bill C-27 / AIDA text on Parliament of Canada
        "https://www.parl.ca/DocumentViewer/en/44-1/bill/C-27/third-reading",
        # OPC AI and Privacy guidance
        "https://www.priv.gc.ca/en/privacy-topics/technology/artificial-intelligence/",
        # Treasury Board Directive on Automated Decision Making
        "https://www.tbs-sct.gc.ca/pol/doc-eng.aspx?id=32592",
        # ISED Voluntary Code of Conduct on Generative AI
        "https://ised-isde.canada.ca/site/ised/en/voluntary-code-conduct-responsible-development-and-management-advanced-generative-ai-systems",
    ]

    _URL_META = {
        "parl.ca": {
            "sub_jurisdiction": "Federal",
            "document_type":    "Bill / Statute",
        },
        "priv.gc.ca": {
            "sub_jurisdiction": "Federal",
            "document_type":    "Regulatory Guidance",
        },
        "tbs-sct.gc.ca": {
            "sub_jurisdiction": "Federal",
            "document_type":    "Directive",
        },
        "ised-isde.canada.ca": {
            "sub_jurisdiction": "Federal",
            "document_type":    "Voluntary Code of Conduct",
        },
    }

    def _classify(self, url: str) -> tuple[str, str]:
        for fragment, meta in self._URL_META.items():
            if fragment in url:
                return meta["sub_jurisdiction"], meta["document_type"]
        return "Federal", "Government Guidance"

    def start_requests(self):
        for url in self.start_urls:
            sub_jurisdiction, document_type = self._classify(url)
            self.logger.info(f"🚀 CANADA SPIDER — requesting: {url}")
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
                    "document_type":    document_type,
                },
                dont_filter=True,
            )

    async def parse(self, response):
        self.logger.info(f"🎯 CANADA SPIDER parse — {response.url} ({len(response.body)} bytes)")
        try:
            raw_text = response.css("body ::text").getall()
            clean_text = " ".join([t.strip() for t in raw_text if t.strip()])

            if len(clean_text) < 200:
                self.logger.warning(f"⚠ Very short page body ({len(clean_text)} chars) — skipping: {response.url}")
                return

            yield {
                "jurisdiction":     "Canada",
                "sub_jurisdiction": response.meta.get("sub_jurisdiction", "Federal"),
                "document_type":    response.meta.get("document_type", "Government Guidance"),
                "source_url":       response.url,
                "raw_text":         clean_text,
            }
        except Exception as exc:
            self.logger.error(f"💥 Canada spider parse error: {exc}")

    def handle_error(self, failure):
        self.logger.error(f"🛑 Canada Spider request failure: {repr(failure)}")
