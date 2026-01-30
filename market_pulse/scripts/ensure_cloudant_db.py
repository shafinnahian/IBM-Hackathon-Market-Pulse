"""
Create the Cloudant database (e.g. market_pulse_jobs) if it does not exist.

Usage:
    python -m market_pulse.scripts.ensure_cloudant_db

Requires CLOUDANT_URL and CLOUDANT_APIKEY in the environment (or .env).
"""

import os

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.environ.get("CLOUDANT_DB_NAME", "market_pulse_jobs")


def main() -> None:
    url = os.environ.get("CLOUDANT_URL")
    apikey = os.environ.get("CLOUDANT_APIKEY")
    if not url or not apikey:
        raise SystemExit("Set CLOUDANT_URL and CLOUDANT_APIKEY in .env")

    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    from ibmcloudant.cloudant_v1 import CloudantV1

    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(url)

    try:
        client.put_database(db=DB_NAME).get_result()
        print(f"Created database: {DB_NAME}")
    except Exception as e:
        if "file_exists" in str(e).lower() or "412" in str(e):
            print(f"Database already exists: {DB_NAME}")
        else:
            raise


if __name__ == "__main__":
    main()
