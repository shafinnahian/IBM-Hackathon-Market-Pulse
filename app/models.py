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


class JobDetail(JobSummary):
    """Full job listing including description."""

    description: str = Field("", description="Full plain-text job description")
    source: str = Field("", description="Data source (e.g. themuse)")
    muse_id: int | None = Field(None, description="The Muse platform job ID")


class JobSearchResponse(BaseModel):
    """Paginated job search results."""

    total_results: int = Field(..., description="Number of jobs returned in this response")
    jobs: list[JobSummary]
    limit: int
    skip: int


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
