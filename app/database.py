from ibmcloudant.cloudant_v1 import CloudantV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from app.config import settings

_client: CloudantV1 | None = None


def get_cloudant() -> CloudantV1:
    global _client
    if _client is None:
        authenticator = IAMAuthenticator(settings.cloudant_apikey)
        _client = CloudantV1(authenticator=authenticator)
        _client.set_service_url(settings.cloudant_url)
    return _client


def ensure_database(db_name: str) -> None:
    """Create a database if it doesn't already exist."""
    client = get_cloudant()
    try:
        client.put_database(db=db_name).get_result()
    except Exception:
        pass  # database already exists
