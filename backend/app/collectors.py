"""Bounded indexing of public Brazilian vacancies and regional search channels.

Listings are observed on the publisher's public page. Search links never become
vacancies, and blocked portals are not bypassed. No candidate data is transmitted.
"""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from time import monotonic
from types import SimpleNamespace
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.job_sources import (ExternalJob, FeedError, amount, clean_description, recruitment_contact,
                             fetch_feed, parse_job_postings, plain, public_https_url)
from app.matching import (brazil_state_name, is_brazilian_job, job_location_details,
                          normalize, related_title, text_contains, title_matches)

logger = logging.getLogger(__name__)
PUBLIC_SOURCE_CACHE_SECONDS = 90
PUBLIC_HEADERS = {'Accept': 'text/html,application/json', 'User-Agent': 'Vagou-PublicBrazilJobIndex/1.0'}
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


@dataclass(frozen=True)
class BrazilianPortal:
    name: str
    origin: str
    hosts: tuple[str, ...]
    detail_pattern: str


BRAZILIAN_PORTALS = (
    BrazilianPortal('Gupy', 'https://portal.gupy.io', ('portal.gupy.io',), r'/jobs?/'),
    BrazilianPortal('LinkedIn', 'https://br.linkedin.com', ('br.linkedin.com', 'www.linkedin.com'), r'/jobs/view/'),
    BrazilianPortal('Indeed', 'https://br.indeed.com', ('br.indeed.com',), r'/viewjob\?'),
    BrazilianPortal('InfoJobs', 'https://www.infojobs.com.br', ('www.infojobs.com.br',), r'/vaga-de-.*__\d+\.aspx'),
    BrazilianPortal('Vagas.com.br', 'https://www.vagas.com.br', ('www.vagas.com.br',), r'/vagas/v\d+/'),
    BrazilianPortal('Catho', 'https://www.catho.com.br', ('www.catho.com.br',), r'/vagas/[^?]+/\d+/?'),
    BrazilianPortal('Programathor', 'https://programathor.com.br', ('programathor.com.br',), r'/jobs/\d+'),
    BrazilianPortal('Trabalha Brasil', 'https://www.trabalhabrasil.com.br', ('www.trabalhabrasil.com.br',), r'/vagas-de-emprego[^?]*/\d+/?'),
)


def source_name(url: str) -> str:
    host = (urlsplit(url).hostname or 'Fonte autorizada').casefold()
    labels = {'gupy.io': 'Gupy', 'linkedin.com': 'LinkedIn', 'indeed.com': 'Indeed',
        'infojobs.com.br': 'InfoJobs', 'vagas.com.br': 'Vagas.com.br',
        'trabalhabrasil.com.br': 'Trabalha Brasil', 'catho.com.br': 'Catho',
        'programathor.com.br': 'Programathor'}
    return next((label for domain, label in labels.items() if host == domain or host.endswith(f'.{domain}')), host[:120])


def _first(record: dict, *keys, default=None):
    return next((record[key] for key in keys if record.get(key) is not None), default)


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize(value)).strip('-')[:160]


def _query(preferences: dict) -> str:
    # One intended role is more useful than an impossible AND of every skill.
    values = preferences.get('titles') or preferences.get('keywords') or []
    return str(values[0]).strip()[:120] if values else 'vagas'


def _region(preferences: dict) -> tuple[str, str | None]:
    locations = preferences.get('locations') or []
    if not locations:
        return '', None
    details = job_location_details(SimpleNamespace(location=str(locations[0]), modality='onsite'))
    return details.get('city') or '', details.get('state')


def _broader_query(query: str) -> str | None:
    """Broaden a sparse real search without changing the user's saved criteria."""
    if related_title(query, 'suporte'):
        broad = 'suporte'
    else:
        broad = re.sub(r'\b(?:senior|senioridade|pleno|junior|jr|sr|nivel\s*[123]|n\s*[123]|ii|iii|iv)\b',
                       '', normalize(query))
        broad = ' '.join(broad.split()).strip(' -/')
    return broad if broad and normalize(broad) != normalize(query) else None


