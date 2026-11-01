"""Deterministic, explainable matching; no inferred skills from untrusted PDF text."""
import re
import unicodedata


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).strip()


# Exact vocabulary aliases, not substrings: Java remains distinct from JavaScript.
_ALIASES = {
    'engenheiro de software': 'developer', 'software engineer': 'developer',
    'software developer': 'developer', 'desenvolvedor de software': 'developer',
    'desenvolvedor': 'developer', 'desenvolvedora': 'developer', 'programador': 'developer',
    'programadora': 'developer', 'analista de dados': 'data analyst',
    'cientista de dados': 'data scientist', 'engenheiro de dados': 'data engineer',
    'analista': 'analyst', 'dados': 'data', 'desenvolvimento': 'development',
    'atendimento ao cliente': 'customer support', 'customer service': 'customer support',
    'suporte ao cliente': 'customer support', 'atendimento': 'customer support',
    'recursos humanos': 'human resources', 'gestao de projetos': 'project management',
    'gestao': 'management', 'vendas': 'sales', 'vendedor': 'sales',
    'gerente': 'manager', 'administrativo': 'administrative', 'assistente': 'assistant',
    'programacao em python': 'python', 'programacao python': 'python',
    'js': 'javascript', 'node.js': 'nodejs', 'node js': 'nodejs',
    'postgres': 'postgresql', 'k8s': 'kubernetes', 'planilhas': 'excel',
    'suporte tecnico': 'technical support', 'suporte de ti': 'technical support',
    'suporte em ti': 'technical support', 'it support': 'technical support',
    'suporte': 'technical support', 'helpdesk': 'help desk',
    'tecnico de informatica': 'computer technician', 'tecnico em informatica': 'computer technician',
    'informatica': 'information technology', 'tecnologia da informacao': 'information technology',
    'infraestrutura': 'infrastructure', 'redes': 'networking', 'sistemas': 'systems',
}
_STOPWORDS = {'de', 'do', 'da', 'dos', 'das', 'em', 'e', 'the', 'of', 'and', 'a', 'o'}
_KNOWN_SKILLS = ('python', 'javascript', 'java', 'sql', 'postgresql', 'docker',
    'kubernetes', 'excel', 'sales', 'customer support', 'human resources', 'nodejs',
    'typescript', 'react', 'angular', 'flutter', 'dart', 'c#', 'c++', 'aws', 'azure',
    'technical support', 'service desk', 'help desk', 'networking', 'infrastructure',
    'windows', 'linux', 'active directory', 'tcp/ip', 'hardware', 'office 365',
    'information technology', 'systems')

_BRAZIL_STATES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas',
    'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo',
    'GO': 'Goiás', 'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul',
    'MG': 'Minas Gerais', 'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná',
    'PE': 'Pernambuco', 'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina',
    'SP': 'São Paulo', 'SE': 'Sergipe', 'TO': 'Tocantins',
}
_STATE_BY_NAME = {normalize(name): code for code, name in _BRAZIL_STATES.items()}
_STATE_BY_NAME['federal district'] = 'DF'
_CITY_STATES = {
    'rio branco': 'AC', 'maceio': 'AL', 'macapa': 'AP', 'manaus': 'AM',
    'salvador': 'BA', 'fortaleza': 'CE', 'brasilia': 'DF', 'vitoria': 'ES',
    'goiania': 'GO', 'sao luis': 'MA', 'cuiaba': 'MT', 'campo grande': 'MS',
    'belo horizonte': 'MG', 'belem': 'PA', 'joao pessoa': 'PB', 'curitiba': 'PR',
    'recife': 'PE', 'teresina': 'PI', 'rio de janeiro': 'RJ', 'natal': 'RN',
    'porto alegre': 'RS', 'porto velho': 'RO', 'boa vista': 'RR',
    'florianopolis': 'SC', 'sao paulo': 'SP', 'aracaju': 'SE', 'palmas': 'TO',
    'campinas': 'SP', 'santos': 'SP', 'sorocaba': 'SP', 'ribeirao preto': 'SP',
    'guarulhos': 'SP', 'sao bernardo do campo': 'SP', 'santo andre': 'SP', 'franca': 'SP',
    'niteroi': 'RJ', 'duque de caxias': 'RJ', 'joinville': 'SC', 'blumenau': 'SC',
    'londrina': 'PR', 'maringa': 'PR', 'uberlandia': 'MG', 'contagem': 'MG',
    'anapolis': 'GO', 'aparecida de goiania': 'GO', 'luziania': 'GO',
    'valparaiso de goias': 'GO', 'aguas lindas de goias': 'GO', 'novo gama': 'GO',
    'cidade ocidental': 'GO', 'santo antonio do descoberto': 'GO', 'formosa': 'GO',
    'aguas claras': 'DF', 'ceilandia': 'DF', 'taguatinga': 'DF', 'samambaia': 'DF',
    'gama': 'DF', 'guara': 'DF', 'sobradinho': 'DF',
}
_FOREIGN_LOCATION = re.compile(
    r'\b(?:germany|deutschland|alemanha|munich|munchen|bavaria|berlin|europe|european|'
    r'united states|usa|u\.s\.|united kingdom|uk|canada|australia|singapore|mexico|'
    r'saudi arabia|france|spain|espanha|portugal|india|asia|africa|'
    r'new york|london|lisbon|amsterdam|netherlands|switzerland|zurich)\b'
)


