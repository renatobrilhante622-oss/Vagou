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