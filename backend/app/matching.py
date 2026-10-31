"""Deterministic, explainable matching; no inferred skills from untrusted PDF text."""
import unicodedata


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).strip()


def match(skills: list[str], required: list[str]) -> dict:
    available = {normalize(x) for x in skills}
    requirements = {normalize(x) for x in required if normalize(x)}
    missing = sorted(requirements - available)
    score = round(100 * len(requirements & available) / len(requirements)) if requirements else 0
    # 75 is observation: high strictly exceeds 75; 50 is inclusive.
    category = 'high' if score > 75 else 'observation' if score >= 50 else 'discarded'
    return {'match_score': score, 'category': category, 'missing_skills': missing}


def eligible(job, preferences: dict) -> bool:
    if float(job.salary_max) < preferences.get('min_salary', 0):
        return False
    if preferences.get('modalities') and job.modality not in preferences['modalities']:
        return False
    if preferences.get('titles') and not any(normalize(t) in normalize(job.title) for t in preferences['titles']):
        return False
    if job.modality != 'remote' and preferences.get('locations') and normalize(job.location) not in {normalize(x) for x in preferences['locations']}:
        return False
    return True