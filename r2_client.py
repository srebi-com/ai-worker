import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import boto3
from botocore.config import Config


@dataclass
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str


def load_r2_config() -> R2Config:
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    bucket = os.environ.get("R2_BUCKET", "srebi-incidents")

    if not account_id or not access_key_id or not secret_access_key:
        raise RuntimeError("Missing R2 environment variables.")

    return R2Config(
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket=bucket,
    )


def build_client(config: R2Config):
    endpoint = f"https://{config.account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


class R2Client:
    def __init__(self, config: R2Config) -> None:
        self.config = config
        self.client = build_client(config)

    def get_json(self, key: str) -> Optional[dict[str, Any]]:
        try:
            response = self.client.get_object(Bucket=self.config.bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception:
            return None

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.client.put_object(
            Bucket=self.config.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )

    def download(self, key: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.client.download_file(self.config.bucket, key, local_path)

    def upload(self, local_path: str, key: str, content_type: str) -> None:
        self.client.upload_file(
            local_path,
            self.config.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