def dedupe_reasons(values: list[str]) -> list[str]:
    """Keep original readable wording while removing repeated explanations."""
    seen = set()
    result = []
    for value in values:
        text = ' '.join(str(value or '').split()).strip(' ;')
        key = normalize(text).rstrip('.;')
        if key and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _state_code(value: str) -> str | None:
    cleaned = str(value or '').strip()
    if cleaned.upper().startswith('BR-'):
        cleaned = cleaned[3:]
    if cleaned.upper() in _BRAZIL_STATES:
        return cleaned.upper()
    return _STATE_BY_NAME.get(normalize(cleaned))


def brazil_state_name(uf: str) -> str | None:
    """Return the official state label for an observed Brazilian UF/name."""
    code = _state_code(uf)
    return _BRAZIL_STATES.get(code) if code else None


def job_location_details(job) -> dict:
    """Normalize observed geography; never invent an unknown city or country.

    An explicit foreign country overrides a coincidentally Brazilian city name.
    Worldwide/Latin-America labels alone do not prove a Brazil-only vacancy.
    """
    location = str(getattr(job, 'location', '') or '').strip()
    location = re.sub(r'\(([A-Za-z]{2})\)',
        lambda found: '/ ' + found[1].upper() if found[1].upper() in _BRAZIL_STATES else found[0], location)
    raw_country = str(getattr(job, 'country', '') or '').strip()
    country = normalize(raw_country)
    foreign_country = bool(country and country not in {'br', 'brasil', 'brazil', 'bra'})
    explicit_brazil = country in {'br', 'brasil', 'brazil', 'bra'} or bool(
        re.search(r'\b(?:brasil|brazil)\b', normalize(location)))
    parts = [part.strip() for part in re.split(r'\s*[/,|–—]\s*|\s+-\s+', location) if part.strip()]
    raw_city = str(getattr(job, 'city', '') or '').strip()
    city = raw_city or (parts[0] if parts else '')
    if normalize(city) in {'brasil', 'brazil', 'remote', 'remoto', 'remoto brasil',
                           'remote brazil', 'home office', 'nao informada', 'worldwide', 'latin america'}:
        city = ''
    state = _state_code(getattr(job, 'state', '') or '')
    for part in parts[1:]:
        state = state or _state_code(part)
    city_key = normalize(city)
    # The Distrito Federal is frequently published as Brasília/DF or Brasília - DF.
    suffix = re.search(r'^(.*?)\s*(?:[-/]\s*|\s+)([A-Z]{2})$', city, re.IGNORECASE)
    if suffix and suffix[2].upper() in _BRAZIL_STATES:
        city, city_key = suffix[1].strip(), normalize(suffix[1])
        state = state or suffix[2].upper()
    known_city_state = _CITY_STATES.get(city_key)
    state = state or known_city_state
    # Full state-only listings are useful but do not establish a city.
    if not state and normalize(location) in _STATE_BY_NAME:
        state = _STATE_BY_NAME[normalize(location)]
        city = ''
    elif not parts[1:] and _state_code(city) and not known_city_state:
        state = _state_code(city)
        city = ''
    foreign_location = bool(_FOREIGN_LOCATION.search(normalize(location)))
    # Ambiguous US state abbreviations require Brazil provenance or a known city.
    ambiguous_state = state in {'AL', 'MA', 'MS', 'MT', 'PA', 'PR', 'SC'}
    structured_state = bool(state and city and (not ambiguous_state or explicit_brazil or known_city_state))
    brazilian = not foreign_country and not foreign_location and bool(
        explicit_brazil or known_city_state or structured_state or normalize(location) in _STATE_BY_NAME)
    return {'city': city or None, 'state': state, 'is_brazilian': brazilian,
            'is_remote': getattr(job, 'modality', None) == 'remote'}


