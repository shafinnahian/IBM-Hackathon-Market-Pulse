"""
Company normalization and Cloudant upsert.

Given a company name (and optional source id), derive a deterministic _id
(e.g. company:acme-corp) and upsert the company document so job_post
documents can reference company_id.
"""

import re
from datetime import datetime, timezone


def normalize_company_slug(name: str) -> str:
    """
    Normalize company name to a slug for use in _id.
    Lowercase, replace non-alphanumeric with hyphen, collapse hyphens.
    """
    if not name or not isinstance(name, str):
        return "unknown"
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def company_id_from_slug(slug: str) -> str:
    """Return Cloudant document _id for a company slug."""
    return f"company:{slug}"


def ensure_company(
    client,
    db: str,
    name: str,
    source_id: str | None = None,
) -> str:
    """
    Upsert a company document and return its _id (company_id).
    Uses normalized name for deterministic _id so re-runs overwrite.
    """
    slug = normalize_company_slug(name)
    doc_id = company_id_from_slug(slug)
    display_name = (name or "").strip() or "Unknown"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "_id": doc_id,
        "type": "company",
        "name": display_name,
        "normalized_name": slug.replace("-", " "),
        "created_at": now,
    }
    if source_id:
        doc["source_id"] = source_id
    rev = None
    try:
        existing = client.get_document(db=db, doc_id=doc_id).get_result()
        rev = existing.get("_rev") if isinstance(existing, dict) else getattr(existing, "_rev", None)
    except Exception:
        pass
    kwargs = {"db": db, "doc_id": doc_id, "document": doc}
    if rev is not None:
        kwargs["rev"] = rev
    client.put_document(**kwargs).get_result()
    return doc_id
