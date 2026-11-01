"""Rich job metadata stays additive and validates Brazilian public contracts."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from pydantic import ValidationError

from app.models import Job
from app.schemas import AutomationEventReport, JobCreate, JobOut, PublicJobOut


def payload():
    return {'title': 'Analista de Suporte', 'company': 'Empresa de Tecnologia',
            'description': 'Atendimento de chamados, suporte a sistemas e documentação dos procedimentos.',
            'salary_min': 3000, 'salary_max': 5000, 'modality': 'onsite',
            'location': 'Brasília / DF', 'keywords': ['suporte'],
            'city': 'Brasília', 'state': 'Distrito Federal', 'country': 'br'}


def test_brazilian_state_and_country_write_contract_is_normalized():
    model = JobCreate.model_validate(payload())
    assert model.state == 'DF' and model.country == 'BR'
    for changes in [{'state': 'Bavaria'}, {'country': 'DE'}]:
        with pytest.raises(ValidationError):
            JobCreate.model_validate({**payload(), **changes})
    legacy = payload()
    for name in ('city', 'state', 'country'):
        legacy.pop(name)
    assert JobCreate.model_validate(legacy).city is None


def test_public_job_output_exposes_additive_aliases_without_changing_wire_names():
    job = Job(**JobCreate.model_validate({**payload(), 'contact_email': 'rh@example.com'}).model_dump(),
              id=uuid.uuid4(), created_at=datetime.now(timezone.utc), active=True,
              moderation_status='approved', source_name='Gupy',
              source_url='https://company.gupy.io/jobs/fixture')
    data = PublicJobOut.model_validate(job).model_dump(mode='json')
    assert data['company_name'] == data['company'] == 'Empresa de Tecnologia'
    assert data['external_url'] == data['source_url'] == 'https://company.gupy.io/jobs/fixture'
    assert data['contact_email'] == data['recruiter_email'] == 'rh@example.com'
    assert data['modality'] == 'onsite' and data['modality_label'] == 'Presencial'


def test_public_source_without_structured_skills_serializes_without_fabricating_them():
    values = JobCreate.model_validate(payload()).model_dump()
    values['keywords'] = []
    job = Job(**values, id=uuid.uuid4(), created_at=datetime.now(timezone.utc),
              active=True, moderation_status='approved', source_name='Gupy',
              source_url='https://company.gupy.io/jobs/without-structured-skills')
    assert PublicJobOut.model_validate(job).keywords == []
    with pytest.raises(ValidationError):
        JobCreate.model_validate({**payload(), 'keywords': []})


def test_archived_foreign_metadata_can_be_read_without_relaxing_brazil_only_writes():
    values = JobCreate.model_validate(payload()).model_dump()
    values.update(location='Munich, Bavaria', city='Munich', state=None, country='DE')
    job = Job(**values, id=uuid.uuid4(), created_at=datetime.now(timezone.utc), active=False,
        moderation_status='approved', source_name='Legacy foreign source')
    assert JobOut.model_validate(job).country == 'DE'
    with pytest.raises(ValidationError):
        JobCreate.model_validate({**payload(), 'country': 'DE'})


def test_event_report_accepts_metadata_and_old_snapshot_rows():
    original = {'id': uuid.uuid4(), 'job_id': uuid.uuid4(),
                'status': 'possible_match', 'detail': 'Confira os requisitos.',
                'created_at': datetime.now(timezone.utc)}
    assert AutomationEventReport.model_validate(original).description is None
    enriched = AutomationEventReport.model_validate({**original,
        'description': 'Suporte a estações de trabalho e sistemas internos.',
        'contact_email': 'rh@example.com', 'recruiter_email': 'rh@example.com',
        'city': 'Brasília', 'state': 'DF', 'modality': 'onsite', 'contract_type': 'clt',
        'salary_min': Decimal('3000.00'), 'salary_max': Decimal('5000.00')})
    assert enriched.salary_min == 3000 and enriched.state == 'DF'
