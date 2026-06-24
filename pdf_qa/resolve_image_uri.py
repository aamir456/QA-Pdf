"""
Resolves the correct Hugging Face inference container image URI for your
AWS region, using the official SageMaker Python SDK's lookup function
rather than a hardcoded URI (container versions/tags change over time,
and hardcoding risks using a stale or wrong one).

Usage:
    pip install sagemaker
    python resolve_image_uri.py
"""

from sagemaker import image_uris

REGION = "eu-central-1"

# A recent, well-supported combination as of when this was written.
# If this specific combination isn't available, the error message from
# image_uris.retrieve will list valid alternatives -- read it, it's helpful.
PYTORCH_VERSION = "2.1.0"
TRANSFORMERS_VERSION = "4.37.0"
PY_VERSION = "py310"

uri = image_uris.retrieve(
    framework="huggingface",
    base_framework_version=f"pytorch{PYTORCH_VERSION}",
    region=REGION,
    version=TRANSFORMERS_VERSION,
    py_version=PY_VERSION,
    instance_type="ml.m5.large",  # serverless inference has no GPU, CPU image only
    image_scope="inference",
)

print(f"Resolved image URI for {REGION}:")
print(uri)
print("\nCopy this exact string into infra/sagemaker.tf as the container image value.")
