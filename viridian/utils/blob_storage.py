import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse
import re
from urllib.parse import urlparse

import requests
from azure.core.credentials import AccessToken
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobClient, BlobServiceClient, ContainerClient
from azure.storage.queue import QueueClient

DEFAULT_CONN_STR = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://localhost:10000/devstoreaccount1;QueueEndpoint=http://localhost:10001/devstoreaccount1;TableEndpoint=http://localhost:10002/devstoreaccount1;"
DEFAULT_BLOB_URL_PREFIX = "http://localhost:10000/devstoreaccount1/fixity-dev"

BLOB_NAME_SUFFIX_PATTERN = r"(\d{4}/\d{2}/\d{2}/.*)$"
STORAGE_ENTITY_TYPE_MAP = {
    "FL": "FILE",
    "IE": "IE",
}


@dataclass
class EntityInfo:
    stored_entity_id: str
    version: int
    storage_entity_type: str

    def is_valid_storage_entity_type(self):
        return self.storage_entity_type in STORAGE_ENTITY_TYPE_MAP.values()


ENTITY_INFO_PATTERN = re.compile(r"^V(\d+)[-_](FL|IE|SIP|MD)([^.]+)$")


def guess_entity_info(blob_name: str) -> Optional[EntityInfo]:
    if not blob_name:
        return None
    file_name = blob_name.split("/")[-1]
    file_name = file_name.split(".", 1)[0]
    match = ENTITY_INFO_PATTERN.match(file_name)
    if not match:
        return None

    version = int(match.group(1))
    storage_entity_type = match.group(2)
    stored_entity_id = f"{match.group(2)}{match.group(3)}"
    storage_entity_type = STORAGE_ENTITY_TYPE_MAP.get(
        storage_entity_type, storage_entity_type
    )

    return EntityInfo(
        stored_entity_id=stored_entity_id,
        version=version,
        storage_entity_type=storage_entity_type,
    )


@dataclass
class StorageAccessAccount:
    protocol: str
    account_name: str
    account_key: str
    blob_endpoint: str
    queue_endpoint: str
    table_endpoint: str
    fixity_worker_url: str

    def blob_url_prefix(self, container_name):
        return f"{self.blob_endpoint}/{container_name}"


def is_malformed_blob_name(blob_name: str) -> bool:
    if blob_name is None or blob_name.strip() == "":
        return True

    # Validate the raw path segment as it appears in the URL. Reserved URL
    # characters such as ?, &, #, spaces, etc. must be percent-encoded;
    # otherwise they change the meaning of the URL and should be treated as
    # malformed.
    try:
        return quote(unquote(blob_name), safe="/") != blob_name
    except Exception:
        return True


@dataclass
class BlobAccessArguments:
    account_url: str
    account_name: str
    container_name: str
    _blob_name: str
    index_location: str
    blob_prefix: Optional[str] = None

    @property
    def blob_name(self):
        if self._blob_name is None:
            return None
        return unquote(self._blob_name)

    def is_empty_blob_prefix(self):
        return not self.blob_prefix or self.blob_prefix.strip() == ""

    def is_blob_name_malformed(self):
        return is_malformed_blob_name(self._blob_name)


@dataclass
class QueueAccessArguments:
    account_url: str
    queue_name: str


class StaticTokenCredential:
    def __init__(self, token: str, expires_on: int):
        self._token = token
        self._expires_on = expires_on

    def get_token(self, *scopes, **kwargs):
        return AccessToken(self._token, self._expires_on)

    @property
    def token(self):
        return self._token


def _get_value_by_key(conn_str: str, key: str) -> str:
    start_idx = conn_str.index(key)
    if start_idx < 0:
        return None
    end_idx = conn_str.index(";", start_idx)
    if end_idx < 0:
        return conn_str[start_idx + len(key) + 1 :]
    else:
        return conn_str[start_idx + len(key) + 1 : end_idx]


def get_managed_credential(
    managed_identity_client_id=None,
    managed_identity_token_url=None,
    resource="https://storage.azure.com/",
):
    client_id = managed_identity_client_id or os.environ.get(
        "MANAGED_IDENTITY_CLIENT_ID", None
    )
    if client_id is None:
        raise ValueError("MANAGED_IDENTITY_CLIENT_ID environment variable is not set.")
    token_url = managed_identity_token_url or os.environ.get(
        "MANAGED_IDENTITY_TOKEN_URL", None
    )
    if token_url is None:
        credential = ManagedIdentityCredential(client_id=client_id)
        return credential

    params = {
        "api-version": "2025-04-07",
        "resource": resource,
        "client_id": client_id,
    }
    headers = {"Metadata": "true"}
    response = requests.get(token_url, params=params, headers=headers)
    response.raise_for_status()
    data = response.json()
    credential = StaticTokenCredential(data["access_token"], int(data["expires_on"]))
    return credential


