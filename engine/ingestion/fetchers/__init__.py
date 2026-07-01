"""Fetcher registry — maps source name to fetcher class. Lazy imports for partial deploys."""
ACTIVE_FETCHERS = {}
_IMPORT_ERRORS = {}

for _name, _mod, _cls in [
    ("fred", "engine.ingestion.fetchers.fred_fetcher", "FredFetcher"),
    ("github", "engine.ingestion.fetchers.github_fetcher", "GitHubFetcher"),
    ("hackernews", "engine.ingestion.fetchers.hackernews_fetcher", "HackerNewsFetcher"),
    ("stackoverflow", "engine.ingestion.fetchers.stackoverflow_fetcher", "StackOverflowFetcher"),
    ("eastmoney", "engine.ingestion.fetchers.eastmoney_fetcher", "EastMoneyFetcher"),
    ("producthunt", "engine.ingestion.fetchers.producthunt_fetcher", "ProductHuntFetcher"),
    ("_36kr", "engine.ingestion.fetchers._36kr_fetcher", "_36krFetcher"),
    ("google_trends", "engine.ingestion.fetchers.google_trends_fetcher", "GoogleTrendsFetcher"),
]:
    try:
        mod = __import__(_mod, fromlist=[_cls])
        ACTIVE_FETCHERS[_name] = getattr(mod, _cls)
    except (ImportError, ModuleNotFoundError) as e:
        _IMPORT_ERRORS[_name] = str(e)

FUTURE_FETCHERS = [
    "sina", "_36kr", "nbs", "eurostat",
    "producthunt", "google_trends", "g2", "upwork", "crunchbase",
]
