"""The exact data shape we ask the AI to return.

OpenAI Structured Outputs (strict mode) rules we follow:
- Every field is listed and required. "Optional" means the value may be
  null (`str | None`), not that the field may be missing.
- No default values and no extra fields (extra="forbid").
Field descriptions are sent to the model as part of the schema.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectData(StrictModel):
    title: str
    description: str | None
    role: str | None
    start_month: str | None = Field(description="YYYY-MM if stated, otherwise null.")
    end_month: str | None = Field(description="YYYY-MM if stated; null if ongoing or not stated.")
    is_ongoing: bool
    activities: list[str]


class AchievementData(StrictModel):
    title: str
    issuer: str | None
    year: int | None


class ResumeData(StrictModel):
    first_name: str | None
    last_name: str | None
    surname: str | None = Field(
        description="Family name / surname, only if written separately from the last name."
    )
    email: str | None
    phone: str | None
    date_of_birth: str | None = Field(
        description="YYYY-MM-DD, only if a date of birth is explicitly written."
    )
    experience_type: Literal["fresher", "experienced"] | None
    total_experience_months: int | None = Field(
        description="Total professional experience in months, only if stated or computable "
        "from dated job entries."
    )
    current_company: str | None
    professional_role: str | None = Field(description='Main job title, e.g. "Java Developer".')
    skills: list[str]
    current_city: str | None
    preferred_locations: list[str]
    preferred_roles: list[str]
    projects: list[ProjectData]
    certifications: list[AchievementData]
    awards: list[AchievementData]
    experience_summary: str | None = Field(
        description="2-4 sentences using only facts from the resume."
    )