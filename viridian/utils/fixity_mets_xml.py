import os

import xmltodict
from azure.core.exceptions import AzureError, ResourceNotFoundError
from metadata import (
    AmdInfo,
    EntityInfo,
    FinalResultCode,
    FixityResult,
    MetsFixityResult,
)
from utils.blob_storage import DEFAULT_CONN_STR, build_blob_client

DEFAULT_CHECKSUM_TYPE = "MD5"


def xml_file_to_dict(xml_file: str):
    with open(xml_file, "r") as fp:
        xml_data = fp.read()
        return xmltodict.parse(xml_data)


class MetsXmlParser:
    def __init__(self):
        self.result = []

    def _parse_dict_by_key(self, key, node, target_key):
        if node is None:
            return

        if key == target_key:
            if isinstance(node, list):
                self.result.extend(node)
            else:
                self.result.append(node)

        if isinstance(node, dict):

            for temp_key in node:
                self._parse_dict_by_key(temp_key, node[temp_key], target_key)

        if isinstance(node, list):
            for sub_node in node:
                self._parse_dict_by_key("", sub_node, target_key)

    def parse_dict_by_key(self, node, target_key):
        self.result = []
        self._parse_dict_by_key("", node, target_key)
        ret = list(self.result)
        self.result = []
        return ret


def extract_fixity_value_from_amd_sec(
    records, target_checksum_type=DEFAULT_CHECKSUM_TYPE
):
    for record in records:
        if "key" not in record:
            continue
        # -----------------------------------------------------------:Example-----
        # "key": [
        #     {
        #         "@id": "objectType",
        #         "#text": "FILE"
        #     },
        #     {
        #         "@id": "creationDate",
        #         "#text": "2025-02-11 11:08:24"
        #     },
        #     {
        #         "@id": "createdBy",
        #         "#text": "NLNZNewspaper"
        #     },
        #     {
        #         "@id": "modificationDate",
        #         "#text": "2025-02-11 11:24:44"
        #     },
        #     {
        #         "@id": "modifiedBy",
        #         "#text": "NLNZNewspaper"
        #     },
        #     {
        #         "@id": "owner",
        #         "#text": "CRS00.INS00.DPR00"
        #     }
        # ]
        #############################################################################
        key_ary = record["key"]

        section = {}
        for item in key_ary:
            if "@id" not in item or "#text" not in item:
                continue
            section[item["@id"]] = item["#text"]

        if (
            "fixityType" in section
            and section["fixityType"] == target_checksum_type
            and "fixityValue" in section
        ):
            return section["fixityValue"]
    return None


# This class takes a METS file in XML format and breaks it up
# to get a set of entities (files) with MD5 sums
# The METS standard was _not_ designed to be easy to parse
# what we do is to convert a mets.xml to json and extract by keys:
# 1. Extract the amd sections, it should be an array contains lots of record sections
# 2. Extract the record sections, it should be an array contains lots of key sections
# 3. Extract the key sections, it should be an array contains lots of items
# 4. Convert the key array to a dict, then we can extract the fixity value from the dict
def _parse_mets_xml(xml_data):
    coll_mets_file = []
    data_dict = xmltodict.parse(xml_data)
    parser = MetsXmlParser()
    mets_amd_sec = parser.parse_dict_by_key(data_dict, "mets:amdSec")
    # print(mets_amd_sec)
    for amd in mets_amd_sec:
        records = parser.parse_dict_by_key(amd, "record")
        # print(records)
        fixity_value = extract_fixity_value_from_amd_sec(
            records=records, target_checksum_type=DEFAULT_CHECKSUM_TYPE
        )
        if fixity_value is None:
            continue

        # The ID looks like: 'FL41360797-amd'
        amd_id = str(amd["@ID"]).replace("-amd", "")
        amd_info = AmdInfo(
            amd_id=amd_id, checksum_type=DEFAULT_CHECKSUM_TYPE, checksum=fixity_value
        )

        coll_mets_file.append(amd_info.to_dict())

    return coll_mets_file


def parse_mets_xml(entity: EntityInfo):
    managed_identity_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID", None)
    if managed_identity_client_id is None:
        connection_string = os.environ.get(
            "RosettaBlobConnectionString", DEFAULT_CONN_STR
        )
    else:
        connection_string = None

    ret = MetsFixityResult(
        id=entity.id,
        blob_url=entity.blob_url,
        state=FinalResultCode.COMMON_ERROR,
    )

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
            mets_content = blob_client.download_blob().readall()
            coll = _parse_mets_xml(mets_content)

            ret.state = FinalResultCode.FIXITY_FINISHED
            ret.coll = coll
    except ValueError as ex:
        ret.state = FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS
        ret.error_desc = f"Invalid blob URL: {entity.blob_url}. {ex}"
    except ResourceNotFoundError as ex:
        ret.state = FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS
        ret.error_desc = f"Blob not found: {entity.blob_url}. {ex}"
    except Exception as ex:
        ret.state = FinalResultCode.COMMON_ERROR
        ret.error_desc = f"{ex}"
    finally:
        if blob_client:
            blob_client.close()

    return ret
