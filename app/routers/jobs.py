import re
import time
from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.database import get_cloudant
from app.models import (
    JobDetail,
    JobFiltersResponse,
    JobMatchResponse,
    JobMatchSummary,
    JobSearchResponse,
    JobSummary,
    TrendingSkill,
    TrendingSkillsResponse,
)
from app.skills import TECH_SKILLS

router = APIRouter(prefix="/jobs", tags=["Jobs"])

DB_NAME = "market_pulse_jobs"


# ---------------------------------------------------------------------------
# Unified doc → model converters
# ---------------------------------------------------------------------------

def _doc_to_summary(doc: dict) -> JobSummary:
    return JobSummary(
        id=doc.get("_id", ""),
        title=doc.get("title_raw", ""),
        company=doc.get("company_name", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("posted_at", ""),
        landing_page_url=doc.get("url", ""),
        source=doc.get("source", ""),
    )


def _doc_to_detail(doc: dict) -> JobDetail:
    return JobDetail(
        id=doc.get("_id", ""),
        title=doc.get("title_raw", ""),
        company=doc.get("company_name", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("posted_at", ""),
        landing_page_url=doc.get("url", ""),
        description=doc.get("description_raw", ""),
        source=doc.get("source", ""),
        external_id=str(doc.get("external_id")) if doc.get("external_id") is not None else None,
        salary_min=doc.get("salary_min"),
        salary_max=doc.get("salary_max"),
    )


# ---------------------------------------------------------------------------
# Selector builder
# ---------------------------------------------------------------------------

def _build_selector(
    title: str | None,
    company: str | None,
    location: str | None,
    category: str | None,
    level: str | None,
    source: str | None,
) -> dict:
    selector: dict = {"type": "job_post"}

    if source:
        selector["source"] = source
    if title:
        selector["title_raw"] = {"$regex": f"(?i){title}"}
    if company:
        selector["company_name"] = {"$regex": f"(?i){company}"}
    if location:
        selector["locations"] = {"$elemMatch": {"$regex": f"(?i){location}"}}
    if category:
        selector["categories"] = {"$elemMatch": {"$regex": f"(?i){category}"}}
    if level:
        selector["levels"] = {"$elemMatch": {"$regex": f"(?i){level}"}}

    return selector


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=JobSearchResponse,
    operation_id="search_jobs",
    summary="Search job listings by title, company, location, category, or level",
    description=(
        "Search tech job listings from The Muse and Adzuna. All text filters are "
        "case-insensitive partial matches. Combine multiple filters to narrow results. "
        "Use the 'source' parameter to filter by data source ('themuse' or 'adzuna'). "
        "Adzuna jobs include salary data visible in the detail endpoint. "
        "The 'level' filter only applies to Muse jobs."
    ),
)
def search_jobs(
    title: str | None = Query(None, description="Job title keyword, e.g. 'Data Scientist'"),
    company: str | None = Query(None, description="Company name, e.g. 'Google'"),
    location: str | None = Query(None, description="City or region, e.g. 'New York'"),
    category: str | None = Query(
        None,
        description="Job category, e.g. 'Software Engineering', 'Data Science', 'IT Jobs'",
    ),
    level: str | None = Query(
        None,
        description="Seniority level: 'Entry Level', 'Mid Level', or 'Senior Level' (Muse jobs only)",
    ),
    source: str | None = Query(
        None,
        description="Filter by data source: 'themuse', 'adzuna', or omit for both",
    ),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
) -> JobSearchResponse:
    selector: dict = {"type": "job_post"}

    if title:
        selector["title_raw"] = {"$regex": f"(?i){title}"}
    if company:
        selector["company_name"] = {"$regex": f"(?i){company}"}
    if location:
        selector["locations"] = {"$elemMatch": {"$eq": f"(?i){location}"}}
    if category:
        selector["categories"] = {"$elemMatch": {"$regex": f"(?i){category}"}}
    if level:
        selector["levels"] = {"$elemMatch": {"$regex": f"(?i){level}"}}
    client = get_cloudant()

    if source:
        selector = _build_selector(title, company, location, category, level, source)
        result = client.post_find(
            db=DB_NAME, selector=selector, limit=limit, skip=skip,
        ).get_result()
        jobs = [_doc_to_summary(d) for d in result.get("docs", [])]
    else:
        # Interleaved query: half from each source, merged by date
        half_a = limit // 2 + limit % 2
        half_b = limit // 2
        skip_a = skip // 2 + skip % 2
        skip_b = skip // 2

        muse_sel = _build_selector(title, company, location, category, level, "themuse")
        adzuna_sel = _build_selector(title, company, location, category, level, "adzuna")

        muse_docs = client.post_find(
            db=DB_NAME, selector=muse_sel, limit=half_a, skip=skip_a,
        ).get_result().get("docs", [])

        adzuna_docs = client.post_find(
            db=DB_NAME, selector=adzuna_sel, limit=half_b, skip=skip_b,
        ).get_result().get("docs", [])

        all_docs = muse_docs + adzuna_docs
        all_docs.sort(key=lambda d: d.get("posted_at", ""), reverse=True)
        jobs = [_doc_to_summary(d) for d in all_docs]

    return JobSearchResponse(
        total_results=len(jobs),
        jobs=jobs,
        limit=limit,
        skip=skip,
    )


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_filters_cache: JobFiltersResponse | None = None
_filters_cache_time: float = 0


@router.get(
    "/filters",
    response_model=JobFiltersResponse,
    operation_id="get_job_filters",
    summary="Get all available filter values for job searches",
    description=(
        "Returns every distinct location, category, and level in the database. "
        "Use this to discover valid filter values before searching jobs. "
        "For example, call this to find valid locations instead of guessing city names. "
        "Results are cached for 1 hour."
    ),
)
def get_job_filters() -> JobFiltersResponse:
    global _filters_cache, _filters_cache_time

    if _filters_cache and (time.time() - _filters_cache_time) < 3600:
        return _filters_cache

    client = get_cloudant()
    locations: set[str] = set()
    categories: set[str] = set()
    levels: set[str] = set()
    bookmark: str | None = None

    while True:
        kwargs: dict = {
            "db": DB_NAME,
            "selector": {"type": "job_post"},
            "fields": ["locations", "categories", "levels"],
            "limit": 200,
        }
        if bookmark:
            kwargs["bookmark"] = bookmark
        for attempt in range(5):
            try:
                result = client.post_find(**kwargs).get_result()
                break
            except Exception as exc:
                if "429" in str(exc) and attempt < 4:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
        docs = result.get("docs", [])
        if not docs:
            break
        for doc in docs:
            for loc in doc.get("locations", []):
                locations.add(loc)
            for cat in doc.get("categories", []):
                categories.add(cat)
            for lvl in doc.get("levels", []):
                levels.add(lvl)
        bookmark = result.get("bookmark")
        if not bookmark or len(docs) < 200:
            break

    _filters_cache = JobFiltersResponse(
        locations=sorted(locations),
        categories=sorted(categories),
        levels=sorted(levels),
    )
    _filters_cache_time = time.time()
    return _filters_cache


# ---------------------------------------------------------------------------
# Trending skills
# ---------------------------------------------------------------------------

# Pre-compile per-skill regex patterns (case-insensitive, word-boundary)
_SKILL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (skill, re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE))
    for skill in sorted(TECH_SKILLS)
]


