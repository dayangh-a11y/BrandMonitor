"""Crawler package — production mass collection."""

from src.crawler.manager import CrawlerManager, make_dedupe_key
from src.crawler.mass import refresh_successful_races, run_mass_crawl, seed_discovery
from src.crawler.metrics import collect_dashboard_metrics, format_dashboard
from src.crawler.models import CrawlJob
from src.crawler.reports import generate_daily_report
from src.crawler.stats import CrawlDailyReport, CrawlRun
from src.crawler.worker import CrawlWorker

__all__ = [
    "CrawlDailyReport",
    "CrawlJob",
    "CrawlRun",
    "CrawlWorker",
    "CrawlerManager",
    "collect_dashboard_metrics",
    "format_dashboard",
    "generate_daily_report",
    "make_dedupe_key",
    "refresh_successful_races",
    "run_mass_crawl",
    "seed_discovery",
]