def portal_search_url(portal: BrazilianPortal, preferences: dict) -> str:
    query = _query(preferences)
    city, state = _region(preferences)
    location = f'{city}, {state}' if city and state else city or 'Brasil'
    if portal.name == 'Gupy':
        params = {'term': query}
        if city:
            params['city'] = city
        # This is the public server-rendered search route, not the defunct API.
        return portal.origin + '/job-search/' + urlencode(params, quote_via=quote)
    if portal.name == 'LinkedIn':
        return portal.origin + '/jobs/search/?' + urlencode({'keywords': query, 'location': location + (', Brasil' if city else ''), 'f_TPR': 'r2592000'})
    if portal.name == 'Indeed':
        return portal.origin + '/jobs?' + urlencode({'q': query, 'l': location})
    if portal.name == 'InfoJobs':
        state_name = brazil_state_name(state) if state else None
        route = '/empregos-em-' + _slug(state_name) + '.aspx' if state_name else '/empregos.aspx'
        return portal.origin + route + '?' + urlencode({'palabra': query, 'poblacion': location})
    if portal.name == 'Vagas.com.br':
        return portal.origin + '/vagas-de-' + _slug(query) + ('-em-' + _slug(city) if city else '')
    if portal.name == 'Catho':
        return portal.origin + '/vagas/' + _slug(query) + ('/' + _slug(city + ('-' + state if state else '')) if city else '') + '/'
    if portal.name == 'Programathor':
        return portal.origin + '/jobs?' + urlencode({'search': query})
    if city and state:
        return portal.origin + '/vagas-de-emprego-em-' + _slug(city + '-' + state) + '/' + _slug(query)
    return portal.origin + '/busca?' + urlencode({'q': query})


def regional_search_channels(preferences: dict) -> list[SearchChannel]:
    """Live official search URLs, explicitly separate from individual vacancies."""
    titles = (preferences.get('titles') or preferences.get('keywords') or ['vagas'])[:3]
    locations = (preferences.get('locations') or ['Brasil'])[:3]
    channels = []
    for title in dict.fromkeys(str(value).strip() for value in titles if str(value).strip()):
        for location in dict.fromkeys(str(value).strip() for value in locations if str(value).strip()):
            selected = {**preferences, 'titles': [title], 'locations': [location] if location != 'Brasil' else []}
            for portal in BRAZILIAN_PORTALS:
                channels.append(SearchChannel(portal.name, portal_search_url(portal, selected), title, location))
    return channels


class _PublicIndex(HTMLParser):
    """Read public job anchors and publisher-provided JSON, never execute JS."""
    def __init__(self):
        super().__init__()
        self.links = []
        self.documents = []
        self._anchor = None
        self._script = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self._anchor = [attrs['href'], attrs.get('title', ''), []]
        if tag == 'script' and (attrs.get('id') == '__NEXT_DATA__' or 'json' in attrs.get('type', '').lower()):
            self._script = attrs
            self._parts = []

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor[2].append(data)
        if self._script is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self._anchor is not None:
            href, title, parts = self._anchor
            self.links.append((href, plain(title or ' '.join(parts), 300)))
            self._anchor = None
        if tag == 'script' and self._script is not None:
            self.documents.append((self._script, ''.join(self._parts)))
            self._script = None
            self._parts = []


def _requirements(description: str) -> str:
    text = unescape(description)
    start = re.search(r'requisitos(?: e qualifica[çc][õo]es)?|qualifica[çc][õo]es|o que (?:voc[eê] precisa|esperamos)|habilidades|requirements', text, re.IGNORECASE)
    if not start:
        return ''
    section = text[start.end():]
    end = re.search(r'informa[çc][õo]es adicionais|benef[ií]cios|o que oferecemos', section, re.IGNORECASE)
    return plain(section[:end.start()] if end else section, 12000)


def _advertised_skills(description: str) -> list[str]:
    # Only actual advertised requirements; never candidate preferences or biography.
    from app.matching import advertised_skills
    return advertised_skills(_requirements(description))


def _normalize_brazilian(jobs: list[ExternalJob]) -> list[ExternalJob]:
    result = []
    seen = set()
    for job in jobs:
        if not is_brazilian_job(job):
            continue
        key = job.source_url
        if key in seen:
            continue
        seen.add(key)
        details = job_location_details(job)
        result.append(replace(job, description=clean_description(job.description),
            contact_email=job.contact_email or recruitment_contact({}, job.description),
            city=details.get('city'), state=details.get('state'), country='BR',
            keywords=job.keywords or _advertised_skills(job.description)))
    return result


