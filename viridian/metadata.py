import enum
import json
from dataclasses import asdict, dataclass
from typing import Optional

DEFAULT_FIXITY_TYPE = "MD5"
DEFAULT_CONTAINER_NAME = "fixity-dev"
FIXITY_CONTAINER_NAME = "fixity-persistent"
DELIMITER = b"\r\n"


class AzureFuncNames:
    BLOB_EVENT_QUEUE = "fixity-event-output-queue"
    HTTP_QUERY_PROPERTY = "fixity/query_property"
    HTTP_BATCH_STARTER = "fixity/batch_processor"
    HTTP_SINGLE_STARTER_FILE = "fixity/single_processor_file"
    HTTP_SINGLE_STARTER_METS = "fixity/single_processor_mets"
    HTTP_ORCHESTRATOR_DELETE = "fixity/orchestrator_delete"
    BLOB_CONTAINER_FAN_IN = "fixity-fan-in"
    BLOB_CONTAINER_FAN_OUT = "fixity-fan-out"
    QUEUE_BATCH_INPUT = "fixity-batch-input-queue"
    QUEUE_BATCH_OUTPUT = "fixity-batch-output-queue"
    QUEUE_SINGLE_INPUT = "fixity-single-input-queue"
    QUEUE_SINGLE_OUTPUT = "fixity-single-output-queue"


class FinalResultCode:
    FIXITY_INITIALED = 100
    FIXITY_RUNNING = 101
    FIXITY_FINISHED = 102
    FILE_CHECKSUM_MATCH = 0
    FILE_CHECKSUM_NOT_MATCH = 1
    FILE_ENTRY_IN_DB_BUT_NOT_IN_FS = 2
    FILE_IO_ERROR = 3
    FILE_SIZE_NOT_MATCH = 4
    PARSE_METS_XML_ERROR = 5
    COMMON_ERROR = 6
    METS_CHECKSUM_MATCH = 7
    METS_CHECKSUM_NOT_MATCH = 8
    FILE_EXISTS_IN_METS_BUT_NOT_IN_DB = 9
    BLOB_EVENT_NOT_IN_DB = 10
    BLOB_DUPLICATED_IN_DB = 11
    BLOB_DUPLICATED_IN_EVENTS = 12
    EARLY_CHECK_FILE_SIZE_NOT_MATCH = 204
    EARLY_CHECK_COMMON_ERROR = 206
    EARLY_CHECK_BLOB_EVENT_NOT_IN_DB = 210
    EARLY_CHECK_BLOB_DUPLICATED_IN_DB = 211
    EARLY_CHECK_BLOB_DUPLICATED_IN_EVENTS = 212
    EARLY_CHECK_BLOB_MALFORMED_NAME = 213


FinalResultOptions = {
    FinalResultCode.FIXITY_INITIALED: "Initialed",
    FinalResultCode.FIXITY_RUNNING: "Running",
    FinalResultCode.FIXITY_FINISHED: "Finished",
    FinalResultCode.FILE_CHECKSUM_MATCH: "File checksum (calculated) the same as recorded in database",
    FinalResultCode.FILE_CHECKSUM_NOT_MATCH: "File checksum (calculated) different then recorded in database",
    FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS: "File entity exists in database but not in file system",
    FinalResultCode.FILE_IO_ERROR: "Error reading file from file system (I/O error)",
    FinalResultCode.FILE_SIZE_NOT_MATCH: "File size of the file stored on the file system is different than recorded in the database",
    FinalResultCode.PARSE_METS_XML_ERROR: "Error parsing XML: XML (IE Mets) is not valid",
    FinalResultCode.COMMON_ERROR: "System error",
    FinalResultCode.METS_CHECKSUM_MATCH: "The checksum as stated in the IE Mets filed matches that stored in the database",
    FinalResultCode.METS_CHECKSUM_NOT_MATCH: "The checksum as stated in the IE Mets filed does not match that stored in the database",
    FinalResultCode.FILE_EXISTS_IN_METS_BUT_NOT_IN_DB: "File exists in IE METs but not in the database",
    FinalResultCode.BLOB_EVENT_NOT_IN_DB: "Blob name not found in the database",
    FinalResultCode.BLOB_DUPLICATED_IN_DB: "Blob name duplicated in the database",
    FinalResultCode.BLOB_DUPLICATED_IN_EVENTS: "Blob name duplicated in the events",
    FinalResultCode.EARLY_CHECK_FILE_SIZE_NOT_MATCH: "Early check: File size of the file stored on the file system is different than recorded in the database",
    FinalResultCode.EARLY_CHECK_BLOB_EVENT_NOT_IN_DB: "Early check: Blob name not found in the database",
    FinalResultCode.EARLY_CHECK_COMMON_ERROR: "Early check: System error",
    FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_DB: "Early check: Blob name duplicated in the database",
    FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_EVENTS: "Early check: Blob name duplicated in the events",
    FinalResultCode.EARLY_CHECK_BLOB_MALFORMED_NAME: "Early check: Blob name is malformed",
}