def is_brazilian_job(job) -> bool:
    return job_location_details(job)['is_brazilian']


def _support_role(value: str):
    text = normalize(value)
    if re.search(r'\b(?:service\s*desk|help\s*desk|helpdesk)\b', text):
        return 'service_desk', None
    if re.search(r'\b(?:infraestrutura|infrastructure|redes|network|networking)\b', text):
        return 'infrastructure', None
    if re.search(r'\b(?:auxiliar|assistente)\b.*\b(?:ti|informatica|tecnologia)\b', text):
        return 'assistant_it', None
    if re.search(r'\b(?:tecnico|technician)\b.*\b(?:informatica|computer|ti)\b', text):
        return 'computer_technician', None
    if re.search(r'\b(?:suporte|technical support|it support|noc)\b', text):
        level = re.search(r'\b(?:n|nivel|level|tier)\s*([123])\b', text)
        return 'support', level[1] if level else None
    if re.search(r'\banalista\b.*\bsistemas\b', text):
        return 'systems', None
    return None


def related_title(title: str, requested: str) -> bool:
    return bool(_support_role(title) and _support_role(requested))


def canonical_text(value: str) -> str:
    result = normalize(value)
    for phrase, canonical in sorted(_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', canonical, result)
    return ' '.join(result.split())


def text_contains(text: str, term: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(canonical_text(term)) + r'(?!\w)', canonical_text(text)))


def advertised_skills(requirements_text: str) -> list[str]:
    """Extract only vocabulary literally present in an advertised requirement.

    Callers must supply the provider's requirement text, never candidate data.
    This is lexical extraction, not a claim of qualifications absent in the ad.
    """
    return [skill for skill in _KNOWN_SKILLS if text_contains(requirements_text, skill)]


def title_matches(title: str, requested: str) -> bool:
    actual_role, requested_role = _support_role(title), _support_role(requested)
    if actual_role and requested_role:
        if actual_role[0] != requested_role[0]:
            return False
        if actual_role[1] and requested_role[1] and actual_role[1] != requested_role[1]:
            return False
    wanted = [token for token in canonical_text(requested).split() if token not in _STOPWORDS]
    actual = canonical_text(title)
    return bool(wanted) and all(text_contains(actual, token) for token in wanted)


def english_search_query(preferences: dict) -> str:
    values = [*(preferences.get('keywords') or []), *(preferences.get('titles') or [])]
    for value in values:
        for skill in _KNOWN_SKILLS:
            if text_contains(value, skill):
                return skill
    return canonical_text(str(values[0]))[:100] if values else ''


def location_key(value: str) -> str:
    return ' '.join(normalize(value.replace('/', ' ').replace(',', ' ').replace('-', ' ')).split())


def location_matches(job_location: str, preferred_location: str) -> bool:
    job_key, preferred_key = location_key(job_location), location_key(preferred_location)
    if job_key == preferred_key or job_key.startswith(f'{preferred_key} ') or job_key.endswith(f' {preferred_key}'):
        return True
    from types import SimpleNamespace
    actual = job_location_details(SimpleNamespace(location=job_location))
    preferred = job_location_details(SimpleNamespace(location=preferred_location))
    if not actual['is_brazilian'] or not preferred['is_brazilian']:
        return False
    return bool(actual['city'] and preferred['city'] and
                normalize(actual['city']) == normalize(preferred['city']) and
                (not actual['state'] or not preferred['state'] or actual['state'] == preferred['state']))


def remote_region_allowed(job_location: str) -> bool:
    from types import SimpleNamespace
    return is_brazilian_job(SimpleNamespace(location=job_location, modality='remote'))


def compatible_region(job, preferences: dict) -> bool:
    """Whether a verified Brazilian vacancy belongs to a requested region."""
    if not is_brazilian_job(job):
        return False
    locations = (preferences or {}).get('locations') or []
    if not locations:
        return True
    if getattr(job, 'modality', None) == 'remote':
        return True
    details = job_location_details(job)
    observed = ' / '.join(part for part in (details['city'], details['state']) if part)
    return any(location_matches(observed or job.location, location) for location in locations)


