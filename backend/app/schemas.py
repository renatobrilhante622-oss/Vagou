from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.company import valid_cnpj, normalize_cnpj


Password = Annotated[str, StringConstraints(strip_whitespace=False)]
Role = Literal['candidate', 'recruiter']
Modality = Literal['remote', 'hybrid', 'onsite']
ContractType = Literal['clt', 'pj', 'internship', 'temporary', 'apprentice', 'other']


def normalize_br_phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = re.sub(r'\D', '', value)
    if len(digits) in (10, 11):
        digits = '55' + digits
    if len(digits) not in (12, 13) or not digits.startswith('55'):
        raise ValueError('Informe telefone com DDD válido, como +5511999999999.')
    return '+' + digits


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Register(StrictModel):
    email: EmailStr
    password: Password = Field(min_length=12, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    role: Role
    privacy_version: str
    consent: Literal[True]
    company_cnpj: str | None = Field(default=None, max_length=64)
    company_name: str | None = Field(default=None, min_length=2, max_length=200)
    company_contact_email: EmailStr | None = None
    company_phone: str | None = None

    @field_validator('company_phone')
    @classmethod
    def valid_company_phone(cls, value):
        return normalize_br_phone(value)

    @field_validator('company_cnpj')
    @classmethod
    def cnpj_valid(cls, value):
        if value is None:
            return value
        normalized = normalize_cnpj(value)
        if not valid_cnpj(normalized):
            raise ValueError('Informe um CNPJ válido, com dígitos verificadores corretos.')
        return normalized

    @model_validator(mode='after')
    def recruiter_company_required(self):
        fields = [self.company_cnpj, self.company_name, self.company_contact_email, self.company_phone]
        if self.role == 'recruiter' and not all(fields):
            raise ValueError('Informe CNPJ, razão social, e-mail e telefone de contato da empresa.')
        if self.role == 'candidate' and any(value is not None for value in fields):
            raise ValueError('Dados empresariais são exclusivos do cadastro de contratantes.')
        return self


class Login(StrictModel):
    email: EmailStr
    password: Password = Field(min_length=1, max_length=128)


class DeleteAccount(StrictModel):
    password: Password = Field(min_length=1, max_length=128)


class Skills(StrictModel):
    skills: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('skills')
    @classmethod
    def valid_skills(cls, value):
        if any(not x.strip() or len(x) > 80 for x in value):
            raise ValueError('Skills must contain 1–80 characters')
        return sorted(set(x.strip().casefold() for x in value))


class ProfileUpdate(Skills):
    name: str = Field(min_length=2, max_length=120)
    phone: str | None = None

    @field_validator('phone')
    @classmethod
    def phone_normalized(cls, value):
        return normalize_br_phone(value)


class Preferences(StrictModel):
    titles: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    min_salary: float = Field(default=0, ge=0, le=1000000, allow_inf_nan=False)
    modalities: list[Modality] = Field(default_factory=list, max_length=3)
    locations: list[str] = Field(default_factory=list, max_length=20)
    contract_types: list[ContractType] = Field(default_factory=list, max_length=6)
    completed_course_ids: list[str] = Field(default_factory=list, max_length=50)
    automation_enabled: bool | None = False
    automation_max_applications_per_run: int | None = Field(default=20, ge=1, le=100)
    automation_interval_minutes: int | None = Field(default=60, ge=15, le=1440)

    @field_validator('min_salary', mode='before')
    @classmethod
    def empty_salary_is_optional(cls, value):
        return 0 if value is None or value == '' else value

    @field_validator('modalities', 'titles', 'keywords', 'locations', 'contract_types', 'completed_course_ids', mode='before')
    @classmethod
    def empty_lists_are_optional(cls, value):
        return [] if value is None else value

    @field_validator('completed_course_ids')
    @classmethod
    def completed_courses_valid(cls, value):
        from app.courses import COURSES
        allowed = {course['id'] for course in COURSES}
        if any(course not in allowed for course in value):
            raise ValueError('Selecione somente cursos disponíveis no catálogo Vagou!.')
        return list(dict.fromkeys(value))

    @field_validator('titles', 'locations', 'keywords')
    @classmethod
    def valid_terms(cls, value):
        if any(not x.strip() or len(x) > 160 for x in value):
            raise ValueError('Search terms must contain 1–160 characters')
        return value


class AutomationRunReport(StrictModel):
    id: UUID
    status: Literal['queued', 'running', 'complete', 'failed', 'cancelled']
    started_at: datetime
    finished_at: datetime | None = None
    collected_jobs: int = Field(default=0, ge=0)
    scanned_jobs: int = Field(default=0, ge=0)
    external_jobs_scanned: int = Field(default=0, ge=0)
    filtered_jobs: int = Field(default=0, ge=0)
    possible_match_jobs: int = Field(default=0, ge=0)
    eligible_jobs: int = Field(default=0, ge=0)
    submitted_applications: int = Field(default=0, ge=0)
    manual_review_jobs: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    omitted_events: int = Field(default=0, ge=0)


class AutomationRunsReport(StrictModel):
    items: list[AutomationRunReport]
    next_offset: int | None = None


class AutomationRunStatusReport(AutomationRunReport):
    progress: dict = Field(default_factory=dict)


class AutomationEventReport(StrictModel):
    id: UUID
    job_id: UUID | None = None
    job_title: str | None = None
    job_url: str | None = None
    status: Literal['submitted', 'already_applied', 'requires_manual', 'possible_match', 'missing_resume', 'filtered', 'failed']
    detail: str
    created_at: datetime
    company: str | None = None
    location: str | None = None
    source_name: str | None = None
    match_score: int | None = Field(default=None, ge=0, le=100)
    match_reasons: list[str] = Field(default_factory=list)


class AutomationEventsReport(StrictModel):
    run: AutomationRunReport
    items: list[AutomationEventReport]
    next_offset: int | None = None


class JobCreate(StrictModel):
    title: str = Field(min_length=2, max_length=160)
    company: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=30, max_length=30000)
    salary_min: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    salary_max: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    modality: Modality
    contract_type: ContractType | None = None
    location: str = Field(min_length=2, max_length=160)
    keywords: list[str] = Field(min_length=1, max_length=100)

    @field_validator('keywords')
    @classmethod
    def keywords_valid(cls, value):
        return Skills(skills=value).skills

    @model_validator(mode='after')
    def salary_order(self):
        if self.salary_max < self.salary_min:
            raise ValueError('salary_max must be >= salary_min')
        return self


class PublicJobOut(JobCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool
    created_at: datetime
    moderation_status: Literal['pending', 'approved', 'rejected'] = 'pending'
    source_url: str | None = None
    source_name: str = 'Vagou!'


class JobOut(PublicJobOut):
    moderation_note: str | None = None
    moderated_at: datetime | None = None


class StatusUpdate(StrictModel):
    status: Literal['reviewing', 'interview', 'rejected', 'hired']


class VerifyEmail(StrictModel):
    email: EmailStr
    code: str = Field(pattern=r'^\d{6}$')


class ResendVerification(StrictModel):
    email: EmailStr


class ModerationDecision(StrictModel):
    status: Literal['approved', 'rejected']
    note: str = Field(default='', max_length=1000)
