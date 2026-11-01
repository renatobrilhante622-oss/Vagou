"""Brazil-only public catalog and rich regional recommendation contracts."""
import asyncio
import os
import uuid

import httpx
import pytest

from app.job_catalog import unique_reasons


def test_legacy_explanations_are_readable_and_unique():
    assert unique_reasons(['  Cargo compatível. ', 'cargo compatível;', 'Localização compatível.']) == [
        'Cargo compatível.', 'Localização compatível.']
    assert unique_reasons('Um motivo completo.') == ['Um motivo completo.']


@pytest.mark.skipif(not os.getenv('VAGOU_TEST_URL'), reason='Disposable integration stack required')
def test_regional_feed_finds_high_and_possible_matches_and_archives_foreign_rows():
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config import settings
    from app.models import Job, User
    from app.security import token

    async def scenario():
        engine = create_async_engine(settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        candidate_id, recruiter_id = uuid.uuid4(), uuid.uuid4()
        high_id, possible_id, foreign_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        try:
            async with sessions.begin() as db:
                common = dict(name='Regional fixture', email_verified=True, password_hash='fixture-unused',
                              privacy_version='2026-01')
                candidate = User(id=candidate_id, email=f'{candidate_id}@example.com', role='candidate',
                    skills=['suporte', 'windows', 'redes'], preferences={'titles':['Suporte N2'],
                    'keywords':['suporte', 'tecnologia'], 'locations':['Brasília / DF'],
                    'modalities':['onsite']}, **common)
                db.add_all([candidate, User(id=recruiter_id, email=f'{recruiter_id}@example.com', role='recruiter', **common)])
                await db.flush()
                fixture = dict(recruiter_id=recruiter_id, company='Empresa fixture brasileira',
                    description='Atendimento de chamados, diagnóstico de hardware e suporte Windows aos usuários.',
                    salary_min=4000, salary_max=6000, modality='onsite', contract_type='clt',
                    location='Brasília / DF', city='Brasília', state='DF', country='BR',
                    moderation_status='approved', source_name='Gupy', contact_email='rh@example.com')
                older = datetime.now(timezone.utc) - timedelta(days=1)
                db.add(Job(id=high_id, title='Analista de Suporte N2', keywords=['suporte', 'windows'],
                    source_url=f'https://example.com/jobs/{high_id}', created_at=older, **fixture))
                db.add(Job(id=possible_id, title='Analista de Service Desk', keywords=['windows', 'hardware'],
                    source_url=f'https://example.com/jobs/{possible_id}', created_at=older, **fixture))
                db.add(Job(id=foreign_id, title='IT Support', keywords=['suporte'],
                    **{**fixture, 'location':'Munich, Bavaria', 'city':'Munich', 'state':None, 'country':'DE'}))
                # More recent, unrelated Brazilian ads must not hide regional
                # recommendations behind the first twenty rows of the catalog.
                for _ in range(24):
                    db.add(Job(title='Analista de Suporte N2', keywords=['suporte'],
                        **{**fixture, 'location':'São Paulo / SP', 'city':'São Paulo', 'state':'SP'}))
            async with httpx.AsyncClient(base_url=os.environ['VAGOU_TEST_URL'], timeout=30) as client:
                response = await client.get('/v1/matches?limit=2', headers={'Authorization':'Bearer ' + token(candidate)})
                assert response.status_code == 200, response.text
                payload = response.json()
                rows = {row['job']['id']: row for row in payload['items']}
                assert set(rows) == {str(high_id), str(possible_id)}
                assert rows[str(high_id)]['match_score'] >= 70 and rows[str(high_id)]['category'] == 'high'
                assert 40 <= rows[str(possible_id)]['match_score'] < 70
                assert rows[str(possible_id)]['category'] == 'observation'
                job = rows[str(high_id)]['job']
                assert job['city'] == 'Brasília' and job['state'] == 'DF' and job['country'] == 'BR'
                assert job['company_name'] == fixture['company'] and job['description'] == fixture['description']
                assert job['contact_email'] == job['recruiter_email'] == 'rh@example.com'
                assert job['external_url'] == f'https://example.com/jobs/{high_id}'
                assert payload['collector_status']['failed_sources'] == 0
                for row in rows.values():
                    assert len(row['match_reasons']) == len(set(row['match_reasons']))
                assert (await client.get(f'/v1/jobs/{foreign_id}')).status_code == 404
            async with sessions() as db:
                saved = await db.get(Job, foreign_id)
                assert saved is not None and saved.active is False
        finally:
            async with sessions.begin() as db:
                await db.execute(delete(User).where(User.id.in_([candidate_id, recruiter_id])))
            await engine.dispose()

    asyncio.run(scenario())
