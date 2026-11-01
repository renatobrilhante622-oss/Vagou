"""Bounded public feeds plus honest regional search-channel recommendations."""
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from time import monotonic
from urllib.parse import urlencode, urlsplit

import httpx

from app.job_sources import ExternalJob, FeedError, amount, fetch_feed, parse_feed, plain, public_https_url, contact_email
from app.matching import english_search_query

REMOTIVE_API_URL = 'https://remotive.com/api/remote-jobs'
ARBEITNOW_API_URL = 'https://www.arbeitnow.com/api/job-board-api'
JOBICY_API_URL = 'https://jobicy.com/api/v2/remote-jobs'
PUBLIC_SOURCE_CACHE_SECONDS = 90
_source_cache = {}
_cache_lock = asyncio.Lock()


@dataclass(frozen=True)
class SearchChannel:
    source_name: str
    external_url: str
    query: str
    location: str
    destination_channel: str = 'portal_search'


@dataclass(frozen=True)
class CollectedSource:
    name: str
    jobs: list[ExternalJob]
    auto_approve: bool = False
    search_channels: list[SearchChannel] = field(default_factory=list)


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
                keywords, minimum, maximum, contract, url, contact_email(record.get('contact_email') or record.get('recruiter_email'))))
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


def regional_search_channels(preferences: dict) -> list[SearchChannel]:
    """Real search URLs, never fabricated vacancies or automatic submissions."""
    titles = [str(value).strip() for value in preferences.get('titles', []) if str(value).strip()][:3]
    keywords = [str(value).strip() for value in preferences.get('keywords', []) if str(value).strip()][:3]
    queries = list(dict.fromkeys(' '.join(dict.fromkeys([title, *keywords]))[:180] for title in titles)) if titles else [' '.join(keywords) or 'vagas']
    locations = [str(value).strip() for value in preferences.get('locations', []) if str(value).strip()][:3] or ['Brasil']
    channels = []
    portals = [('Gupy', 'gupy.io/jobs'), ('LinkedIn', 'linkedin.com/jobs'),
               ('Indeed', 'br.indeed.com'), ('InfoJobs', 'infojobs.com.br'),
               ('Vagas.com.br', 'vagas.com.br/vagas'), ('Catho', 'catho.com.br/vagas')]
    for query in queries:
        for location in locations:
            for name, domain in portals:
                if name == 'LinkedIn':
                    url = 'https://www.linkedin.com/jobs/search/?' + urlencode({'keywords': query, 'location': location + ', Brasil'})
                elif name == 'Indeed':
                    url = 'https://br.indeed.com/jobs?' + urlencode({'q': query, 'l': location})
                elif name == 'InfoJobs':
                    url = 'https://www.infojobs.com.br/empregos.aspx?' + urlencode({'palabra': query, 'poblacion': location})
                else:
                    # A public, provider-scoped search avoids inventing private
                    # APIs or relying on undocumented ATS routes that return404.
                    url = 'https://www.google.com/search?' + urlencode({'q': f'site:{domain} {query} {location}'})
                channels.append(SearchChannel(name, url, query, location))
    return channels


async def collect_gupy(preferences: dict, max_jobs: int = 20,
                       api_url: str | None = None) -> CollectedSource:
    """Optional explicitly supplied authorized endpoint; no defunct default API."""
    if not api_url:
        return CollectedSource('Gupy', [], search_channels=[channel for channel in regional_search_channels(preferences) if channel.source_name == 'Gupy'])
    public_https_url(api_url)
    params = gupy_search_params(preferences)
    if not params['jobName']:
        return CollectedSource('Gupy', [])
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False,
            headers={'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedJobSearch/1.0'}) as client:
        payload = await _public_json(client, api_url, params)
    return CollectedSource('Gupy', parse_gupy_response(payload, max_jobs), auto_approve=True)


async def _public_json(client: httpx.AsyncClient, url: str, params: dict | None = None,
                       max_bytes: int = 2 * 1024 * 1024) -> dict:
    body = bytearray()
    async with client.stream('GET', url, params=params) as response:
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower()
        if 'application/json' not in content_type:
            raise FeedError('A fonte pública não respondeu com JSON.')
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise FeedError('A fonte pública excedeu o limite de tamanho.')
    try:
        result = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise FeedError('A fonte pública retornou JSON inválido.') from None
    if not isinstance(result, dict):
        raise FeedError('A fonte pública retornou um formato inesperado.')
    return result


