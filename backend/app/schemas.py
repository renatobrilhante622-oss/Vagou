from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Role = Literal['candidate', 'recruiter']
Modality = Literal['remote', 'hybrid', 'onsite']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Register(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    role: Role
    privacy_version: str
    consent: Literal[True]


class Login(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class DeleteAccount(StrictModel):
    password: str = Field(min_length=1, max_length=128)


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
    phone: str | None = Field(default=None, pattern=r'^\+55\d{10,11}$')


class Preferences(StrictModel):
    titles: list[str] = Field(default_factory=list, max_length=20)
    min_salary: float = Field(default=0, ge=0, le=1000000, allow_inf_nan=False)
    modalities: list[Modality] = Field(default_factory=list, max_length=3)
    locations: list[str] = Field(default_factory=list, max_length=20)
    automation_enabled: bool = False

    @field_validator('titles', 'locations')
    @classmethod
    def valid_terms(cls, value):
        if any(not x.strip() or len(x) > 160 for x in value):
            raise ValueError('Search terms must contain 1–160 characters')
        return value


class JobCreate(StrictModel):
    title: str = Field(min_length=2, max_length=160)
    company: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=30, max_length=30000)
    salary_min: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    salary_max: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    modality: Modality
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


class JobOut(JobCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool
    created_at: datetime


class StatusUpdate(StrictModel):
    status: Literal['reviewing', 'interview', 'rejected', 'hired']