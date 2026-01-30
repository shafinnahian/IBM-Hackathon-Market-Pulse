"""
Role configuration and title → role_id mapping.

Canonical roles and keyword/synonym lists are used to map raw job titles
from APIs to a role document _id (e.g. role:software-engineer).
"""

# Order matters: first matching role wins. Put more specific roles first.
DEFAULT_ROLES = [
    {
        "id": "software-engineer",
        "name": "Software Engineer",
        "keywords": [
            "software engineer",
            "backend engineer",
            "frontend engineer",
            "full stack",
            "fullstack",
            "python developer",
            "python architect",
            "java developer",
            "developer",
            "engineer",
            "architect",
            "programmer",
            "software development",
            "application developer",
        ],
    },
    {
        "id": "data-scientist",
        "name": "Data Scientist",
        "keywords": [
            "data scientist",
            "data engineer",
            "data analyst",
            "analytics",
            "machine learning",
            "ml engineer",
            "ai engineer",
            "research scientist",
        ],
    },
    {
        "id": "devops",
        "name": "DevOps / SRE",
        "keywords": [
            "devops",
            "sre",
            "site reliability",
            "platform engineer",
            "cloud engineer",
            "infrastructure",
        ],
    },
    {
        "id": "product-manager",
        "name": "Product Manager",
        "keywords": [
            "product manager",
            "product owner",
            "technical product",
        ],
    },
    {
        "id": "other",
        "name": "Other",
        "keywords": [],
    },
]


def map_title_to_role_id(title: str, roles: list[dict] | None = None) -> str:
    """
    Map a raw job title to a canonical role _id.

    Uses keyword matching (case-insensitive). First role whose keywords
    appear in the title wins. If none match, returns role:other.

    Args:
        title: Raw job title from the API (e.g. "Senior Python Architect").
        roles: List of role dicts with "id" and "keywords". Defaults to DEFAULT_ROLES.

    Returns:
        Role document _id, e.g. "role:software-engineer".
    """
    if roles is None:
        roles = DEFAULT_ROLES
    normalized = (title or "").strip().lower()
    if not normalized:
        return "role:other"

    for role in roles:
        if role["id"] == "other":
            continue
        for kw in role.get("keywords", []):
            if kw and kw.lower() in normalized:
                return f"role:{role['id']}"

    return "role:other"
