"""Concurrent collection from administrator-approved public job feeds only."""
import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.job_sources import ExternalJob, FeedError, fetch_feed


@dataclass(frozen=True)
class CollectedSource:
    name: str
    jobs: list[ExternalJob]


def source_name(url: str) -> str:
    host = (urlsplit(url).hostname or 'Fonte autorizada').casefold()
    labels = {
        'gupy.io': 'Gupy', 'linkedin.com': 'LinkedIn', 'indeed.com': 'Indeed',
        'infojobs.com.br': 'InfoJobs', 'vagas.com.br': 'Vagas.com.br',
        'trabalhabrasil.com.br': 'Trabalha Brasil', 'catho.com.br': 'Catho',
        'glassdoor.com': 'Glassdoor', 'remotive.com': 'Remotive',
    }
    return next((label for domain, label in labels.items() if host == domain or host.endswith(f'.{domain}')), host[:120])


async def collect_authorized_sources(urls: list[str], allowed_hosts: list[str],
                                    max_bytes: int, max_jobs: int,
                                    concurrency: int = 4) -> tuple[list[CollectedSource], int]:
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))

    async def collect(url: str):
        async with semaphore:
            try:
                jobs = await fetch_feed(url, allowed_hosts, max_bytes, max_jobs)
                return CollectedSource(source_name(url), jobs)
            except Exception:
                return None

    results = await asyncio.gather(*(collect(url) for url in urls[:20]))
    sources = [result for result in results if result is not None]
    return sources, len(results) - len(sources)