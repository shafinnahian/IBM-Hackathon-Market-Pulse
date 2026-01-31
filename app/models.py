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
    message: str | None = Field(None, description="Hint when no results are found")


class JobMatchResponse(BaseModel):
    """Skill-matched job results, ranked by match count."""

    total_results: int = Field(..., description="Number of jobs returned in this response")
    jobs: list[JobMatchSummary]
    limit: int


# ---------------------------------------------------------------------------
# Filter models
# ---------------------------------------------------------------------------

class JobFiltersResponse(BaseModel):
    """Matching filter values for a single field."""

    field: str = Field(..., description="The field that was queried: 'locations', 'categories', or 'levels'")
    values: list[str] = Field(..., description="Matching values, sorted alphabetically")
    total: int = Field(..., description="Total number of matches (before limit applied)")


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
    message: str | None = Field(None, description="Hint when no results are found")


# ---------------------------------------------------------------------------
# Salary models
# ---------------------------------------------------------------------------

class SalaryRecord(BaseModel):
    """A single salary data point from an Adzuna job posting."""

    job_title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    location: str = Field(..., description="Job location")
    salary_min: float = Field(..., description="Minimum salary in USD/year")
    salary_max: float = Field(..., description="Maximum salary in USD/year")


class SalaryAggregation(BaseModel):
    """Aggregate salary statistics across matching job postings."""

    avg_salary_min: float = Field(..., description="Average of salary_min across matches")
    avg_salary_max: float = Field(..., description="Average of salary_max across matches")
    overall_min: float = Field(..., description="Lowest salary_min")
    overall_max: float = Field(..., description="Highest salary_max")
    median_salary: float = Field(..., description="Median of (salary_min + salary_max) / 2")


class SalaryResponse(BaseModel):
    """Salary search results with aggregation."""

    count: int = Field(..., description="Number of matching salary records")
    aggregation: SalaryAggregation | None = Field(None, description="Aggregate stats (null if no results)")
    records: list[SalaryRecord]
    message: str | None = Field(None, description="Hint when no results are found")
