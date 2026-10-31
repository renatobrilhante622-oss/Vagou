"""Deterministic matching and shared, explainable vacancy preference filters."""
import re
import unicodedata


STATES = {
    'acre': 'ac', 'alagoas': 'al', 'amapa': 'ap', 'amazonas': 'am', 'bahia': 'ba',
    'ceara': 'ce', 'distrito federal': 'df', 'espirito santo': 'es', 'goias': 'go',
    'maranhao': 'ma', 'mato grosso': 'mt', 'mato grosso do sul': 'ms',
    'minas gerais': 'mg', 'para': 'pa', 'paraiba': 'pb', 'parana': 'pr',
    'pernambuco': 'pe', 'piaui': 'pi', 'rio de janeiro': 'rj',
    'rio grande do norte': 'rn', 'rio grande do sul': 'rs', 'rondonia': 'ro',
    'roraima': 'rr', 'santa catarina': 'sc', 'sao paulo': 'sp', 'sergipe': 'se',
    'tocantins': 'to',
}


def normalize(value: str) -> str:
    plain = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
    return ' '.join(plain.split())


def location_key(value: str) -> tuple[str, str | None]:
    """Parse city/UF without removing meaningful hyphens in municipality names."""
    value = normalize(value)
    parts = re.split(r'\s*[/,]\s*|\s+-\s+', value)
    if len(parts) > 1:
        state = STATES.get(parts[-1], parts[-1])
        if state in STATES.values():
            return ' '.join(parts[:-1]).strip(), state
    match_state = re.fullmatch(r'(.+)\s+([a-z]{2})', value)
    if match_state and match_state[2] in STATES.values():
        return match_state[1].strip(), match_state[2]
    return value, None


def location_matches(location: str, requested: str) -> bool:
    city, state = location_key(location)
    requested_city, requested_state = location_key(requested)
    return city == requested_city and (requested_state is None or state == requested_state)


def match(skills: list[str], required: list[str]) -> dict:
    available = {normalize(x) for x in skills}
    requirements = {normalize(x) for x in required if normalize(x)}
    missing = sorted(requirements - available)
    score = round(100 * len(requirements & available) / len(requirements)) if requirements else 0
    category = 'high' if score > 75 else 'observation' if score >= 50 else 'discarded'
    return {'match_score': score, 'category': category, 'missing_skills': missing}


def eligible(job, preferences: dict) -> bool:
    # A vacancy range must overlap the candidate's desired remuneration range.
    if float(job.salary_max) < preferences.get('min_salary', 0):
        return False
    maximum = preferences.get('max_salary')
    if maximum is not None and float(getattr(job, 'salary_min', 0)) > maximum:
        return False
    if preferences.get('modalities') and job.modality not in preferences['modalities']:
        return False
    if preferences.get('titles') and not any(normalize(t) in normalize(job.title) for t in preferences['titles']):
        return False
    if job.modality != 'remote' and preferences.get('locations') and not any(
            location_matches(job.location, location) for location in preferences['locations']):
        return False
    return True
