"""
Builds model.tar.gz for SageMaker deployment: downloads the real
all-MiniLM-L6-v2 model files, combines them with the custom inference
code, and packages everything into the exact directory structure
SageMaker's Hugging Face container expects:

    model.tar.gz/
    ├── config.json, model.safetensors, tokenizer files, etc.
    └── code/
        ├── inference.py
        └── requirements.txt

This structure was verified against AWS/community reference examples
before being used here -- code/ must sit at the top level of the
archive, not nested inside another folder.

Usage:
    python build_sagemaker_package.py
"""

import shutil
import tarfile
from pathlib import Path

from transformers import AutoTokenizer, AutoModel

BUILD_DIR = Path("sagemaker_build")
OUTPUT_TARBALL = Path("model.tar.gz")


def main():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir()
    (BUILD_DIR / "code").mkdir()

    print("Downloading all-MiniLM-L6-v2 model files from Hugging Face ...")
    tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
    model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
    tokenizer.save_pretrained(str(BUILD_DIR))
    model.save_pretrained(str(BUILD_DIR))
    print("  Model files saved.")

    print("Copying inference code ...")
    shutil.copy("sagemaker_inference_code/inference.py", BUILD_DIR / "code" / "inference.py")
    shutil.copy("sagemaker_inference_code/requirements.txt", BUILD_DIR / "code" / "requirements.txt")

    print(f"Building {OUTPUT_TARBALL} ...")
    if OUTPUT_TARBALL.exists():
        OUTPUT_TARBALL.unlink()

    with tarfile.open(OUTPUT_TARBALL, "w:gz") as tar:
        for item in BUILD_DIR.iterdir():
            tar.add(item, arcname=item.name)

    size_mb = OUTPUT_TARBALL.stat().st_size / (1024 * 1024)
    print(f"\nDone. {OUTPUT_TARBALL} created ({size_mb:.1f} MB).")

    print("\nVerifying internal structure ...")
    with tarfile.open(OUTPUT_TARBALL, "r:gz") as tar:
        names = tar.getnames()
        has_code_dir = any(n.startswith("code/") or n == "code" for n in names)
        has_config = any("config.json" in n for n in names)
        print(f"  code/ present at top level: {has_code_dir}")
        print(f"  config.json present: {has_config}")
        if not (has_code_dir and has_config):
            print("  WARNING: structure looks wrong, check before uploading to S3.")
        else:
            print("  Structure looks correct.")

    shutil.rmtree(BUILD_DIR)


if __name__ == "__main__":
    main()