def parse_gupy_response(payload: dict, max_jobs: int = 20) -> list[ExternalJob]:
    records = _first(payload, 'data', 'jobs', 'results', default=[])
    if not isinstance(records, list):
        raise FeedError('A página pública da Gupy não contém anúncios estruturados.')
    jobs = []
    for record in records[:max_jobs]:
        if not isinstance(record, dict):
            continue
        try:
            title = plain(_first(record, 'name', 'title', 'jobName', default=''), 160)
            company = plain(_first(record, 'companyName', 'careerPageName', 'company', default=''), 160)
            raw_description = str(_first(record, 'description', 'descriptionText', 'summary', default=''))
            description = plain(unescape(raw_description), 30000)
            url = public_https_url(_first(record, 'jobUrl', 'applicationUrl', 'url', default=''))
            host = (urlsplit(url).hostname or '').casefold()
            if host != 'gupy.io' and not host.endswith('.gupy.io'):
                continue
            if not title or not company or len(description) < 30:
                continue
            expiry = record.get('applicationDeadline')
            if expiry:
                expiration = datetime.fromisoformat(str(expiry).replace('Z', '+00:00'))
                expiration = expiration if expiration.tzinfo else expiration.replace(tzinfo=timezone.utc)
                if expiration < datetime.now(timezone.utc):
                    continue
            job_type = str(record.get('type') or '').casefold()
            if 'talent_pool' in job_type:
                continue
            address = record.get('location') or record.get('address') or {}
            address = address if isinstance(address, dict) else {}
            city = plain(_first(record, 'city', default=_first(address, 'city', 'name', default='')), 80)
            state = plain(_first(record, 'state', 'stateCode', default=_first(address, 'state', 'stateCode', default='')), 40)
            country = record.get('country') or address.get('country')
            location = ', '.join(part for part in (city, state) if part) or 'Não informada'
            mode = str(_first(record, 'modality', 'workplaceType', 'workplace', default='')).casefold()
            if mode in {'on-site', 'on_site', 'onsite', 'presencial'}:
                modality = 'onsite'
            elif mode in {'hybrid', 'hibrido', 'híbrido'}:
                modality = 'hybrid'
            elif mode in {'remote', 'remoto'}:
                modality = 'remote'
            else:
                modality = 'onsite' if city else 'remote'
            tags = _first(record, 'keywords', 'skills', 'tags', default=[])
            tags = tags if isinstance(tags, list) else []
            keywords = sorted({plain(item.get('name') or item.get('label') or '', 80).casefold()
                if isinstance(item, dict) else plain(item, 80).casefold() for item in tags
                if isinstance(item, (str, dict))})[:100]
            keywords = [value for value in keywords if value] or _advertised_skills(raw_description)
            salary = record.get('salary') if isinstance(record.get('salary'), dict) else {}
            minimum = amount(_first(record, 'salaryMin', 'salary_min', default=_first(salary, 'min', 'minimum')))
            maximum = amount(_first(record, 'salaryMax', 'salary_max', default=_first(salary, 'max', 'maximum')))
            currency = str(salary.get('currency') or record.get('salaryCurrency') or '').upper()
            if currency and currency != 'BRL':
                minimum = maximum = 0.0
            if maximum < minimum:
                continue
            contract = str(_first(record, 'contractType', 'employmentType', 'jobType', default=job_type)).casefold()
            contract = {'clt': 'clt', 'pj': 'pj', 'internship': 'internship', 'estágio': 'internship',
                'temporary': 'temporary', 'temporário': 'temporary', 'apprentice': 'apprentice',
                'aprendiz': 'apprentice', 'vacancy_type_effective': 'clt',
                'vacancy_type_internship': 'internship', 'vacancy_type_apprentice': 'apprentice'}.get(contract)
            identity = str(_first(record, 'id', 'jobId', default=hashlib.sha256(url.encode()).hexdigest()))[:255]
            from app.job_sources import recruitment_contact
            jobs.append(ExternalJob(identity, title, company, description, location, modality,
                keywords, minimum, maximum, contract, url, recruitment_contact(record, raw_description),
                city=city or None, state=state or None, country=country))
        except (FeedError, TypeError, ValueError):
            continue
    return _normalize_brazilian(jobs)