def parse_conn_str(conn_str: str) -> StorageAccessAccount:
    if conn_str and conn_str.strip().rstrip(";") == "UseDevelopmentStorage=true":
        conn_str = DEFAULT_CONN_STR

    if not conn_str or not conn_str.startswith("DefaultEndpointsProtocol"):
        raise ValueError(f"Invalid connection string: {conn_str}")

    protocol = _get_value_by_key(conn_str, "DefaultEndpointsProtocol")
    account_name = _get_value_by_key(conn_str, "AccountName")
    account_key = _get_value_by_key(conn_str, "AccountKey")
    if account_name == "devstoreaccount1":
        blob_endpoint = _get_value_by_key(conn_str, "BlobEndpoint")
        queue_endpoint = _get_value_by_key(conn_str, "QueueEndpoint")
        table_endpoint = _get_value_by_key(conn_str, "TableEndpoint")
        fixity_worker_url = "http://localhost:7071"
    else:
        blob_endpoint = f"https://{account_name}.blob.core.windows.net"
        queue_endpoint = f"https://{account_name}.queue.core.windows.net"
        table_endpoint = f"https://{account_name}.table.core.windows.net"
        fixity_worker_url = f"https://{account_name}.azurewebsites.net"

    return StorageAccessAccount(
        protocol=protocol,
        account_name=account_name,
        account_key=account_key,
        blob_endpoint=blob_endpoint,
        queue_endpoint=queue_endpoint,
        table_endpoint=table_endpoint,
        fixity_worker_url=fixity_worker_url,
    )


def guess_index_location(blob_name: str):
    if not blob_name:
        return None

    match = re.search(BLOB_NAME_SUFFIX_PATTERN, blob_name)

    if match:
        return match.group(1)

    return blob_name


def parse_blob_url(blob_url: str) -> BlobAccessArguments:
    try:
        blob = BlobClient.from_blob_url(blob_url)
    except Exception as e:
        raise ValueError(f"Invalid blob URL: {blob_url}") from e

    account_url = f"{blob.scheme}://{blob.primary_hostname}"
    prefix_len = len(account_url) + len(blob.container_name) + 2  # +2 for the slashes
    if len(blob_url) > prefix_len:
        blob_name = blob_url[prefix_len:]
    else:
        blob_name = None

    index_location = guess_index_location(blob_name)
    blob_prefix = (
        blob_name[: -len(index_location)] if blob_name and index_location else None
    )
    if blob_prefix:
        blob_prefix = blob_prefix.strip("/")

    return BlobAccessArguments(
        account_url=account_url,
        account_name=blob.account_name,
        container_name=blob.container_name,
        _blob_name=blob_name,
        index_location=index_location,
        blob_prefix=blob_prefix,
    )


def build_container_client(
    account_url,
    container_name,
    *,
    connection_string=None,
    managed_identity_client_id=None,
    managed_identity_token_url=None,
    connection_verify=False,
) -> ContainerClient:
    if connection_string:
        if (
            connection_string
            and connection_string.strip().rstrip(";") == "UseDevelopmentStorage=true"
        ):
            connection_string = DEFAULT_CONN_STR

        blob_service_client = BlobServiceClient.from_connection_string(
            conn_str=connection_string,
            connection_verify=connection_verify,
        )
        container_client = blob_service_client.get_container_client(container_name)
    else:
        if not account_url:
            raise ValueError("account_url is required for managed identity auth.")
        credential = get_managed_credential(
            managed_identity_client_id=managed_identity_client_id,
            managed_identity_token_url=managed_identity_token_url,
        )
        blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=credential,
            connection_verify=connection_verify,
        )
        container_client = blob_service_client.get_container_client(container_name)

    return container_client


def build_blob_client(
    blob_url,
    *,
    connection_string=None,
    managed_identity_client_id=None,
    connection_verify=False,
) -> BlobClient:
    if not blob_url:
        raise ValueError("Blob_url is required.")

    blob_info = parse_blob_url(blob_url)
    account_url = blob_info.account_url
    container_name = blob_info.container_name
    blob_name = blob_info.blob_name

    if connection_string:
        if (
            connection_string
            and connection_string.strip().rstrip(";") == "UseDevelopmentStorage=true"
        ):
            connection_string = DEFAULT_CONN_STR

        blob_client = BlobClient.from_connection_string(
            conn_str=connection_string,
            container_name=container_name,
            blob_name=blob_name,
            connection_verify=connection_verify,
        )
    else:
        if not account_url:
            raise ValueError("account_url is required for managed identity auth.")
        credential = DefaultAzureCredential(
            managed_identity_client_id=managed_identity_client_id,
        )
        blob_client = BlobClient(
            account_url=account_url,
            container_name=container_name,
            blob_name=blob_name,
            credential=credential,
            connection_verify=connection_verify,
        )

    return blob_client


