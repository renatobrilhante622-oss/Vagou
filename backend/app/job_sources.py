"""Bounded ingestion of explicitly configured public/authorized job feeds.

Supported formats are JSON `{jobs: [...]}`, RSS/Atom, and schema.org JobPosting
JSON-LD. This module never sends candidate data or submits to external websites.
Configure only sources whose terms permit reuse.
"""
from email_validator import EmailNotValidError, validate_email

import hashlib
import ipaddress
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html import unescape
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
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag.casefold() in {'script', 'style', 'noscript'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.casefold() in {'script', 'style', 'noscript'} and self.hidden:
            self.hidden -= 1

    def handle_data(self, value):
        if not self.hidden:
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
    parser.feed(unescape(str(value or '')))
    return ' '.join(' '.join(parser.parts).split())[:maximum]


def clean_description(value, maximum: int = 30000) -> str:
    """Normalize published vacancy prose without exposing scripts or guessing facts."""
    text = plain(value, maximum)
    return re.sub(r':(?=[A-Za-zÀ-ÿ])', ': ', text).strip()


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


def contact_email(value) -> str | None:
    """Only provider-declared public recruitment contacts, never scraped addresses."""
    if not isinstance(value, str):
        return None
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def _normalized(value) -> str:
    return ''.join(character for character in unicodedata.normalize('NFKD', str(value or '').casefold())
                   if not unicodedata.combining(character)).strip()


BRAZILIAN_STATES = {
    'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA',
    'ceara': 'CE', 'distrito federal': 'DF', 'espirito santo': 'ES', 'goias': 'GO',
    'maranhao': 'MA', 'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG',
    'para': 'PA', 'paraiba': 'PB', 'parana': 'PR', 'pernambuco': 'PE', 'piaui': 'PI',
    'rio de janeiro': 'RJ', 'rio grande do norte': 'RN', 'rio grande do sul': 'RS',
    'rondonia': 'RO', 'roraima': 'RR', 'santa catarina': 'SC', 'sao paulo': 'SP',
    'sergipe': 'SE', 'tocantins': 'TO',
}


def state_code(value) -> str | None:
    normalized = _normalized(value)
    upper = normalized.upper()
    return upper if upper in BRAZILIAN_STATES.values() else BRAZILIAN_STATES.get(normalized)


def country_code(value) -> str | None:
    if isinstance(value, dict):
        value = value.get('name') or value.get('identifier') or value.get('value')
    normalized = _normalized(value)
    if not normalized:
        return None
    if len(normalized) == 2 and normalized.isalpha():
        return 'GB' if normalized == 'uk' else normalized.upper()
    known = {'brasil': 'BR', 'brazil': 'BR', 'germany': 'DE', 'alemanha': 'DE',
        'united states': 'US', 'estados unidos': 'US', 'usa': 'US', 'canada': 'CA',
        'united kingdom': 'GB', 'reino unido': 'GB', 'portugal': 'PT', 'france': 'FR',
        'franca': 'FR', 'spain': 'ES', 'espanha': 'ES', 'argentina': 'AR',
        'chile': 'CL', 'colombia': 'CO', 'mexico': 'MX', 'peru': 'PE',
        'australia': 'AU', 'india': 'IN', 'netherlands': 'NL', 'holanda': 'NL'}
    # ZZ preserves the fact an explicit, unrecognized country was supplied;
    # it must never be silently treated as Brazil merely because a city matches.
    return known.get(normalized, 'ZZ')


def recruitment_contact(record: dict, description: str = '') -> str | None:
    """Read an announced hiring contact, excluding ambient/legal/support mail."""
    for key in ('contact_email', 'recruiter_email', 'email'):
        address = contact_email(record.get(key))
        if address:
            return address
    application = record.get('applicationContact') or {}
    for entry in application if isinstance(application, list) else [application]:
        address = contact_email(entry.get('email') if isinstance(entry, dict) else entry)
        if address:
            return address
    recruitment = re.compile(r'\b(?:rh|recrutamento|recruitment|recruiting|careers|hiring|selecao|curriculo|curriculos|vagas|talentos|dp|candidatura|candidaturas)\b')
    organization = record.get('hiringOrganization') or {}
    points = record.get('contactPoint') or (organization.get('contactPoint') if isinstance(organization, dict) else None) or []
    for point in points if isinstance(points, list) else [points]:
        if isinstance(point, dict) and recruitment.search(_normalized(point.get('contactType') or point.get('name'))):
            address = contact_email(point.get('email'))
            if address:
                return address
    text = plain(description, 30000)
    for found in list(re.finditer(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))[:20]:
        address = contact_email(found.group().strip('.,;:'))
        if not address:
            continue
        local = _normalized(address.split('@', 1)[0])
        if re.search(r'(?:^|[._-])(?:suporte|support|sac|privacidade|privacy|dpo|noreply|no-reply|comercial|marketing|ouvidoria)(?:$|[._-])', local):
            continue
        context = _normalized(text[max(0, found.start() - 110):min(len(text), found.end() + 60)])
        if recruitment.search(context):
            return address
    return None


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
    contact_email: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None

    expires_at: datetime | None = None

    def values(self):
        return asdict(self)


def _record_location(record: dict) -> tuple[str, str | None, str | None, str | None]:
    value = record.get('location') or record.get('candidate_required_location')
    address = value.get('address', value) if isinstance(value, dict) else {}
    address = address if isinstance(address, dict) else {}
    city = plain(record.get('city') or address.get('addressLocality') or address.get('city'), 80) or None
    state = state_code(record.get('state') or address.get('addressRegion') or address.get('state'))
    country = country_code(record.get('country') or address.get('addressCountry') or address.get('country'))
    location = plain(value, 160) if isinstance(value, str) else ''
    if city and state:
        location = f'{city}, {state}'
    if not location:
        location = ', '.join(part for part in (city, state, country) if part) or 'Não informada'
    return location, city, state, country


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
            modality = {'remoto': 'remote', 'presencial': 'onsite', 'hibrido': 'hybrid'}.get(
                _normalized(record.get('modality')), record.get('modality', 'remote'))
            if modality not in ('remote', 'hybrid', 'onsite'):
                continue
            minimum, maximum = amount(record.get('salary_min')), amount(record.get('salary_max'))
            if record.get('currency') or record.get('salary_currency'):
                if str(record.get('currency') or record.get('salary_currency')).upper() != 'BRL':
                    minimum = maximum = 0.0
            if maximum < minimum:
                continue
            contract_type = record.get('contract_type')
            if contract_type not in ('clt', 'pj', 'internship', 'temporary', 'apprentice', 'other'):
                contract_type = None
            identity = str(record.get('id') or hashlib.sha256(url.encode()).hexdigest())[:255]
            location, city, state, country = _record_location(record)
            jobs.append(ExternalJob(identity, title, company, description,
                location, modality, keywords, minimum, maximum, contract_type, url,
                recruitment_contact(record, record.get('description', '')), city, state, country))
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
            metadata = {'location': location, 'city': _xml_value(node, 'city'),
                        'state': _xml_value(node, 'state'), 'country': _xml_value(node, 'country'),
                        'contact_email': _xml_value(node, 'contact_email', 'recruiter_email', 'email')}
            location, city, state, country = _record_location(metadata)
            jobs.append(ExternalJob(identity[:255], title, company, description, location,
                modality, sorted(set(tags))[:100], 0, 0, None, url,
                recruitment_contact(metadata, description), city, state, country))
        except FeedError:
            continue
        if len(jobs) >= max_jobs:
            break
    return jobs


def _jsonld_values(document):
    # Some public JobPosting publishers put literal CR/LF inside descriptions.
    # This tolerates those characters, without executing scripts or relaxing URL,
    # field-size, country, contact and salary validation below.
    try:
        value = json.loads(document, strict=False)
    except json.JSONDecodeError:
        # Gupy career pages sometimes entity-encode the entire JSON object.
        # Decode that wrapper once, only after normal JSON failed. Valid JSON
        # containing entity-escaped HTML/quotes in a description stays intact.
        if not re.match(r'^\s*[\[{]\s*(?:&quot;|&#34;|&#x22;)', document, re.IGNORECASE):
            raise
        value = json.loads(unescape(document), strict=False)
    values = value if isinstance(value, list) else [value]
    expanded = []
    for item in values:
        if not isinstance(item, dict):
            continue
        graph = item.get('@graph')
        expanded.extend(graph if isinstance(graph, list) else [item])
    return expanded


def posting_expiration(record: dict) -> datetime | None:
    value = record.get('validThrough') or record.get('expires_at')
    if not isinstance(value, str) or not value.strip(): return None
    try:
        expiration = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if len(value.strip()) == 10:
            expiration = expiration.replace(hour=23, minute=59, second=59)
        return expiration.replace(tzinfo=timezone.utc) if expiration.tzinfo is None else expiration
    except ValueError: return None


def _posting_expired(record: dict) -> bool:
    value = record.get('validThrough')
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        if len(value.strip()) == 10:
            return date.fromisoformat(value.strip()) < datetime.now(timezone.utc).date()
        expiration = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        return expiration <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _posting_modality(record: dict, description: str, has_city: bool) -> str | None:
    declared = _normalized(record.get('jobLocationType') or record.get('workplaceType') or record.get('modality'))
    mapping = {'onsite': 'onsite', 'on-site': 'onsite', 'on_site': 'onsite',
               'presencial': 'onsite', 'hybrid': 'hybrid', 'hibrido': 'hybrid',
               'remote': 'remote', 'remoto': 'remote', 'telecommute': 'remote'}
    if declared in mapping:
        return mapping[declared]
    locations = record.get('jobLocation') or {}
    if isinstance(locations, list):
        brazilian = [item for item in locations if isinstance(item, dict) and
            country_code(_schema_address(item).get('addressCountry')) == 'BR']
        locations = brazilian[0] if brazilian else locations[0] if locations else {}
    properties = (locations.get('additionalProperty') or []) if isinstance(locations, dict) else []
    for item in properties if isinstance(properties, list) else [properties]:
        if isinstance(item, dict):
            nested = _normalized(item.get('value'))
            if nested in mapping:
                return mapping[nested]
    header = re.search(r'(?:modalidade|modelo de trabalho|regime de trabalho)\s*[:\-]?\s*(remoto|hibrido|presencial|home office)', _normalized(description))
    if header:
        return {'remoto': 'remote', 'home office': 'remote', 'hibrido': 'hybrid', 'presencial': 'onsite'}[header.group(1)]
    # "Prestar suporte remoto" is a duty, not evidence that a role is remote.
    if re.search(r'\b100\s*%\s*remoto\b', _normalized(description)):
        return 'remote'
    return 'onsite' if has_city else None


def _applicant_countries(record: dict) -> set[str]:
    requirements = record.get('applicantLocationRequirements') or []
    countries = set()
    for item in requirements if isinstance(requirements, list) else [requirements]:
        if isinstance(item, dict):
            value = item.get('addressCountry') or item.get('name')
            if isinstance(item.get('address'), dict):
                value = item['address'].get('addressCountry') or value
        else:
            value = item
        code = country_code(value)
        if code:
            countries.add(code)
    return countries


def _posting_contract(record: dict, description: str) -> str | None:
    declared = _normalized(record.get('contract_type') or record.get('employmentType'))
    mapping = {'clt': 'clt', 'pj': 'pj', 'intern': 'internship', 'internship': 'internship',
               'estagio': 'internship', 'temporary': 'temporary', 'temporario': 'temporary',
               'apprentice': 'apprentice', 'aprendiz': 'apprentice'}
    if declared in mapping:
        return mapping[declared]
    explicit = re.search(r'(?:contratacao|contrato|regime|vinculo)\s*(?:de\s+)?(?:trabalho\s*)?[:\-]?\s*(clt|pj)\b', _normalized(description))
    # FULL_TIME/CONTRACTOR do not establish Brazilian CLT/PJ legal status.
    return explicit.group(1) if explicit else None


def _schema_address(value) -> dict:
    if not isinstance(value, dict):
        return {}
    address = value.get('address', value)
    return address if isinstance(address, dict) else {}


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
            if _posting_expired(record):
                continue
            organization = record.get('hiringOrganization') or {}
            if isinstance(organization, list):
                organization = organization[0] if organization else {}
            company = plain(organization.get('name') if isinstance(organization, dict) else '', 160)
            address = record.get('jobLocation') or {}
            if isinstance(address, list):
                brazilian = [item for item in address if isinstance(item, dict) and
                    country_code(_schema_address(item).get('addressCountry')) == 'BR']
                address = brazilian[0] if brazilian else address[0] if address else {}
            address = _schema_address(address)
            city = plain(address.get('addressLocality', ''), 80) if isinstance(address, dict) else ''
            raw_state = plain(address.get('addressRegion', ''), 40)
            state = state_code(raw_state)
            country = country_code(address.get('addressCountry'))
            location = ', '.join(part for part in (city, state or raw_state) if part) or 'Não informada'
            description = plain(record.get('description', ''), 30000)
            title = plain(record.get('title', ''), 160)
            link = record.get('url') or page_url
            modality = _posting_modality(record, description, bool(city))
            if modality == 'remote' and 'BR' in _applicant_countries(record):
                if country != 'BR':
                    city = state = None
                    location = 'Remoto Brasil'
                country = 'BR'
            if modality == 'remote' and country == 'BR' and not city:
                location = 'Remoto Brasil'
            if not title or not company or len(description) < 30 or not modality:
                continue
            try:
                url = public_https_url(str(link))
                salary = record.get('baseSalary') or {}
                amount_value = salary.get('value', {}) if isinstance(salary, dict) else {}
                minimum = amount(amount_value.get('minValue', amount_value.get('value'))) if isinstance(amount_value, dict) else amount(amount_value)
                maximum = amount(amount_value.get('maxValue', amount_value.get('value'))) if isinstance(amount_value, dict) else minimum
                if isinstance(salary, dict) and salary.get('currency') and str(salary['currency']).upper() != 'BRL':
                    minimum = maximum = 0.0
                if maximum < minimum:
                    minimum = maximum = 0.0
                identifier = record.get('identifier') or {}
                identity = str((identifier.get('value') if isinstance(identifier, dict) else identifier) or url)[:255]
                contract = _posting_contract(record, description)
                tags = record.get('skills', [])
                tags = tags if isinstance(tags, list) else [tags] if tags else []
                jobs.append(ExternalJob(identity, title, company, description, location, modality,
                    sorted({plain(tag, 80).casefold() for tag in tags if plain(tag, 80)})[:100],
                    minimum, maximum, contract, url, recruitment_contact(record, record.get('description', '')),
                    city or None, state, country, posting_expiration(record)))
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
