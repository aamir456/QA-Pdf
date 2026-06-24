"""
AWS integration layer: assumes the least-privilege IAM roles created by
Terraform (infra/iam.tf), then uses the resulting temporary credentials
for S3 calls.

This is the one file that talks to AWS directly. ingest.py and query.py
call the functions here without knowing or caring about STS, credential
expiry, or boto3 session details — same separation-of-concerns principle
as vector_store.py for ChromaDB.

Why role assumption instead of just using `aws configure` credentials
directly: your IAM user (aamir-terraform) has AdministratorAccess, because
Terraform needs broad power to provision infrastructure. Application code
should never run with that power. Assuming a role scopes every S3 call
down to exactly what that role's policy allows -- ingest_role cannot
delete objects, query_role cannot touch raw_pdfs at all, etc. If this
script had a bug or a leaked credential, the damage is capped by the
role's policy, not by what your IAM user could do.
"""

import json
import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

import config


def _assume_role(role_arn: str, session_name: str):
    """
    Calls sts:AssumeRole using your default AWS CLI credentials, and returns
    a boto3 Session backed by the temporary credentials that role grants.
    Temporary credentials expire after config.ASSUME_ROLE_SESSION_SECONDS;
    a fresh call to this function is needed after that (each ingest/query
    run calls this once, so expiry is not a concern in normal use).
    """
    sts_client = boto3.client("sts", region_name=config.AWS_REGION)
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=config.ASSUME_ROLE_SESSION_SECONDS,
        )
    except NoCredentialsError:
        print("No AWS credentials found. Run 'aws configure' first.")
        sys.exit(1)
    except ClientError as e:
        print(f"Failed to assume role {role_arn}: {e}")
        print("Check that the role exists (terraform apply completed) and")
        print("that your IAM user is listed as a trusted principal in its trust policy.")
        sys.exit(1)

    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=config.AWS_REGION,
    )


def get_ingest_s3_client():
    """Returns an S3 client using temporary credentials scoped to ingest_role."""
    if not config.INGEST_ROLE_ARN:
        print("PDFQA_INGEST_ROLE_ARN is not set. Run 'terraform output' in infra/")
        print("and set it as an environment variable.")
        sys.exit(1)
    session = _assume_role(config.INGEST_ROLE_ARN, "pdfqa-ingest-session")
    return session.client("s3")


def get_query_s3_client():
    """Returns an S3 client using temporary credentials scoped to query_role."""
    if not config.QUERY_ROLE_ARN:
        print("PDFQA_QUERY_ROLE_ARN is not set. Run 'terraform output' in infra/")
        print("and set it as an environment variable.")
        sys.exit(1)
    session = _assume_role(config.QUERY_ROLE_ARN, "pdfqa-query-session")
    return session.client("s3")


def upload_pdf(s3_client, pdf_path, bucket=None):
    """Uploads a local PDF file to the raw-pdfs bucket, server-side encrypted via the bucket's default KMS key."""
    bucket = bucket or config.RAW_PDFS_BUCKET
    key = pdf_path.name
    try:
        s3_client.upload_file(str(pdf_path), bucket, key)
    except ClientError as e:
        print(f"Failed to upload {pdf_path.name} to s3://{bucket}/{key}: {e}")
        raise
    return f"s3://{bucket}/{key}"


def upload_chunks(s3_client, pdf_filename, chunk_records, bucket=None):
    """
    Uploads chunk text + metadata as a single JSON file to the chunks bucket,
    one JSON file per source PDF: <pdf_filename>.chunks.json

    chunk_records: list of {"id": ..., "text": ..., "metadata": {...}}
    """
    bucket = bucket or config.CHUNKS_BUCKET
    key = f"{pdf_filename}.chunks.json"
    body = json.dumps(chunk_records, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    except ClientError as e:
        print(f"Failed to upload chunks for {pdf_filename} to s3://{bucket}/{key}: {e}")
        raise
    return f"s3://{bucket}/{key}"


def list_chunk_files(s3_client, bucket=None):
    """Lists all chunk JSON files in the chunks bucket."""
    bucket = bucket or config.CHUNKS_BUCKET
    try:
        response = s3_client.list_objects_v2(Bucket=bucket)
    except ClientError as e:
        print(f"Failed to list objects in s3://{bucket}: {e}")
        raise
    return [obj["Key"] for obj in response.get("Contents", [])]


def download_chunk_file(s3_client, key, bucket=None):
    """Downloads and parses a single chunk JSON file from the chunks bucket."""
    bucket = bucket or config.CHUNKS_BUCKET
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        print(f"Failed to download s3://{bucket}/{key}: {e}")
        raise
    body = response["Body"].read().decode("utf-8")
    return json.loads(body)
