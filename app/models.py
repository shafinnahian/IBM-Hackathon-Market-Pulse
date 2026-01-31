from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Job models
# ---------------------------------------------------------------------------

class JobSummary(BaseModel):
    """Compact job listing returned in search results."""

    id: str = Field(..., description="Document ID")
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    locations: list[str] = Field(default_factory=list, description="Job locations")
    categories: list[str] = Field(default_factory=list, description="Job categories like Software Engineering")
    levels: list[str] = Field(default_factory=list, description="Seniority levels like Mid Level, Senior Level")
    publication_date: str = Field("", description="ISO 8601 publication date")
    landing_page_url: str = Field("", description="Link to the full job posting")
    source: str = Field("", description="Data source: 'themuse' or 'adzuna'")


class JobDetail(JobSummary):
    """Full job listing including description."""

    description: str = Field("", description="Full plain-text job description")
    external_id: str | None = Field(None, description="External platform job ID")
    salary_min: float | None = Field(None, description="Minimum salary in USD/year (Adzuna jobs only)")
    salary_max: float | None = Field(None, description="Maximum salary in USD/year (Adzuna jobs only)")


class JobMatchSummary(JobSummary):
    """Job listing with skill match info."""

    matched_skills: list[str] = Field(default_factory=list, description="Skills found in the job description")
    match_count: int = Field(0, description="Number of skills matched")


class JobSearchResponse(BaseModel):
    """Paginated job search results."""

    total_results: int = Field(..., description="Number of jobs returned in this response")
    jobs: list[JobSummary]
    limit: int
    skip: int


class JobMatchResponse(BaseModel):
    """Skill-matched job results, ranked by match count."""

    total_results: int = Field(..., description="Number of jobs returned in this response")
    jobs: list[JobMatchSummary]
    limit: int


# ---------------------------------------------------------------------------
# Trending skills models
# ---------------------------------------------------------------------------

class TrendingSkill(BaseModel):
    """A single skill with its frequency stats."""

    skill: str = Field(..., description="Skill name, e.g. 'Python'")
    count: int = Field(..., description="Number of job descriptions mentioning this skill")
    percentage: float = Field(..., description="count / jobs_analyzed * 100")


class TrendingSkillsResponse(BaseModel):
    """Top trending skills extracted from job descriptions."""

    skills: list[TrendingSkill]
    jobs_analyzed: int = Field(..., description="Total job descriptions scanned")
    limit: int


# ---------------------------------------------------------------------------
# Salary models
# ---------------------------------------------------------------------------

class SalaryInfo(BaseModel):
    """Core salary data."""

    median_salary: float | None = Field(None, description="Total median compensation in USD/year")
    min_salary: float | None = Field(None, description="Minimum reported salary")
    max_salary: float | None = Field(None, description="Maximum reported salary")
    median_base_salary: float | None = Field(None, description="Median base salary excluding bonuses/equity")
    salary_currency: str = Field("USD", description="Currency code")
    salary_period: str = Field("YEAR", description="Pay period")
    publisher_name: str = Field("", description="Data source publisher")
    confidence: str = Field("", description="Confidence level of the estimate")


class SalaryRecord(BaseModel):
    """A single salary data point with context."""

    job_title: str = Field(..., description="Job role title")
    location: str | None = Field(None, description="City or region")
    years_of_experience: str | None = Field(None, description="Experience bracket, e.g. ONE_TO_THREE")
    company: str | None = Field(None, description="Company name")
    salary: SalaryInfo


class SalaryResponse(BaseModel):
    """Salary query results."""

    count: int = Field(..., description="Number of matching salary records")
    data: list[SalaryRecord]