def parse_queue_url(queue_url: str) -> QueueAccessArguments:
    parsed = urlparse(queue_url)
    path = parsed.path.lstrip("/")
    segments = [seg for seg in path.split("/") if seg]
    if len(segments) < 1:
        raise ValueError("Queue URL must include queue name.")

    if ".queue." in parsed.netloc:
        # Production-style: https://{account}.queue.core.windows.net/{queue}
        account_url = f"{parsed.scheme}://{parsed.netloc}"
        queue_name = segments[0]
    else:
        # Azurite-style: http://127.0.0.1:10001/{account}/{queue}
        if len(segments) < 2:
            raise ValueError("Azurite Queue URL must include account and queue name.")
        account_name = segments[0]
        account_url = f"{parsed.scheme}://{parsed.netloc}/{account_name}"
        queue_name = segments[1]

    return QueueAccessArguments(
        account_url=account_url,
        queue_name=unquote(queue_name),
    )


def build_queue_client(
    queue_url,
    *,
    connection_string=None,
    managed_identity_client_id=None,
    clear_queue=False,
    verify_ssl=False,
    ssl_cert_path=None,
) -> QueueClient:

    if not queue_url:
        raise ValueError("queue_url is required.")

    logging.info(
        f"Building QueueClient for queue_url: {queue_url}, connection_string: {connection_string}, managed_identity_client_id: {managed_identity_client_id}, clear_queue: {clear_queue}, verify_ssl: {verify_ssl}, ssl_cert_path: {ssl_cert_path} "
    )

    queue_info = parse_queue_url(queue_url)

    logging.info(
        f"Parsed queue_url: account_url={queue_info.account_url}, queue_name={queue_info.queue_name}"
    )

    account_url = queue_info.account_url
    queue_name = queue_info.queue_name
    connection_verify = verify_ssl
    connection_cert = None

    if ssl_cert_path:
        cert_path = Path(ssl_cert_path)
        if cert_path.is_dir():
            crt_file = cert_path / "fixity.cer"
            key_file = cert_path / "fixity.key"
            if crt_file.is_file() and key_file.is_file():
                connection_cert = (str(crt_file), str(key_file))
        elif cert_path.is_file():
            sibling_key = cert_path.with_suffix(".key")
            if sibling_key.is_file():
                connection_cert = (str(cert_path), str(sibling_key))
            else:
                # A single PEM may contain both certificate and private key.
                connection_cert = str(cert_path)

    client_options = {"connection_verify": connection_verify}
    if connection_cert:
        client_options["connection_cert"] = connection_cert

    if connection_string:
        logging.info("Using connection string for QueueClient authentication.")
        queue_client = QueueClient.from_connection_string(
            conn_str=connection_string,
            queue_name=queue_name,
            **client_options,
        )
    else:
        if not account_url:
            raise ValueError("account_url is required for managed identity auth.")
        credential = DefaultAzureCredential(
            managed_identity_client_id=managed_identity_client_id
        )
        queue_client = QueueClient(
            account_url=account_url,
            queue_name=queue_name,
            credential=credential,
            **client_options,
        )

    try:
        queue_client.create_queue()
    except ResourceExistsError:
        pass
    except Exception as ex:
        logging.error(f"Failed to create queue: {queue_name}. Error: {ex}")
        raise ex

    if clear_queue:
        queue_client.clear_messages()

    return queue_client


