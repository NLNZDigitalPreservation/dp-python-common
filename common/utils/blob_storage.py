import hashlib
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from azure.storage.blob import (BlobClient, BlobProperties, BlobServiceClient,
                                ContentSettings)

# from azure.core.pipeline.transport import RequestsTransport


@dataclass
class BlobPropertiesDTO:
    blob_name: str
    container: str
    blob_tier: Optional[str] = None
    content_md5: Optional[str] = None
    content_type: Optional[str] = None
    content_disposition: Optional[str] = None


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Open the file in binary mode and read it in chunks
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)

    # Return the hexadecimal digest
    return md5_hash.hexdigest()


class BlobStorageAccess:
    def __init__(self, args):
        self.connection_string = args.connection_string
        self.container_name = args.container_name
        self.credential = args.account_key

        # Create a BlobServiceClient
        self.blob_service_client = None
        # Get the container client
        self.container_client = None

    def init(self, connection_string, container_name):
        # transport = RequestsTransport(verify=False)
        # transport = (transport,)
        # Create a BlobServiceClient
        # connection_verify=self._blob_client_kwargs(),
        self.blob_service_client = BlobServiceClient.from_connection_string(
            conn_str=connection_string, connection_verify=False
        )

        # Get the container client
        self.container_client = self.blob_service_client.get_container_client(
            container_name
        )
        is_container_exists = self.container_client.exists()
        if not is_container_exists:
            self.container_client.create_container()

    def get_all_blob_properties(self):
        ret = []
        # Get the blob client
        blobs = self.container_client.list_blobs()
        for blob in blobs:
            if blob.content_settings.content_md5 is not None:
                content_md5 = blob.content_settings.content_md5.hex()
            else:
                content_md5 = ""
            dto = BlobPropertiesDTO(
                blob_name=blob.name,
                container=blob.container,
                blob_tier=blob.blob_tier,
                content_md5=content_md5,
                content_type=blob.content_settings.content_type,
                content_disposition=blob.content_settings.content_disposition,
            )
            ret.append(asdict(dto))
        return ret

    def get_blob_data(self, blob_name):
        # Get the blob client
        blob_client = self.container_client.get_blob_client(blob_name)
        stream = blob_client.download_blob()
        content = stream.readall()
        print(f"content length: {len(content)}")
        blob_client.close()

    def get_blob_properties(self, blob_name=None, blob_url=None):
        if blob_name is None and blob_url is None:
            raise RuntimeError(f"Either blob_name or blob_url is empty")

        if blob_name is not None and blob_url is not None:
            raise RuntimeError(f"Either blob_name or blob_url is valued")

        # Get the blob client
        if blob_name is not None:
            blob_client = self.container_client.get_blob_client(blob_name)
        else:
            blob_client = BlobClient.from_blob_url(
                blob_url, credential=self.credential, **self._blob_client_kwargs()
            )

        properties: BlobProperties = blob_client.get_blob_properties()
        print(properties)

        blob_client.close()
        return properties

    def get_blob_md5(self, blob_name):
        properties: BlobProperties = self.get_blob_properties(blob_name)
        content_md5 = properties.content_settings.content_md5
        # content_md5_str = base64.b64encode(content_md5).decode('utf-8')
        content_md5_str = content_md5.hex()
        print(content_md5_str)
        return content_md5_str

    def put_blob_data(
        self, blob_name, data, content_type=None, content_encoding=None, filename=None
    ):
        # Get the blob client
        blob_client = self.container_client.get_blob_client(blob_name)
        if blob_client.exists():
            print(f"blob does exist: {blob_name}")
            return

        content_settings = ContentSettings()
        if content_type is not None:
            content_settings.content_type = content_type
        if content_encoding is not None:
            content_settings.content_encoding = content_encoding
        if filename is not None:
            content_settings.content_disposition = f'attachment; filename="{filename}"'

        md5_hash = hashlib.md5()
        for chunk in iter(lambda: data.read(4096), b""):
            md5_hash.update(chunk)
        content_settings.content_md5 = md5_hash.digest()

        try:
            data.seek(0)
        except Exception:
            pass

        try:
            blob_client.upload_blob(data, content_settings=content_settings, timeout=30)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        finally:
            blob_client.close()

        logging.info(f"Upload data to {self.container_name}")

    def put_blob_file(self, blob_name, file_path):
        filename = Path(file_path).name
        with open(file_path, "rb") as data:
            # data = io.BufferedReader(fp)
            self.put_blob_data(blob_name=blob_name, data=data, filename=filename)
        print(f"Upload {file_path} to {self.container_name}")

    def delete_blob(self, blob_name):
        # Get the blob client
        blob_client = self.container_client.get_blob_client(blob_name)
        if blob_client.exists():
            blob_client.delete_blob()


if __name__ == "__main__":
    bs_access = BlobStorageAccess(
        connection_string="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://localhost:10000/devstoreaccount1;",
        container_name="fixity-dev",
    )

    test_blob_name = "xyz"
    test_file_path = "/tmp/xxyyzz.txt"

    bs_access.delete_blob(test_blob_name)

    bs_access.put_blob_file(blob_name=test_blob_name, file_path=test_file_path)

    bs_access.get_blob_md5(test_blob_name)

    bs_access.get_blob_data(test_blob_name)

    md5 = calculate_md5(file_path=test_file_path)
    print(md5)

    bs_access.get_all_blob_properties()