def _keyword_coverage(job, keywords: list[str]) -> int:
    searchable = canonical_text(' '.join([job.title, job.description, *(job.keywords or [])]))
    technical_role = bool(_support_role(job.title))
    broad_technical = {'tecnologia', 'ti', 'technology', 'information technology', 'technical support'}
    return sum(text_contains(searchable, keyword) or
               (technical_role and canonical_text(keyword) in broad_technical)
               for keyword in keywords)


def match(skills: list[str], required: list[str]) -> dict:
    available = {canonical_text(x) for x in skills}
    # A declared support specialization includes its core support competency.
    # Expand only the candidate's explicit skill labels: a generic support
    # declaration must not satisfy an employer's specific N2/NOC requirement.
    for skill in tuple(available):
        if re.fullmatch(r'technical support (?:(?:n|nivel|level|tier)\s*[123]|noc)', skill):
            available.add('technical support')
    requirements = {canonical_text(x) for x in required if normalize(x)}
    missing = sorted(requirements - available)
    score = round(100 * len(requirements & available) / len(requirements)) if requirements else 0
    # Automation contract: >=70 submits, 40–69 are possible matches.
    category = 'high' if score >= 70 else 'observation' if score >= 40 else 'discarded'
    return {'match_score': score, 'category': category, 'missing_skills': missing}


def evaluate_job(job, skills: list[str], preferences: dict) -> dict:
    preferences = preferences or {}
    if not is_brazilian_job(job):
        return {'match_score': 0, 'category': 'discarded', 'match_reasons': [],
                'missed_reasons': ['A vaga não possui localização brasileira confirmada.']}
    components = []
    reasons = []
    missed = []

    requirements = list(job.keywords or [])
    inferred = not requirements
    if inferred:
        searchable_skills = ' '.join([job.title, job.description])
        requirements = advertised_skills(searchable_skills)
    skill_match = match(skills, requirements)
    if requirements:
        components.append((0.35, skill_match['match_score']))
        if skill_match['match_score'] == 100:
            reasons.append('Competências compatíveis com os requisitos da vaga.')
        elif skill_match['match_score']:
            reasons.append(f"{skill_match['match_score']}% das competências da vaga coincidem.")
            missed.append('Competências pendentes: ' + ', '.join(skill_match['missing_skills'][:5]))
        else:
            missed.append('Poucas competências coincidem com os requisitos da vaga.')
    else:
        components.append((0.35, 0))
        missed.append('A fonte não informou competências suficientes para confirmar o match.')
    if inferred:
        missed.append('Competências inferidas do texto; confirme os requisitos no anúncio oficial.')

    titles = preferences.get('titles') or []
    adjacent_role = False
    if titles:
        title_match = any(title_matches(job.title, title) for title in titles)
        adjacent_role = not title_match and any(related_title(job.title, title) for title in titles)
        components.append((0.20, 100 if title_match else 60 if adjacent_role else 0))
        if title_match:
            reasons.append('Cargo compatível com sua busca.')
        elif adjacent_role:
            reasons.append('Cargo da mesma área de suporte e tecnologia; avalie as atribuições e o nível.')
        else:
            missed.append('Cargo diferente dos títulos selecionados.')

    keywords = [canonical_text(value) for value in preferences.get('keywords', []) if normalize(value)]
    if keywords:
        covered = _keyword_coverage(job, keywords)
        components.append((0.15, round(100 * covered / len(keywords))))
        (reasons if covered else missed).append(
            f'{covered}/{len(keywords)} palavras-chave encontradas.' if covered else 'Nenhuma palavra-chave selecionada foi encontrada.')

    locations = preferences.get('locations') or []
    if locations:
        location_match = compatible_region(job, preferences)
        components.append((0.10, 100 if location_match else 0))
        (reasons if location_match else missed).append(
            'Localização compatível.' if location_match else 'Vaga fora da Cidade/UF selecionada.')

    modalities = preferences.get('modalities') or []
    if modalities:
        modality_match = job.modality in modalities
        components.append((0.05, 100 if modality_match else 0))
        (reasons if modality_match else missed).append(
            'Modalidade compatível.' if modality_match else 'Modalidade diferente da selecionada.')

    minimum = float(preferences.get('min_salary') or 0)
    if minimum:
        salary_max = float(job.salary_max or 0)
        salary_score = 100 if salary_max >= minimum else 50 if salary_max == 0 else 0
        components.append((0.10, salary_score))
        (reasons if salary_score == 100 else missed).append(
            'Faixa salarial atende ao piso.' if salary_score == 100 else
            'Faixa salarial não informada.' if salary_score == 50 else 'Faixa salarial abaixo do piso.')

    contracts = preferences.get('contract_types') or []
    if contracts:
        contract = getattr(job, 'contract_type', None)
        contract_score = 100 if contract in contracts else 50 if contract is None else 0
        components.append((0.05, contract_score))
        (reasons if contract_score == 100 else missed).append(
            'Tipo de contrato compatível.' if contract_score == 100 else
            'Tipo de contrato não informado.' if contract_score == 50 else 'Tipo de contrato diferente do selecionado.')

    # Geography, salary and modality cannot establish professional relevance.
    semantic_title = any(title_matches(job.title, title) or related_title(job.title, title) for title in titles)
    technical_terms = ('python', 'sql', 'windows', 'linux', 'networking', 'infrastructure',
                       'hardware', 'active directory', 'tcp/ip', 'noc', 'service desk', 'help desk')
    advertised = canonical_text(' '.join([job.title, job.description, *(job.keywords or [])]))
    sought_support = any(_support_role(title) for title in titles) or any(
        _support_role(value) or canonical_text(value) in {'ti', 'tecnologia', 'information technology'} for value in preferences.get('keywords', []))
    technical_overlap = any(text_contains(advertised, term) and any(
        text_contains(value, term) for value in [*skills, *preferences.get('keywords', [])]) for term in technical_terms)
    keyword_overlap = bool(keywords and _keyword_coverage(job, keywords))
    relevant = semantic_title or technical_overlap or (keyword_overlap and not sought_support) or (not titles and not keywords and skill_match['match_score'] > 0)
    if sought_support and not (_support_role(job.title) or technical_overlap):
        relevant = False
    if not relevant:
        return {'match_score': 0, 'category': 'discarded', 'match_reasons': [],
                'missed_reasons': ['A área profissional da vaga não corresponde ao perfil buscado.']}

    total_weight = sum(weight for weight, _ in components)
    score = round(sum(weight * value for weight, value in components) / total_weight) if total_weight else 0
    if minimum and float(job.salary_max or 0) == 0:
        score = min(score, 69)  # Unknown remuneration cannot authorize a paid-range submission.
    if inferred:
        score = min(score, 69)  # An unconfirmed skill mention never auto-submits.
    if adjacent_role:
        score = min(score, 69)  # Related roles remain an individual decision.
    incompatible = filter_reason(job, preferences)
    if incompatible:
        # High skill overlap never overrides an explicit location, modality,
        # salary, title, keyword or contract restriction chosen by the user.
        score = min(score, 69)
        if incompatible not in missed:
            missed.append(incompatible)
    category = 'strong' if score >= 70 else 'possible' if score >= 40 else 'discarded'
    return {'match_score': score, 'category': category, 'match_reasons': dedupe_reasons(reasons),
            'missed_reasons': dedupe_reasons(missed)}


