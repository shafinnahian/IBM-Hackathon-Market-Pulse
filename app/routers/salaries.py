from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.database import get_cloudant
from app.models import SalaryInfo, SalaryRecord, SalaryResponse

router = APIRouter(prefix="/salaries", tags=["Salaries"])

DB_NAME = settings.cloudant_db_name


def _doc_to_record(doc: dict) -> SalaryRecord:
    api = doc.get("api_response", {})
    return SalaryRecord(
        job_title=doc.get("job_title", ""),
        location=doc.get("location"),
        years_of_experience=doc.get("years_of_experience"),
        company=doc.get("company"),
        salary=SalaryInfo(
            median_salary=api.get("median_salary"),
            min_salary=api.get("min_salary"),
            max_salary=api.get("max_salary"),
            median_base_salary=api.get("median_base_salary"),
            salary_currency=api.get("salary_currency", "USD"),
            salary_period=api.get("salary_period", "YEAR"),
            publisher_name=api.get("publisher_name", ""),
            confidence=api.get("confidence", ""),
        ),
    )


def _query_salary(selector: dict) -> SalaryResponse:
    client = get_cloudant()
    result = client.post_find(
        db=DB_NAME,
        selector=selector,
        limit=200,
    ).get_result()

    docs = result.get("docs", [])
    records = [_doc_to_record(doc) for doc in docs]
    return SalaryResponse(count=len(records), data=records)


@router.get(
    "/by-location",
    response_model=SalaryResponse,
    operation_id="get_salary_by_location",
    summary="Get salary data for a job title by city/location",
    description=(
        "Returns salary benchmarks for a given role across cities. "
        "Omit location to get all available cities for comparison."
    ),
)
def get_salary_by_location(
    job_title: str = Query(..., description="Job role, e.g. 'Software Engineer', 'Data Scientist'"),
    location: str | None = Query(None, description="City name, e.g. 'San Francisco', 'New York'"),
) -> SalaryResponse:
    selector: dict = {
        "type": "salary_by_location",
        "job_title": {"$regex": f"(?i){job_title}"},
    }
    if location:
        selector["location"] = {"$regex": f"(?i){location}"}

    return _query_salary(selector)


@router.get(
    "/by-experience",
    response_model=SalaryResponse,
    operation_id="get_salary_by_experience",
    summary="Get salary data by years of experience for a job title",
    description=(
        "Shows how compensation scales with experience. "
        "Available brackets: LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX, SEVEN_TO_NINE, TEN_PLUS."
    ),
)
def get_salary_by_experience(
    job_title: str = Query(..., description="Job role, e.g. 'Software Engineer'"),
    years_of_experience: str | None = Query(
        None,
        description="Experience bracket: LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX, SEVEN_TO_NINE, or TEN_PLUS",
    ),
    location: str | None = Query(None, description="City name to filter by"),
) -> SalaryResponse:
    selector: dict = {
        "type": "salary_by_experience",
        "job_title": {"$regex": f"(?i){job_title}"},
    }
    if years_of_experience:
        selector["years_of_experience"] = years_of_experience
    if location:
        selector["location"] = {"$regex": f"(?i){location}"}

    return _query_salary(selector)


@router.get(
    "/by-company",
    response_model=SalaryResponse,
    operation_id="get_salary_by_company",
    summary="Get company-specific salary data for a job title",
    description=(
        "Returns salary data at specific companies. "
        "Omit company to see all available companies for a role."
    ),
)
def get_salary_by_company(
    job_title: str = Query(..., description="Job role, e.g. 'Software Engineer'"),
    company: str | None = Query(None, description="Company name, e.g. 'Google', 'Amazon'"),
) -> SalaryResponse:
    selector: dict = {
        "type": "salary_by_company",
        "job_title": {"$regex": f"(?i){job_title}"},
    }
    if company:
        selector["company"] = {"$regex": f"(?i){company}"}

    return _query_salary(selector)


@router.get(
    "/compare",
    response_model=SalaryResponse,
    operation_id="compare_salaries",
    summary="Compare salaries for a role across locations or companies",
    description=(
        "Side-by-side salary comparison. Provide locations and/or companies to compare. "
        "At least one of locations or companies must be provided."
    ),
)
def compare_salaries(
    job_title: str = Query(..., description="Job role to compare"),
    locations: list[str] | None = Query(None, description="Cities to compare, e.g. 'New York'"),
    companies: list[str] | None = Query(None, description="Companies to compare, e.g. 'Google'"),
) -> SalaryResponse:
    if not locations and not companies:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of 'locations' or 'companies'",
        )

    or_clauses = []
    title_regex = {"$regex": f"(?i){job_title}"}

    if locations:
        or_clauses.append({
            "type": "salary_by_location",
            "job_title": title_regex,
            "location": {"$in": locations},
        })
    if companies:
        or_clauses.append({
            "type": "salary_by_company",
            "job_title": title_regex,
            "company": {"$in": companies},
        })

    selector = {"$or": or_clauses} if len(or_clauses) > 1 else or_clauses[0]
    return _query_salary(selector)
