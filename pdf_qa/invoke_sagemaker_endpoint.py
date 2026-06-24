"""
Invokes the SageMaker Serverless Inference endpoint to get a real embedding
back from AWS-hosted infrastructure, using temporary credentials from
assuming ingest_role (which has sagemaker:InvokeEndpoint permission).

Usage:
    python invoke_sagemaker_endpoint.py "some text to embed"
"""

import json
import sys

import config
import aws_storage


def invoke_endpoint(text: str):
    print("Assuming ingest_role for SageMaker endpoint access ...")
    session = aws_storage._assume_role(config.INGEST_ROLE_ARN, "pdfqa-sagemaker-invoke-session")
    runtime_client = session.client("sagemaker-runtime")

    payload = {"inputs": text}
    print("Invoking endpoint 'pdfqa-embedding-endpoint' ...")
    print("(First invocation after idle may take 10-60s -- cold start.)")

    response = runtime_client.invoke_endpoint(
        EndpointName="pdfqa-embedding-endpoint",
        ContentType="application/json",
        Body=json.dumps(payload),
    )

    result = json.loads(response["Body"].read().decode("utf-8"))
    embedding = result["embeddings"][0]

    print(f"\nReceived embedding vector with {len(embedding)} dimensions.")
    print(f"First 5 values: {embedding[:5]}")
    return embedding


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "This is a test sentence."
    invoke_endpoint(text)