async def _public_page(client: httpx.AsyncClient, url: str, allowed_hosts: tuple[str, ...],
                       max_bytes: int, semaphore: asyncio.Semaphore) -> tuple[str, str]:
    public_https_url(url)
    async with semaphore:
        # Canonical redirects are accepted only on the same fixed publisher hosts.
        for hop in range(2):
            if urlsplit(url).hostname not in allowed_hosts:
                raise FeedError('O anúncio saiu do portal público autorizado.')
            async with client.stream('GET', url) as response:
                if response.status_code in {301, 302, 307, 308} and hop == 0:
                    target = urljoin(url, response.headers.get('location', ''))
                    public_https_url(target)
                    url = target
                    continue
                response.raise_for_status()
                content_type = response.headers.get('content-type', '').lower()
                if not any(value in content_type for value in ('text/html', 'application/json')):
                    raise FeedError('O portal não respondeu com anúncios públicos legíveis.')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise FeedError('O portal excedeu o limite de leitura.')
                return body.decode('utf-8'), url
    raise FeedError('Não foi possível resolver a página pública do portal.')


def _detail_links(page: str, page_url: str, portal: BrazilianPortal, query: str, limit: int) -> list[str]:
    parser = _PublicIndex()
    parser.feed(page)
    candidates = []
    seen = set()
    for href, title in parser.links:
        url = urljoin(page_url, unescape(href))
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in portal.hosts or not re.search(portal.detail_pattern, parsed.path + ('?' if parsed.query else '')):
            continue
        # Strip tracking parameters, retaining Indeed's actual vacancy identity.
        if portal.name != 'Indeed':
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
        if url in seen:
            continue
        seen.add(url)
        candidates.append((0 if text_contains(title, query) else 1, url))
    return [url for _, url in sorted(candidates, key=lambda value: value[0])[:limit]]


def _gupy_payload(page: str) -> dict:
    parser = _PublicIndex()
    parser.feed(page)
    document = next((value for attrs, value in parser.documents if attrs.get('id') == '__NEXT_DATA__'), None)
    if not document:
        raise FeedError('A Gupy não publicou anúncios estruturados nesta página.')
    props = json.loads(document).get('props', {}).get('pageProps', {})
    return props.get('initialJobList') or {'data': []}