async def collect_remotive(preferences: dict, max_jobs: int = 20) -> CollectedSource:
    query = english_search_query(preferences)
    headers = {'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedJobSearch/1.0'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, headers=headers) as client:
        payload = await _public_json(client, REMOTIVE_API_URL, {'search': query, 'limit': max_jobs})
    jobs = parse_feed({'jobs': payload.get('jobs', [])}, max_jobs=max_jobs)
    return CollectedSource('Remotive', [ExternalJob(job.source_external_id, job.title, job.company,
        job.description, job.location, 'remote', job.keywords, job.salary_min, job.salary_max,
        job.contract_type, job.source_url, job.contact_email) for job in jobs], auto_approve=True)


async def collect_arbeitnow(preferences: dict, max_jobs: int = 20) -> CollectedSource:
    headers = {'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedJobSearch/1.0'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, headers=headers) as client:
        payload = await _public_json(client, ARBEITNOW_API_URL, {'page': 1}, max_bytes=4 * 1024 * 1024)
    records = payload.get('data', [])
    if not isinstance(records, list):
        raise FeedError('A fonte Arbeitnow retornou uma lista inválida.')
    normalized = []
    for record in records[:max_jobs]:
        if not isinstance(record, dict):
            continue
        remote = bool(record.get('remote'))
        normalized.append({
            'id': record.get('slug') or record.get('id') or record.get('url'),
            'url': record.get('url'), 'title': record.get('title'),
            'company_name': record.get('company_name'), 'description': record.get('description'),
            'location': record.get('location') or 'Não informada',
            'modality': 'remote' if remote else 'onsite', 'tags': record.get('tags') or [],
            'salary_min': record.get('salary_min'), 'salary_max': record.get('salary_max'),
        })
    return CollectedSource('Arbeitnow', parse_feed({'jobs': normalized}, max_jobs=max_jobs), auto_approve=True)


async def collect_jobicy(preferences: dict, max_jobs: int = 20) -> CollectedSource:
    headers = {'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedJobSearch/1.0'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, headers=headers) as client:
        payload = await _public_json(client, JOBICY_API_URL, {'count': min(max_jobs, 100)})
    records = payload.get('jobs', [])
    if not isinstance(records, list):
        raise FeedError('A fonte Jobicy retornou uma lista inválida.')
    normalized = []
    for record in records[:max_jobs]:
        if not isinstance(record, dict):
            continue
        currency = str(record.get('salaryCurrency') or '').upper()
        normalized.append({
            'id': record.get('id') or record.get('url'), 'url': record.get('url'),
            'title': record.get('jobTitle'), 'company_name': record.get('companyName'),
            'description': record.get('jobDescription') or record.get('jobExcerpt'),
            'location': record.get('jobGeo') or 'Não informada', 'modality': 'remote',
            # Industry labels are not verified technical competencies.
            'tags': record.get('skills') or [],
            'salary_min': record.get('salaryMin') if currency == 'BRL' else None,
            'salary_max': record.get('salaryMax') if currency == 'BRL' else None,
            'contact_email': record.get('contact_email') or record.get('recruiter_email'),
        })
    return CollectedSource('Jobicy', parse_feed({'jobs': normalized}, max_jobs=max_jobs), auto_approve=True)


async def collect_authorized_sources(urls: list[str], allowed_hosts: list[str],
                                    max_bytes: int, max_jobs: int,
                                    concurrency: int = 4,
                                    preferences: dict | None = None) -> tuple[list[CollectedSource], int]:
    cache_key = json.dumps([urls, sorted(allowed_hosts), max_bytes, max_jobs, preferences or {}], sort_keys=True)
    async with _cache_lock:
        cached = _source_cache.get(cache_key)
        if cached and cached[0] > monotonic():
            return cached[1], cached[2]
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
        async def collect_builtin(collector):
            try:
                return await collector(preferences, max_jobs=min(max_jobs, 50))
            except Exception:
                return None
        tasks.extend([collect_builtin(collect_remotive), collect_builtin(collect_arbeitnow), collect_builtin(collect_jobicy)])
    results = await asyncio.gather(*tasks)
    sources = [result for result in results if result is not None]
    failures = len(results) - len(sources)
    if preferences is not None:
        sources.append(CollectedSource('Canais regionais brasileiros', [], search_channels=regional_search_channels(preferences)))
    async with _cache_lock:
        _source_cache[cache_key] = (monotonic() + PUBLIC_SOURCE_CACHE_SECONDS, sources, failures)
        for key, value in list(_source_cache.items()):
            if value[0] <= monotonic():
                _source_cache.pop(key, None)
        while len(_source_cache) > 128:
            oldest = min(_source_cache, key=lambda key: _source_cache[key][0])
            _source_cache.pop(oldest, None)
    return sources, failures