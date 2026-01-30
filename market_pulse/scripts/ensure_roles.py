"""
Create or update Role documents in the Cloudant jobs database.

Ensures every canonical role from market_pulse.roles exists so job_post
documents can reference them via role_id. Safe to run multiple times (put overwrites).

Usage:
    python -m market_pulse.scripts.ensure_roles

Requires CLOUDANT_URL and CLOUDANT_APIKEY in the environment (or .env).
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from market_pulse.roles import DEFAULT_ROLES

load_dotenv()

DB_NAME = os.environ.get("CLOUDANT_DB_NAME", "market_pulse_jobs")


def _get_cloudant():
    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    from ibmcloudant.cloudant_v1 import CloudantV1

    url = os.environ.get("CLOUDANT_URL")
    apikey = os.environ.get("CLOUDANT_APIKEY")
    if not url or not apikey:
        raise SystemExit("Set CLOUDANT_URL and CLOUDANT_APIKEY in .env")
    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(url)
    return client


def _ensure_db(client) -> None:
    try:
        client.put_database(db=DB_NAME).get_result()
        print(f"Created database: {DB_NAME}")
    except Exception as e:
        if "file_exists" not in str(e).lower() and "412" not in str(e):
            raise


def main() -> None:
    client = _get_cloudant()
    _ensure_db(client)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for role in DEFAULT_ROLES:
        doc_id = f"role:{role['id']}"
        doc = {
            "_id": doc_id,
            "type": "role",
            "name": role["name"],
            "created_at": now,
        }
        try:
            client.put_document(db=DB_NAME, doc_id=doc_id, document=doc).get_result()
            print(f"Upserted {doc_id}")
        except Exception as e:
            print(f"Skip {doc_id}: {e}")

    print(f"Done. {len(DEFAULT_ROLES)} role documents ensured.")


if __name__ == "__main__":
    main()
