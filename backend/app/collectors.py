"""Concurrent collection from the public Gupy API and approved job feeds."""
import asyncio
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.job_sources import ExternalJob, FeedError, amount, fetch_feed, plain, public_https_url

GUPY_API_URL = 'https://portal.api.gupy.io/api/v1/jobs'


@dataclass(frozen=True)
class CollectedSource:
    name: str
    jobs: list[ExternalJob]
    auto_approve: bool = False


def source_name(url: str) -> str:
    host = (urlsplit(url).hostname or 'Fonte autorizada').casefold()
    labels = {
        'gupy.io': 'Gupy', 'linkedin.com': 'LinkedIn', 'indeed.com': 'Indeed',
        'infojobs.com.br': 'InfoJobs', 'vagas.com.br': 'Vagas.com.br',
        'trabalhabrasil.com.br': 'Trabalha Brasil', 'catho.com.br': 'Catho',
        'glassdoor.com': 'Glassdoor', 'remotive.com': 'Remotive',
        'arbeitnow.com': 'Arbeitnow', 'programathor.com.br': 'Programathor',
    }
    return next((label for domain, label in labels.items() if host == domain or host.endswith(f'.{domain}')), host[:120])


def _first(record: dict, *keys, default=None):
    return next((record[key] for key in keys if record.get(key) is not None), default)


def parse_gupy_response(payload: dict, max_jobs: int = 20) -> list[ExternalJob]:
    records = _first(payload, 'data', 'jobs', 'results', default=[])
    if not isinstance(records, list):
        raise FeedError('A API pública da Gupy retornou uma lista inválida.')
    jobs = []
    for record in records[:max_jobs]:
        if not isinstance(record, dict):
            continue
        try:
            title = plain(_first(record, 'name', 'title', 'jobName', default=''), 160)
            company = plain(_first(record, 'companyName', 'careerPageName', 'company', default=''), 160)
            description = plain(_first(record, 'description', 'descriptionText', 'summary', default=''), 30000)
            url = public_https_url(_first(record, 'jobUrl', 'applicationUrl', 'url', 'careerPageUrl', default=''))
            host = (urlsplit(url).hostname or '').casefold()
            if host != 'gupy.io' and not host.endswith('.gupy.io'):
                continue
            if not title or not company or len(description) < 30:
                continue

            address = record.get('location') or record.get('address') or {}
            address = address if isinstance(address, dict) else {}
            city = plain(_first(record, 'city', default=_first(address, 'city', 'name', default='')), 80)
            state = plain(_first(record, 'state', 'stateCode', default=_first(address, 'state', 'stateCode', default='')), 8).upper()
            location = ', '.join(part for part in (city, state) if part) or plain(str(record.get('location') or 'Não informada'), 160)

            detail = f"{title} {description} {location}".casefold()
            mode = str(_first(record, 'modality', 'workplaceType', 'workplace', default='')).casefold()
            if 'remot' in mode or 'remot' in detail:
                modality = 'remote'
            elif 'hybrid' in mode or 'híbr' in detail or 'hibrid' in mode:
                modality = 'hybrid'
            else:
                modality = 'onsite'

            tags = _first(record, 'keywords', 'skills', 'tags', default=[])
            if not isinstance(tags, list):
                tags = []
            keywords = sorted({plain(item.get('name') or item.get('label') or '', 80).casefold()
                if isinstance(item, dict) else plain(item, 80).casefold() for item in tags
                if isinstance(item, (str, dict)) and plain(item.get('name') if isinstance(item, dict) else item, 80)})[:100]
            salary = record.get('salary') if isinstance(record.get('salary'), dict) else {}
            minimum = amount(_first(record, 'salaryMin', 'salary_min', default=_first(salary, 'min', 'minimum')))
            maximum = amount(_first(record, 'salaryMax', 'salary_max', default=_first(salary, 'max', 'maximum')))
            if maximum and maximum < minimum:
                continue
            contract = str(_first(record, 'contractType', 'employmentType', 'jobType', default='')).casefold()
            contract = {'clt': 'clt', 'pj': 'pj', 'internship': 'internship', 'estágio': 'internship',
                'temporary': 'temporary', 'temporário': 'temporary', 'apprentice': 'apprentice', 'aprendiz': 'apprentice'}.get(contract)
            identity = str(_first(record, 'id', 'jobId', default=hashlib.sha256(url.encode()).hexdigest()))[:255]
            jobs.append(ExternalJob(identity, title, company, description, location, modality,
                keywords, minimum, maximum, contract, url))
        except (FeedError, TypeError, ValueError):
            continue
    return jobs


def gupy_search_params(preferences: dict) -> dict:
    titles = preferences.get('titles') or []
    keywords = preferences.get('keywords') or []
    query = ' '.join(dict.fromkeys([*(str(item).strip() for item in titles),
        *(str(item).strip() for item in keywords)]))[:180]
    params = {'jobName': query, 'limit': 20}
    locations = preferences.get('locations') or []
    if locations:
        parts = re.split(r'\s*[/,]\s*', str(locations[0]), maxsplit=1)
        params['city'] = parts[0][:80]
        if len(parts) > 1:
            params['state'] = parts[1][:8].upper()
    return params


async def collect_gupy(preferences: dict, max_jobs: int = 20) -> CollectedSource:
    params = gupy_search_params(preferences)
    if not params['jobName']:
        return CollectedSource('Gupy', [])
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False,
            headers={'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedJobSearch/1.0'}) as client:
        response = await client.get(GUPY_API_URL, params=params)
        response.raise_for_status()
        if len(response.content) > 2 * 1024 * 1024:
            raise FeedError('A resposta pública da Gupy excedeu o limite de tamanho.')
        try:
            payload = response.json()
        except ValueError:
            raise FeedError('A API pública da Gupy retornou JSON inválido.') from None
    return CollectedSource('Gupy', parse_gupy_response(payload, max_jobs), auto_approve=True)


async def collect_authorized_sources(urls: list[str], allowed_hosts: list[str],
                                    max_bytes: int, max_jobs: int,
                                    concurrency: int = 4,
                                    preferences: dict | None = None) -> tuple[list[CollectedSource], int]:
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))

    async def collect(url: str):
        async with semaphore:
            try:
                jobs = await fetch_feed(url, allowed_hosts, max_bytes, max_jobs)
                return CollectedSource(source_name(url), jobs)
            except Exception:
                return None

    tasks = [collect(url) for url in urls[:20]]
    if preferences:
        async def collect_gupy_safely():
            try:
                return await collect_gupy(preferences, max_jobs=20)
            except Exception:
                return None
        tasks.append(collect_gupy_safely())
    results = await asyncio.gather(*tasks)
    sources = [result for result in results if result is not None]
    return sources, len(results) - len(sources)