@router.get(
    "/trending-skills",
    response_model=TrendingSkillsResponse,
    operation_id="trending_skills",
    summary="Get the most frequently mentioned tech skills across job listings",
    description=(
        "Analyzes job descriptions matching the given filters and returns the most "
        "frequently mentioned tech skills, ranked by frequency. Useful for answering "
        "questions like 'What are the hottest skills for AI right now?' or 'Top skills "
        "for backend dev in California?'"
    ),
)
def trending_skills(
    title: str | None = Query(None, description="Job title keyword, e.g. 'machine learning'"),
    company: str | None = Query(None, description="Company name filter"),
    location: str | None = Query(None, description="City or region, e.g. 'California'"),
    category: str | None = Query(
        None,
        description="Job category, e.g. 'Data Science', 'Software Engineering'",
    ),
    level: str | None = Query(
        None,
        description="Seniority level: 'Entry Level', 'Mid Level', or 'Senior Level'",
    ),
    source: str | None = Query(
        None,
        description="Filter by data source: 'themuse', 'adzuna', or omit for both",
    ),
    limit: int = Query(15, ge=1, le=50, description="Max skills to return (default 15, max 50)"),
) -> TrendingSkillsResponse:
    client = get_cloudant()

    max_docs_per_source = 2000

    def _fetch_all(selector: dict) -> list[dict]:
        """Paginate through matching docs using Cloudant bookmarks (capped)."""
        docs: list[dict] = []
        bookmark: str | None = None
        page_size = 200
        while len(docs) < max_docs_per_source:
            remaining = max_docs_per_source - len(docs)
            kwargs: dict = {"db": DB_NAME, "selector": selector, "limit": min(page_size, remaining)}
            if bookmark:
                kwargs["bookmark"] = bookmark
            for attempt in range(5):
                try:
                    result = client.post_find(**kwargs).get_result()
                    break
                except Exception as exc:
                    if "429" in str(exc) and attempt < 4:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    raise
            page = result.get("docs", [])
            if not page:
                break
            docs.extend(page)
            bookmark = result.get("bookmark")
            if not bookmark or len(page) < page_size:
                break
        return docs

    if source:
        selector = _build_selector(title, company, location, category, level, source)
        docs = _fetch_all(selector)
    else:
        muse_sel = _build_selector(title, company, location, category, level, "themuse")
        adzuna_sel = _build_selector(title, company, location, category, level, "adzuna")
        docs = _fetch_all(muse_sel) + _fetch_all(adzuna_sel)

    # Count skills across all descriptions (once per doc)
    counter: Counter[str] = Counter()
    jobs_analyzed = 0
    for doc in docs:
        text = doc.get("description_raw", "")
        if not text:
            continue
        jobs_analyzed += 1
        for skill_name, pattern in _SKILL_PATTERNS:
            if pattern.search(text):
                counter[skill_name] += 1

    top_skills = [
        TrendingSkill(
            skill=skill,
            count=count,
            percentage=round(count / jobs_analyzed * 100, 1) if jobs_analyzed else 0,
        )
        for skill, count in counter.most_common(limit)
    ]

    return TrendingSkillsResponse(
        skills=top_skills,
        jobs_analyzed=jobs_analyzed,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Skills matching
# ---------------------------------------------------------------------------

def _score_skills(doc: dict, skills: list[str]) -> tuple[list[str], int]:
    """Return (matched_skills, count) for a doc against a list of skills."""
    text = doc.get("description_raw", "").lower()
    matched = [s for s in skills if re.search(rf"\b{re.escape(s.lower())}\b", text)]
    return matched, len(matched)


@router.get(
    "/match-skills",
    response_model=JobMatchResponse,
    operation_id="match_skills",
    summary="Find jobs matching a set of skills",
    description=(
        "Takes a comma-separated list of skills and returns jobs whose descriptions "
        "mention those skills, ranked by how many skills match. Useful for matching "
        "a candidate's resume skills to relevant job listings."
    ),
)
def match_skills(
    skills: str = Query(
        ...,
        description="Comma-separated skills, e.g. 'Python,SQL,React,AWS'",
    ),
    source: str | None = Query(
        None,
        description="Filter by data source: 'themuse', 'adzuna', or omit for both",
    ),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
) -> JobMatchResponse:
    client = get_cloudant()
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]

    if not skill_list:
        return JobMatchResponse(total_results=0, jobs=[], limit=limit)

    pattern = "|".join(re.escape(s) for s in skill_list)
    regex = {"$regex": f"(?i)({pattern})"}
    fetch_limit = limit * 4

    if source:
        selector: dict = {"type": "job_post", "source": source, "description_raw": regex}
        docs = client.post_find(
            db=DB_NAME, selector=selector, limit=fetch_limit,
        ).get_result().get("docs", [])
    else:
        half = fetch_limit // 2
        muse_docs = client.post_find(
            db=DB_NAME,
            selector={"type": "job_post", "source": "themuse", "description_raw": regex},
            limit=half,
        ).get_result().get("docs", [])
        adzuna_docs = client.post_find(
            db=DB_NAME,
            selector={"type": "job_post", "source": "adzuna", "description_raw": regex},
            limit=half,
        ).get_result().get("docs", [])
        docs = muse_docs + adzuna_docs

    scored = []
    for doc in docs:
        matched, count = _score_skills(doc, skill_list)
        if count > 0:
            summary = _doc_to_summary(doc)
            scored.append(JobMatchSummary(
                **summary.model_dump(),
                matched_skills=matched,
                match_count=count,
            ))

    scored.sort(key=lambda j: j.match_count, reverse=True)
    scored = scored[:limit]

    return JobMatchResponse(total_results=len(scored), jobs=scored, limit=limit)


@router.get(
    "/{doc_id}",
    response_model=JobDetail,
    operation_id="get_job_by_id",
    summary="Get full details of a specific job listing",
    description=(
        "Retrieve complete job information including the full description text. "
        "Use the document ID from search results. Works for both Muse and Adzuna jobs. "
        "Adzuna jobs may include salary_min and salary_max fields."
    ),
)
def get_job_by_id(doc_id: str) -> JobDetail:
    client = get_cloudant()

    try:
        result = client.get_document(db=DB_NAME, doc_id=doc_id).get_result()
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    return _doc_to_detail(result)
