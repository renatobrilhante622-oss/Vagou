"""Bounded ingestion of explicitly configured public/authorized job feeds.

Supported formats are JSON `{jobs: [...]}`, RSS/Atom, and schema.org JobPosting
JSON-LD. This module never sends candidate data or submits to external websites.
Configure only sources whose terms permit reuse.
"""
import hashlib
import ipaddress
import json
import math
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from xml.etree import ElementTree
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


class _JsonLd(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() == 'script' and dict(attrs).get('type', '').casefold() == 'application/ld+json':
            self.capture = True
            self.parts = []

    def handle_data(self, value):
        if self.capture:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag.casefold() == 'script' and self.capture:
            self.documents.append(''.join(self.parts))
            self.capture = False


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
    contract_type: str | None
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
            if not title or not company or len(description) < 30:
                continue
            modality = record.get('modality', 'remote')
            if modality not in ('remote', 'hybrid', 'onsite'):
                continue
            minimum, maximum = amount(record.get('salary_min')), amount(record.get('salary_max'))
            if maximum < minimum:
                continue
            contract_type = record.get('contract_type')
            if contract_type not in ('clt', 'pj', 'internship', 'temporary', 'apprentice', 'other'):
                contract_type = None
            identity = str(record.get('id') or hashlib.sha256(url.encode()).hexdigest())[:255]
            jobs.append(ExternalJob(identity, title, company, description,
                plain(record.get('location') or record.get('candidate_required_location') or 'Não informada', 160),
                modality, keywords, minimum, maximum, contract_type, url))
        except (FeedError, ValueError, TypeError):
            continue
    return jobs


def _xml_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1].casefold()


def _xml_value(node, *names) -> str:
    for child in node.iter():
        if _xml_name(child.tag) in names:
            value = child.attrib.get('href') or child.text
            if value and str(value).strip():
                return str(value).strip()
    return ''


def parse_rss(data: bytes, max_jobs: int = 200) -> list[ExternalJob]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        raise FeedError('O feed RSS/Atom retornou XML inválido.') from None
    jobs = []
    for node in root.iter():
        if _xml_name(node.tag) not in ('item', 'entry'):
            continue
        title = plain(_xml_value(node, 'title'), 160)
        company = plain(_xml_value(node, 'company', 'companyname', 'hiringorganization'), 160)
        description = plain(_xml_value(node, 'description', 'summary', 'content'), 30000)
        link = _xml_value(node, 'link', 'url')
        location = plain(_xml_value(node, 'location', 'joblocation'), 160)
        text = f'{title} {description} {location}'.casefold()
        modality = 'remote' if re.search(r'\b(remoto|remote|telecommute)\b', text) else 'hybrid' if re.search(r'\b(h[ií]brido|hybrid)\b', text) else 'onsite' if location else None
        tags = [plain(child.text, 80).casefold() for child in node.iter() if _xml_name(child.tag) in ('category', 'skill') and child.text]
        if not title or not company or len(description) < 30 or not modality or not link:
            continue
        try:
            url = public_https_url(link)
            identity = _xml_value(node, 'guid', 'id') or hashlib.sha256(url.encode()).hexdigest()
            jobs.append(ExternalJob(identity[:255], title, company, description, location or 'Não informada',
                modality, sorted(set(tags))[:100], 0, 0, None, url))
        except FeedError:
            continue
        if len(jobs) >= max_jobs:
            break
    return jobs


def _jsonld_values(document):
    value = json.loads(document)
    values = value if isinstance(value, list) else [value]
    expanded = []
    for item in values:
        if not isinstance(item, dict):
            continue
        graph = item.get('@graph')
        expanded.extend(graph if isinstance(graph, list) else [item])
    return expanded


def parse_job_postings(html: str, page_url: str, max_jobs: int = 200) -> list[ExternalJob]:
    parser = _JsonLd()
    parser.feed(html)
    jobs = []
    for document in parser.documents:
        try:
            records = _jsonld_values(document)
        except (json.JSONDecodeError, TypeError):
            continue
        for record in records:
            kind = record.get('@type', [])
            if 'JobPosting' not in (kind if isinstance(kind, list) else [kind]):
                continue
            organization = record.get('hiringOrganization') or {}
            if isinstance(organization, list):
                organization = organization[0] if organization else {}
            company = plain(organization.get('name') if isinstance(organization, dict) else '', 160)
            address = record.get('jobLocation') or {}
            if isinstance(address, list):
                address = address[0] if address else {}
            address = address.get('address', address) if isinstance(address, dict) else {}
            city = plain(address.get('addressLocality', ''), 80) if isinstance(address, dict) else ''
            state = plain(address.get('addressRegion', ''), 40) if isinstance(address, dict) else ''
            location = ', '.join(part for part in (city, state) if part) or 'Não informada'
            description = plain(record.get('description', ''), 30000)
            title = plain(record.get('title', ''), 160)
            link = record.get('url') or page_url
            text = f"{title} {description} {record.get('jobLocationType', '')}".casefold()
            modality = 'remote' if 'telecommute' in text or re.search(r'\b(remoto|remote)\b', text) else 'hybrid' if re.search(r'\b(h[ií]brido|hybrid)\b', text) else 'onsite' if city else None
            if not title or not company or len(description) < 30 or not modality:
                continue
            try:
                url = public_https_url(str(link))
                salary = record.get('baseSalary') or {}
                amount_value = salary.get('value', {}) if isinstance(salary, dict) else {}
                minimum = amount(amount_value.get('minValue')) if isinstance(amount_value, dict) else amount(amount_value)
                maximum = amount(amount_value.get('maxValue')) if isinstance(amount_value, dict) else minimum
                identity = str(record.get('identifier', {}).get('value') or url)[:255]
                contract = str(record.get('employmentType', '')).casefold()
                contract = {'full_time': 'clt', 'part_time': 'clt', 'contractor': 'pj',
                    'intern': 'internship', 'temporary': 'temporary'}.get(contract)
                tags = record.get('skills', [])
                tags = tags if isinstance(tags, list) else [tags] if tags else []
                jobs.append(ExternalJob(identity, title, company, description, location, modality,
                    sorted({plain(tag, 80).casefold() for tag in tags if plain(tag, 80)})[:100],
                    minimum, maximum, contract, url))
            except (FeedError, TypeError, ValueError):
                continue
            if len(jobs) >= max_jobs:
                return jobs
    return jobs


async def fetch_feed(url: str, allowed_hosts: list[str], max_bytes: int = 2 * 1024 * 1024, max_jobs: int = 200) -> list[ExternalJob]:
    approved_source(url, allowed_hosts)
    # Exact administrative host allowlist, no redirects, inherited proxy/TLS trust.
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False) as client:
        async with client.stream('GET', url, headers={'Accept': 'application/json', 'User-Agent': 'Vagou-AuthorizedFeed/1.0'}) as response:
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').lower()
            if not any(value in content_type for value in ('application/json', 'application/rss+xml', 'application/atom+xml', 'application/xml', 'text/xml', 'text/html')):
                raise FeedError('A fonte não respondeu com JSON, RSS, Atom ou HTML JobPosting.')
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise FeedError('A resposta da fonte excedeu o limite permitido.')
    try:
        if 'json' in content_type:
            return parse_feed(json.loads(body), max_jobs=max_jobs)
        if 'html' in content_type:
            return parse_job_postings(body.decode('utf-8'), url, max_jobs=max_jobs)
        return parse_rss(bytes(body), max_jobs=max_jobs)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise FeedError('A fonte respondeu com um documento inválido.') from None
