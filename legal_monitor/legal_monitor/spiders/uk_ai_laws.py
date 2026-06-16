import scrapy
from scrapy_playwright.page import PageMethod


class UkAiLawsSpider(scrapy.Spider):
    """
    SPIDER: United Kingdom AI Regulatory Framework

    Targets:
    1. UK AI Safety Institute — Foundation Model Taskforce guidance (GOV.UK)
    2. Online Safety Act 2023 — Ofcom AI content obligations (legislation.gov.uk)
    3. ICO Guidance on AI and Data Protection (ico.org.uk)
    4. UK DSIT AI Regulation White Paper response (GOV.UK)
    """

    name = "uk_ai_laws"

    start_urls = [
        # UK AI Regulation White Paper / Pro-innovation approach
        "https://www.gov.uk/government/publications/ai-regulation-a-pro-innovation-approach",
        # Online Safety Act 2023 overview
        "https://www.legislation.gov.uk/ukpga/2023/50/contents",
        # ICO Guidance: explaining decisions made with AI
        "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/artificial-intelligence/explaining-decisions-made-with-artificial-intelligence/",
        # AI Safety Institute overview
        "https://www.gov.uk/government/organisations/ai-safety-institute",
    ]

    _URL_META = {
        "gov.uk/government/publications/ai-regulation": {
            "sub_jurisdiction": "England and Wales",
            "document_type":    "White Paper",
        },
        "legislation.gov.uk": {
            "sub_jurisdiction": "Great Britain",
            "document_type":    "Statute",
        },
        "ico.org.uk": {
            "sub_jurisdiction": "England and Wales",
            "document_type":    "Regulatory Guidance",
        },
        "ai-safety-institute": {
            "sub_jurisdiction": "United Kingdom",
            "document_type":    "Government Guidance",
        },
    }

    def _classify(self, url: str) -> tuple[str, str]:
        for fragment, meta in self._URL_META.items():
            if fragment in url:
                return meta["sub_jurisdiction"], meta["document_type"]
        return "United Kingdom", "Government Guidance"

    def start_requests(self):
        for url in self.start_urls:
            sub_jurisdiction, document_type = self._classify(url)
            self.logger.info(f"🚀 UK SPIDER — requesting: {url}")
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
        self.logger.info(f"🎯 UK SPIDER parse — {response.url} ({len(response.body)} bytes)")
        try:
            raw_text = response.css("body ::text").getall()
            clean_text = " ".join([t.strip() for t in raw_text if t.strip()])

            if len(clean_text) < 200:
                self.logger.warning(f"⚠ Very short page body ({len(clean_text)} chars) — skipping: {response.url}")
                return

            yield {
                "jurisdiction":     "United Kingdom",
                "sub_jurisdiction": response.meta.get("sub_jurisdiction", "United Kingdom"),
                "document_type":    response.meta.get("document_type", "Government Guidance"),
                "source_url":       response.url,
                "raw_text":         clean_text,
            }
        except Exception as exc:
            self.logger.error(f"💥 UK spider parse error: {exc}")

    def handle_error(self, failure):
        self.logger.error(f"🛑 UK Spider request failure: {repr(failure)}")
