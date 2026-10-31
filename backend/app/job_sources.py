"""Bounded ingestion of explicitly configured public/authorized JSON feeds.

Supported envelopes: {jobs: [...]}; fields cover Remotive's public feed and the
same documented partner contract. This module never sends candidate data or
submits to external websites. Configure only sources whose terms permit reuse.
"""
import hashlib
import ipaddress
import json
import math
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx


class FeedError(ValueError):
    pass


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def plain(value, maximum):
    parser = _Text()
    parser.feed(str(value or ''))
    return ' '.join(' '.join(parser.parts).split())[:maximum]


def public_https_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise FeedError('A fonte deve usar HTTPS público sem credenciais na URL.')
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
            raise FeedError('Endereços locais não são aceitos para fontes de vagas.')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise FeedError('Endereços privados não são aceitos para fontes de vagas.')
        if parsed.fragment:
            raise FeedError('Fragmentos não são aceitos em URLs de fontes.')
        return value
    except (TypeError, ValueError) as error:
        if isinstance(error, FeedError):
            raise
        raise FeedError('URL de fonte inválida.') from None


def approved_source(value: str, allowed_hosts: list[str]) -> str:
    public_https_url(value)
    host = urlsplit(value).hostname.casefold()
    if host not in {entry.casefold() for entry in allowed_hosts}:
        raise FeedError('O host da fonte não está autorizado pelo administrador.')
    return value


def amount(value) -> float:
    # Do not infer numeric BRL remuneration from free-form USD/year salaries.
    if value is None:
        return 0.0
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1000000:
        raise FeedError('Remuneração estruturada inválida.')
    return result


@dataclass(frozen=True)
class ExternalJob:
    source_external_id: str
    title: str
    company: str
    description: str
    location: str
    modality: str
    keywords: list[str]
    salary_min: float
    salary_max: float
    source_url: str

    def values(self):
        return asdict(self)


def parse_feed(data: dict, max_jobs: int = 200) -> list[ExternalJob]:
    records = data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise FeedError('A fonte deve retornar um objeto JSON com uma lista jobs.')
    jobs = []
    for record in records[:max_jobs]:
        if not isinstance(record, dict):
            continue
        try:
            url = public_https_url(record.get('url') or record.get('source_url') or '')
            title = plain(record.get('title'), 160)
            company = plain(record.get('company_name') or record.get('company'), 160)
            description = plain(record.get('description'), 30000)
            tags = record.get('tags', record.get('keywords', []))
            if not isinstance(tags, list):
                raise FeedError('Competências inválidas.')
            keywords = sorted({str(item).strip().casefold() for item in tags if isinstance(item, str) and 0 < len(item.strip()) <= 80})[:100]
            if not title or not company or len(description) < 30 or not keywords:
                continue
            modality = record.get('modality', 'remote')
            if modality not in ('remote', 'hybrid', 'onsite'):
                continue
            minimum, maximum = amount(record.get('salary_min')), amount(record.get('salary_max'))
            if maximum < minimum:
                continue
            identity = str(record.get('id') or hashlib.sha256(url.encode()).hexdigest())[:255]
            jobs.append(ExternalJob(identity, title, company, description,
                plain(record.get('location') or record.get('candidate_required_location') or 'Não informada', 160),
                modality, keywords, minimum, maximum, url))
        except (FeedError, ValueError, TypeError):
            continue
    return jobs


async def fetch_feed(url: str, allowed_hosts: list[str], max_bytes: int = 2 * 1024 * 1024, max_jobs: int = 200) -> list[ExternalJob]:
    approved_source(url, allowed_hosts)
    # Exact administrative host allowlist, no redirects, inherited proxy/TLS trust.
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False) as client:
        async with client.stream('GET', url, headers={'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedFeed/1.0'}) as response:
            response.raise_for_status()
            if 'application/json' not in response.headers.get('content-type', '').lower():
                raise FeedError('A fonte não respondeu com JSON.')
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise FeedError('A resposta da fonte excedeu o limite permitido.')
    try:
        return parse_feed(json.loads(body), max_jobs=max_jobs)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise FeedError('A fonte respondeu com JSON inválido.') from None