FinalResultErrorFlag = {
    FinalResultCode.FIXITY_INITIALED: "Yes",
    FinalResultCode.FIXITY_RUNNING: "Yes",
    FinalResultCode.FIXITY_FINISHED: "No",
    FinalResultCode.FILE_CHECKSUM_MATCH: "No",
    FinalResultCode.FILE_CHECKSUM_NOT_MATCH: "Yes",
    FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS: "Yes",
    FinalResultCode.FILE_IO_ERROR: "Yes",
    FinalResultCode.FILE_SIZE_NOT_MATCH: "Yes",
    FinalResultCode.PARSE_METS_XML_ERROR: "Yes",
    FinalResultCode.COMMON_ERROR: "Yes",
    FinalResultCode.METS_CHECKSUM_MATCH: "No",
    FinalResultCode.METS_CHECKSUM_NOT_MATCH: "Yes",
    FinalResultCode.FILE_EXISTS_IN_METS_BUT_NOT_IN_DB: "Yes",
    FinalResultCode.BLOB_EVENT_NOT_IN_DB: "Yes",
    FinalResultCode.BLOB_DUPLICATED_IN_DB: "Yes",
    FinalResultCode.BLOB_DUPLICATED_IN_EVENTS: "Yes",
    FinalResultCode.EARLY_CHECK_FILE_SIZE_NOT_MATCH: "Yes",
    FinalResultCode.EARLY_CHECK_BLOB_EVENT_NOT_IN_DB: "Yes",
    FinalResultCode.EARLY_CHECK_COMMON_ERROR: "Yes",
    FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_DB: "Yes",
    FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_EVENTS: "Yes",
}


def _get_select_option(code):
    return {
        "label": f"[{code}] - {FinalResultOptions[code]}",
        "code": code,
    }


FinalResultGroup = [
    {
        "label": "Succeded Results",
        "code": "succeeded",
        "items": [
            _get_select_option(FinalResultCode.FILE_CHECKSUM_MATCH),
            _get_select_option(FinalResultCode.METS_CHECKSUM_MATCH),
        ],
    },
    {
        "label": "File Failures",
        "code": "failed",
        "items": [
            _get_select_option(FinalResultCode.FILE_CHECKSUM_NOT_MATCH),
            _get_select_option(FinalResultCode.FILE_ENTRY_IN_DB_BUT_NOT_IN_FS),
            _get_select_option(FinalResultCode.FILE_IO_ERROR),
            _get_select_option(FinalResultCode.FILE_SIZE_NOT_MATCH),
            _get_select_option(FinalResultCode.PARSE_METS_XML_ERROR),
            _get_select_option(FinalResultCode.COMMON_ERROR),
            _get_select_option(FinalResultCode.METS_CHECKSUM_NOT_MATCH),
            _get_select_option(FinalResultCode.FILE_EXISTS_IN_METS_BUT_NOT_IN_DB),
            _get_select_option(FinalResultCode.BLOB_EVENT_NOT_IN_DB),
            _get_select_option(FinalResultCode.EARLY_CHECK_FILE_SIZE_NOT_MATCH),
            _get_select_option(FinalResultCode.EARLY_CHECK_BLOB_EVENT_NOT_IN_DB),
            _get_select_option(FinalResultCode.EARLY_CHECK_COMMON_ERROR),
            _get_select_option(FinalResultCode.BLOB_DUPLICATED_IN_DB),
            _get_select_option(FinalResultCode.BLOB_DUPLICATED_IN_EVENTS),
            _get_select_option(FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_DB),
            _get_select_option(FinalResultCode.EARLY_CHECK_BLOB_DUPLICATED_IN_EVENTS),
        ],
    },
]


class FixityTaskState(enum.Enum):
    INITIALED = 0
    RUNNING = 1
    SUCCESS = 2
    FAILED = 5
    BROKEN = 9
    FINALIZING = 8
    ARCHIVED = 10
    REJECTED = 11
    CANCELED = 12

    @staticmethod
    def FINISHED_STATES_VALUES():
        return [
            FixityTaskState.FAILED.value,
            FixityTaskState.SUCCESS.value,
            FixityTaskState.ARCHIVED.value,
            FixityTaskState.REJECTED.value,
            FixityTaskState.CANCELED.value,
        ]


class FixityType(enum.Enum):
    PRELOAD = 0
    BLOB_EVENT = 1
    BAU = 2


class FixityEntityType(enum.Enum):
    FILE = 1
    METS = 2
    BLOB_EVENT = 3


@dataclass
class BlobPropertiesDTO:
    blob_name: str
    container: str
    blob_tier: str
    content_md5: str
    content_type: str
    content_disposition: str


@dataclass
class Pagination:
    rows: int
    offset: int


class TaskPeriodicType(enum.Enum):
    NON_PERIODIC = 0
    WEEKLY = 7
    FORTNIGHT = 14
    MONTHLY = 30
    BI_MONTHLY = 60
    QUARTERLY = 90
    HALF_YEARLY = 180
    ANNUALLY = 365


@dataclass
class EntityInfo:
    id: int
    blob_url: str
    blob_size: Optional[int] = None

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class FixityResult:
    id: int
    blob_url: str
    state: int
    error_desc: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class FileFixityResult(FixityResult):
    checksum: Optional[str] = None
    blob_size: Optional[int] = None

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class AmdInfo:
    amd_id: str
    checksum_type: str
    checksum: str

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class MetsFixityResult(FixityResult):
    coll: Optional[list[dict]] = None

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class BatchRequest:
    trans_id: str
    job_type: int
    req_url: str

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class BatchResponse:
    trans_id: str
    job_type: int
    rsp_url: str

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class SingleEntityInfo(EntityInfo):
    trans_id: Optional[str] = None
    job_type: Optional[int] = None


@dataclass
class SingleFileFixityResult(FileFixityResult):
    trans_id: Optional[str] = None
    job_type: Optional[int] = None


@dataclass
class SingleMetsFixityResult(MetsFixityResult):
    trans_id: Optional[str] = None
    job_type: Optional[int] = None


@dataclass
class HttpBatchRequest:
    trans_id: str
    job_type: int
    entities: list[dict]

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class HttpBatchResponse:
    trans_id: str
    job_type: int
    results: list[dict]

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())
