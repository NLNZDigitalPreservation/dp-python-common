import hashlib
import logging
import os
from datetime import datetime as dt

from azure.core.exceptions import ResourceNotFoundError
from metadata import EntityInfo, FileFixityResult, FinalResultCode
from utils.blob_storage import DEFAULT_CONN_STR, build_blob_client


def pretty_size(size_in_bytes):
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = size_in_bytes
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    return f"{size:.2f}{units[unit_index]}"


def calculate_md5(entity: EntityInfo):
    managed_identity_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID", None)
    if managed_identity_client_id is None:
        connection_string = os.environ.get(
            "RosettaBlobConnectionString", DEFAULT_CONN_STR
        )
    else:
        connection_string = None

    ret = FileFixityResult(
        id=entity.id,
        blob_url=entity.blob_url,
        blob_size=0,
        state=FinalResultCode.COMMON_ERROR,
    )

    md5_hash = hashlib.md5()
    blob_client = None
    try:
        blob_client = build_blob_client(
            blob_url=entity.blob_url,
            connection_string=connection_string,
            managed_identity_client_id=managed_identity_client_id,
            connection_verify=True,
        )

        if not blob_client.exists():
            ret.state = FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS
        else:
            props = blob_client.get_blob_properties()

            downloader = blob_client.download_blob()
            for chunk in downloader.chunks():
                logging.debug(
                    f"Reading chunk of size {pretty_size(len(chunk))} for blob: {entity.blob_url} at {dt.now()}"
                )
                md5_hash.update(chunk)

            ret.state = FinalResultCode.FIXITY_FINISHED
            ret.blob_size = props.size
            ret.checksum = md5_hash.hexdigest()
    except ValueError as ex:
        ret.state = FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS
        ret.error_desc = f"Invalid blob URL: {entity.blob_url}. {ex}"
    except ResourceNotFoundError as ex:
        ret.state = FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS
        ret.error_desc = f"Invalid blob URL: {entity.blob_url}. {ex}"
    except Exception as ex:
        ret.state = FinalResultCode.COMMON_ERROR
        ret.error_desc = f"{ex}"
    finally:
        if blob_client:
            blob_client.close()

    return ret
