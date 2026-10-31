"""Deterministic, explainable matching; no inferred skills from untrusted PDF text."""
import unicodedata


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).strip()


def location_key(value: str) -> str:
    return ' '.join(normalize(value.replace('/', ' ').replace(',', ' ').replace('-', ' ')).split())


def location_matches(job_location: str, preferred_location: str) -> bool:
    job_key, preferred_key = location_key(job_location), location_key(preferred_location)
    return job_key == preferred_key or job_key.startswith(f'{preferred_key} ') or job_key.endswith(f' {preferred_key}')


def match(skills: list[str], required: list[str]) -> dict:
    available = {normalize(x) for x in skills}
    requirements = {normalize(x) for x in required if normalize(x)}
    missing = sorted(requirements - available)
    score = round(100 * len(requirements & available) / len(requirements)) if requirements else 0
    # 75 is observation: high strictly exceeds 75; 50 is inclusive.
    category = 'high' if score > 75 else 'observation' if score >= 50 else 'discarded'
    return {'match_score': score, 'category': category, 'missing_skills': missing}


def evaluate_job(job, skills: list[str], preferences: dict) -> dict:
    preferences = preferences or {}
    components = []
    reasons = []
    missed = []

    skill_match = match(skills, job.keywords or [])
    if job.keywords:
        components.append((0.35, skill_match['match_score']))
        if skill_match['match_score'] == 100:
            reasons.append('Competências compatíveis com os requisitos da vaga.')
        elif skill_match['match_score']:
            reasons.append(f"{skill_match['match_score']}% das competências da vaga coincidem.")
            missed.append('Competências pendentes: ' + ', '.join(skill_match['missing_skills'][:5]))
        else:
            missed.append('Poucas competências coincidem com os requisitos da vaga.')

    titles = preferences.get('titles') or []
    if titles:
        title_match = any(normalize(title) in normalize(job.title) for title in titles)
        components.append((0.20, 100 if title_match else 0))
        (reasons if title_match else missed).append(
            'Cargo compatível com sua busca.' if title_match else 'Cargo diferente dos títulos selecionados.')

    keywords = [normalize(value) for value in preferences.get('keywords', []) if normalize(value)]
    if keywords:
        searchable = normalize(' '.join([job.title, job.description, *(job.keywords or [])]))
        covered = sum(keyword in searchable for keyword in keywords)
        components.append((0.15, round(100 * covered / len(keywords))))
        (reasons if covered else missed).append(
            f'{covered}/{len(keywords)} palavras-chave encontradas.' if covered else 'Nenhuma palavra-chave selecionada foi encontrada.')

    locations = preferences.get('locations') or []
    if locations:
        location_match = job.modality == 'remote' or any(location_matches(job.location, value) for value in locations)
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
    category = 'strong' if score >= 70 else 'possible' if score >= 40 else 'discarded'
    return {'match_score': score, 'category': category, 'match_reasons': reasons, 'missed_reasons': missed}


def eligible(job, preferences: dict) -> bool:
    return filter_reason(job, preferences) is None


def filter_reason(job, preferences: dict) -> str | None:
    preferences = preferences or {}
    if float(job.salary_max) < preferences.get('min_salary', 0):
        return 'Salário abaixo do piso definido.'
    if preferences.get('modalities') and job.modality not in preferences['modalities']:
        return 'Modalidade não selecionada.'
    if preferences.get('titles') and not any(normalize(t) in normalize(job.title) for t in preferences['titles']):
        return 'Cargo fora dos títulos desejados.'
    contract_types = preferences.get('contract_types') or []
    if contract_types and getattr(job, 'contract_type', None) not in contract_types:
        return 'Tipo de contrato não selecionado.'
    keywords = [normalize(value) for value in preferences.get('keywords', []) if normalize(value)]
    if keywords:
        searchable = normalize(' '.join([job.title, job.description, *(job.keywords or [])]))
        if not any(keyword in searchable for keyword in keywords):
            return 'Palavras-chave não encontradas.'
    if job.modality != 'remote' and preferences.get('locations'):
        if not any(location_matches(job.location, value) for value in preferences['locations']):
            return 'Localização fora da região selecionada.'
    return None