def save_json_payload_to_blob(
    blob_url,
    payload_raw,
    *,
    connection_string=None,
    managed_identity_client_id=None,
    ignore_cert_verification=None,
):
    blob_info = parse_blob_url(blob_url)
    if ignore_cert_verification is None:
        ignore_cert_verification = os.environ.get(
            "AZURE_IGNORE_CERT_VERIFICATION", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
    connection_verify = not ignore_cert_verification

    container_client = None
    if connection_string:
        if (
            connection_string
            and connection_string.strip().rstrip(";") == "UseDevelopmentStorage=true"
        ):
            connection_string = DEFAULT_CONN_STR

        blob_service_client = BlobServiceClient.from_connection_string(
            connection_string,
            connection_verify=connection_verify,
        )
        container_client = blob_service_client.get_container_client(
            blob_info.container_name
        )
    else:
        credential = DefaultAzureCredential(
            managed_identity_client_id=managed_identity_client_id
        )
        blob_service_client = BlobServiceClient(
            account_url=blob_info.account_url,
            credential=credential,
            connection_verify=connection_verify,
        )
        container_client = blob_service_client.get_container_client(
            blob_info.container_name
        )

    try:
        container_client.create_container()
    except ResourceExistsError:
        pass
    except Exception as ex:
        print(f"Failed to create container: {blob_info.container_name}. Error: {ex}")
        raise ex

    blob_client = None
    try:
        blob_client = container_client.get_blob_client(blob_info.blob_name)
        blob_client.upload_blob(
            payload_raw, overwrite=True, content_type="application/json"
        )
    finally:
        if blob_client:
            blob_client.close()


def read_json_payload_from_blob(
    blob_url,
    *,
    connection_string=None,
    managed_identity_client_id=None,
    ignore_cert_verification=None,
):
    if ignore_cert_verification is None:
        ignore_cert_verification = os.environ.get(
            "AZURE_IGNORE_CERT_VERIFICATION", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
    connection_verify = not ignore_cert_verification
    blob_client = None
    try:
        blob_client = build_blob_client(
            blob_url=blob_url,
            connection_string=connection_string,
            managed_identity_client_id=managed_identity_client_id,
            connection_verify=connection_verify,
        )
        content = blob_client.download_blob().readall()
        return content
    finally:
        if blob_client:
            blob_client.close()


class AzureWebJobsStorage:
    FAN_IN_CONTAINER_NAME = "fixity-fan-in"
    FAN_OUT_CONTAINER_NAME = "fixity-fan-out"

    def __init__(self, connection_string=None, connection_verify=True):
        if connection_string is None:
            connection_string = os.environ.get("AzureWebJobsStorage", None)
        if connection_string is None:
            connection_string = os.environ.get(
                "AZURE_WEB_JOBS_STORAGE", DEFAULT_CONN_STR
            )
        if connection_string.strip().rstrip(";") == "UseDevelopmentStorage=true":
            connection_string = DEFAULT_CONN_STR

        self.connection_string = connection_string
        self.connection_verify = connection_verify
        self.storage_account = parse_conn_str(connection_string)

    def read_blob(self, blob_url: str) -> dict:
        blob_client = None
        try:
            blob_info = parse_blob_url(blob_url)
            account_url = blob_info.account_url
            container_name = blob_info.container_name
            blob_name = blob_info.blob_name

            blob_client = BlobClient.from_connection_string(
                conn_str=self.connection_string,
                container_name=container_name,
                blob_name=blob_name,
                connection_verify=not self.connection_verify,
            )
            content = blob_client.download_blob().readall()
            return json.loads(content)
        finally:
            if blob_client:
                blob_client.close()

    def write_blob(self, trans_id: str, data: dict, container_name: str) -> str:
        container_client = None
        blob_client = None
        try:
            container_client = ContainerClient.from_connection_string(
                conn_str=self.connection_string,
                container_name=container_name,
                connection_verify=not self.connection_verify,
            )

            if not container_client.exists():
                container_client.create_container()

            blob_client = container_client.get_blob_client(f"{trans_id}.json")
            blob_client.upload_blob(
                json.dumps(data), overwrite=True, content_type="application/json"
            )

            blob_url = f"{self.storage_account.blob_url_prefix(container_name)}/{trans_id}.json"

            return blob_url
        except ResourceExistsError:
            pass
        except Exception as ex:
            logging.error(f"Failed to create container: {container_name}. Error: {ex}")
            raise ex
        finally:
            if blob_client:
                blob_client.close()
            if container_client:
                container_client.close()

    def delete_durable_blobs(self, trans_id: str) -> None:
        req_blob_url = f"{self.storage_account.blob_url_prefix(self.FAN_IN_CONTAINER_NAME)}/{trans_id}.json"
        req_blob_client = build_blob_client(
            blob_url=req_blob_url, connection_string=self.connection_string
        )
        try:
            req_blob_client.delete_blob()
        except Exception as e:
            logging.error(f"Failed to delete request blob: {req_blob_url}. Error: {e}")

        rsp_blob_url = f"{self.storage_account.blob_url_prefix(self.FAN_OUT_CONTAINER_NAME)}/{trans_id}.json"
        rsp_blob_client = build_blob_client(
            blob_url=rsp_blob_url, connection_string=self.connection_string
        )
        try:
            rsp_blob_client.delete_blob()
        except Exception as e:
            logging.error(f"Failed to delete response blob: {rsp_blob_url}. Error: {e}")


azure_web_job_storage = AzureWebJobsStorage()
