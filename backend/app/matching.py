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
}
_STOPWORDS = {'de', 'do', 'da', 'dos', 'das', 'em', 'e', 'the', 'of', 'and', 'a', 'o'}
_KNOWN_SKILLS = ('python', 'javascript', 'java', 'sql', 'postgresql', 'docker',
    'kubernetes', 'excel', 'sales', 'customer support', 'human resources', 'nodejs',
    'typescript', 'react', 'angular', 'flutter', 'dart', 'c#', 'c++', 'aws', 'azure')


def canonical_text(value: str) -> str:
    result = normalize(value)
    for phrase, canonical in sorted(_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', canonical, result)
    return ' '.join(result.split())


def text_contains(text: str, term: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(canonical_text(term)) + r'(?!\w)', canonical_text(text)))


def title_matches(title: str, requested: str) -> bool:
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
    return job_key == preferred_key or job_key.startswith(f'{preferred_key} ') or job_key.endswith(f' {preferred_key}')


def remote_region_allowed(job_location: str) -> bool:
    scope = normalize(job_location)
    if not scope or any(term in scope for term in ('worldwide', 'anywhere', 'global', 'qualquer lugar', 'todo o mundo', 'latin america', 'latam', 'south america', 'america latina', 'america do sul', 'americas')):
        return True
    if any(term in scope for term in ('brasil', 'brazil')):
        return True
    foreign_regions = ('united states', 'usa', 'u.s.', 'canada', 'europe', 'european',
        'united kingdom', 'uk ', 'australia', 'singapore', 'mexico', 'saudi arabia',
        'germany', 'france', 'spain', 'portugal', 'india', 'asia', 'africa')
    if any(term in scope for term in foreign_regions) or scope in {'uk', 'us', 'eu', 'ca'}:
        return False
    brazilian_locations = ('sao paulo', 'rio de janeiro', 'brasilia', 'goiania',
        'recife', 'salvador', 'belo horizonte', 'fortaleza', 'curitiba', 'porto alegre',
        'manaus', 'belem', 'vitoria', 'florianopolis', 'natal', 'joao pessoa', 'maceio',
        'aracaju', 'teresina', 'sao luis', 'palmas', 'cuiaba', 'campo grande', 'boa vista',
        'rio branco', 'porto velho', 'macapa', 'campinas', 'santos', 'niteroi',
        'acre', 'alagoas', 'amapa', 'amazonas', 'bahia', 'ceara', 'distrito federal',
        'espirito santo', 'goias', 'maranhao', 'mato grosso', 'minas gerais', 'para',
        'paraiba', 'parana', 'pernambuco', 'piaui', 'rio grande', 'rondonia', 'roraima',
        'santa catarina', 'sergipe', 'tocantins')
    return any(re.search(r'(?<!\w)' + re.escape(place) + r'(?!\w)', scope)
        for place in brazilian_locations)


def match(skills: list[str], required: list[str]) -> dict:
    available = {canonical_text(x) for x in skills}
    requirements = {canonical_text(x) for x in required if normalize(x)}
    missing = sorted(requirements - available)
    score = round(100 * len(requirements & available) / len(requirements)) if requirements else 0
    # Automation contract: >=70 submits, 40–69 are possible matches.
    category = 'high' if score >= 70 else 'observation' if score >= 40 else 'discarded'
    return {'match_score': score, 'category': category, 'missing_skills': missing}


def evaluate_job(job, skills: list[str], preferences: dict) -> dict:
    preferences = preferences or {}
    components = []
    reasons = []
    missed = []

    requirements = list(job.keywords or [])
    inferred = not requirements
    if inferred:
        searchable_skills = ' '.join([job.title, job.description])
        requirements = [skill for skill in _KNOWN_SKILLS if text_contains(searchable_skills, skill)]
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
    if titles:
        title_match = any(title_matches(job.title, title) for title in titles)
        components.append((0.20, 100 if title_match else 0))
        (reasons if title_match else missed).append(
            'Cargo compatível com sua busca.' if title_match else 'Cargo diferente dos títulos selecionados.')

    keywords = [canonical_text(value) for value in preferences.get('keywords', []) if normalize(value)]
    if keywords:
        searchable = canonical_text(' '.join([job.title, job.description, *(job.keywords or [])]))
        covered = sum(text_contains(searchable, keyword) for keyword in keywords)
        components.append((0.15, round(100 * covered / len(keywords))))
        (reasons if covered else missed).append(
            f'{covered}/{len(keywords)} palavras-chave encontradas.' if covered else 'Nenhuma palavra-chave selecionada foi encontrada.')

    locations = preferences.get('locations') or []
    if locations:
        location_match = any(location_matches(job.location, value) for value in locations)
        location_match = location_match or (job.modality == 'remote' and remote_region_allowed(job.location))
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

    total_weight = sum(weight for weight, _ in components)
    score = round(sum(weight * value for weight, value in components) / total_weight) if total_weight else 0
    if minimum and float(job.salary_max or 0) == 0:
        score = min(score, 69)  # Unknown remuneration cannot authorize a paid-range submission.
    if inferred:
        score = min(score, 69)  # An unconfirmed skill mention never auto-submits.
    incompatible = filter_reason(job, preferences)
    if incompatible:
        # High skill overlap never overrides an explicit location, modality,
        # salary, title, keyword or contract restriction chosen by the user.
        score = min(score, 69)
        if incompatible not in missed:
            missed.append(incompatible)
    category = 'strong' if score >= 70 else 'possible' if score >= 40 else 'discarded'
    return {'match_score': score, 'category': category, 'match_reasons': reasons, 'missed_reasons': missed}


def eligible(job, preferences: dict) -> bool:
    return filter_reason(job, preferences) is None


def filter_reason(job, preferences: dict) -> str | None:
    preferences = preferences or {}
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
        searchable = canonical_text(' '.join([job.title, job.description, *(job.keywords or [])]))
        if not any(text_contains(searchable, keyword) for keyword in keywords):
            return 'Palavras-chave não encontradas.'
    if preferences.get('locations'):
        location_match = any(location_matches(job.location, value) for value in preferences['locations'])
        location_match = location_match or (job.modality == 'remote' and remote_region_allowed(job.location))
        if not location_match:
            return 'Localização fora da região selecionada.'
    return None