async def collect_gupy(preferences: dict, max_jobs: int = 20,
                       api_url: str | None = None, *, semaphore=None,
                       max_bytes: int = 2 * 1024 * 1024) -> CollectedSource:
    portal = BRAZILIAN_PORTALS[0]
    url = api_url or portal_search_url(portal, preferences)
    # The optional legacy administrative endpoint keeps exact explicit host scope.
    hosts = (urlsplit(url).hostname,) if api_url else portal.hosts
    semaphore = semaphore or asyncio.Semaphore(4)
    deadline = monotonic() + 12
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, headers=PUBLIC_HEADERS) as client:
        page, _ = await asyncio.wait_for(_public_page(client, url, hosts, max_bytes, semaphore), timeout=12)
        payload = json.loads(page) if api_url else _gupy_payload(page)
        jobs = parse_gupy_response(payload, max_jobs)
        broader = _broader_query(_query(preferences))
        if not api_url and broader and len(jobs) < min(3, max_jobs):
            budget = min(5, deadline - monotonic())
            if budget > .2:
                async def broaden_region():
                    regional = {**preferences, 'titles': [broader]}
                    html, _ = await _public_page(client, portal_search_url(portal, regional),
                        portal.hosts, max_bytes, semaphore)
                    return parse_gupy_response(_gupy_payload(html), max_jobs)
                try:
                    jobs = _normalize_brazilian([*jobs, *await asyncio.wait_for(broaden_region(), timeout=budget)])
                    jobs.sort(key=lambda job: 0 if title_matches(job.title, _query(preferences)) else 1)
                except Exception as error:
                    logger.info('brazil_regional_index_deferred source=Gupy error_type=%s', type(error).__name__)
        remaining = min(4, max_jobs - len(jobs))
        budget = min(5, deadline - monotonic())
        if not api_url and remaining > 0 and budget > .2 and 'remote' in (preferences.get('modalities') or []):
            async def remote_details():
                remote_url = portal.origin + '/job-search/' + urlencode(
                    {'term': broader or _query(preferences), 'workplaceTypes[]': 'remote'}, quote_via=quote)
                remote_page, _ = await _public_page(client, remote_url, portal.hosts, max_bytes, semaphore)
                records = _gupy_payload(remote_page).get('data', [])
                candidates = [record for record in records if isinstance(record, dict)
                    and record.get('workplaceType') == 'remote' and not record.get('city')][:remaining]
                async def detail(record):
                    try:
                        detail_url = public_https_url(record.get('jobUrl') or '')
                        host = urlsplit(detail_url).hostname or ''
                        if not host.endswith('.gupy.io'):
                            return []
                        html, canonical = await _public_page(client, detail_url, (host,), max_bytes, semaphore)
                        # Brazil-only remote scope must be stated by the actual
                        # JobPosting, not inferred from a Portuguese company bio.
                        return _normalize_brazilian(parse_job_postings(html, canonical, max_jobs=1))
                    except Exception as error:
                        logger.info('brazil_job_detail_unavailable source=Gupy error_type=%s', type(error).__name__)
                        return []
                return [job for group in await asyncio.gather(*(detail(record) for record in candidates)) for job in group]
            try:
                jobs.extend(await asyncio.wait_for(remote_details(), timeout=budget))
            except Exception as error:
                # An optional remote lookup never discards verified city jobs.
                logger.info('brazil_remote_index_deferred source=Gupy error_type=%s', type(error).__name__)
    return CollectedSource('Gupy', _normalize_brazilian(jobs)[:max_jobs], auto_approve=True)


async def collect_brazilian_portal(portal: BrazilianPortal, preferences: dict, max_jobs: int = 20,
                                  *, semaphore=None, max_bytes: int = 2 * 1024 * 1024) -> CollectedSource:
    if portal.name == 'Gupy':
        return await collect_gupy(preferences, max_jobs, semaphore=semaphore, max_bytes=max_bytes)
    semaphore = semaphore or asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, headers=PUBLIC_HEADERS) as client:
        page, page_url = await _public_page(client, portal_search_url(portal, preferences), portal.hosts, max_bytes, semaphore)
        jobs = parse_job_postings(page, page_url, max_jobs=max_jobs)
        # Limit detail reads per publisher; never crawl arbitrary or private links.
        links = _detail_links(page, page_url, portal, _query(preferences), min(max_jobs, 6))
        async def detail(url):
            try:
                html, canonical = await _public_page(client, url, portal.hosts, max_bytes, semaphore)
                return parse_job_postings(html, canonical, max_jobs=1)
            except Exception as error:
                logger.info('brazil_job_detail_unavailable source=%s error_type=%s', portal.name, type(error).__name__)
                return []
        results = await asyncio.gather(*(detail(url) for url in links))
        for result in results:
            jobs.extend(result)
    return CollectedSource(portal.name, _normalize_brazilian(jobs)[:max_jobs], auto_approve=True)


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

    async def collect(url):
        try:
            async def read():
                async with semaphore:
                    return await fetch_feed(url, allowed_hosts, max_bytes, max_jobs)
            jobs = await asyncio.wait_for(read(), timeout=14)
            return CollectedSource(source_name(url), _normalize_brazilian(jobs))
        except Exception as error:
            logger.info('brazil_feed_unavailable source=%s error_type=%s', source_name(url), type(error).__name__)
            return None

    async def builtin(portal):
        try:
            return await asyncio.wait_for(collect_brazilian_portal(portal, preferences,
                max_jobs=min(max_jobs, 30), semaphore=semaphore, max_bytes=max_bytes), timeout=14)
        except Exception as error:
            logger.info('brazil_portal_unavailable source=%s error_type=%s fallback=regional_search', portal.name, type(error).__name__)
            return None

    tasks = [collect(url) for url in urls[:20]]
    if preferences:
        tasks.extend(builtin(portal) for portal in BRAZILIAN_PORTALS)
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