def eligible(job, preferences: dict) -> bool:
    return filter_reason(job, preferences) is None


def filter_reason(job, preferences: dict) -> str | None:
    preferences = preferences or {}
    if not is_brazilian_job(job):
        return 'A vaga não possui localização brasileira confirmada.'
    if float(job.salary_max or 0) > 0 and float(job.salary_max) < preferences.get('min_salary', 0):
        return 'Salário abaixo do piso definido.'
    if preferences.get('max_salary') is not None and float(getattr(job, 'salary_min', 0) or 0) > preferences['max_salary']:
        return 'Salário acima do teto definido.'
    if preferences.get('modalities') and job.modality not in preferences['modalities']:
        return 'Modalidade não selecionada.'
    if preferences.get('titles') and not any(title_matches(job.title, t) for t in preferences['titles']):
        return 'Cargo fora dos títulos desejados.'
    contract_types = preferences.get('contract_types') or []
    if contract_types and getattr(job, 'contract_type', None) not in contract_types:
        return 'Tipo de contrato não selecionado.'
    keywords = [canonical_text(value) for value in preferences.get('keywords', []) if normalize(value)]
    if keywords:
        if not _keyword_coverage(job, keywords):
            return 'Palavras-chave não encontradas.'
    if preferences.get('locations'):
        if not compatible_region(job, preferences):
            return 'Localização fora da região selecionada.'
    return None
