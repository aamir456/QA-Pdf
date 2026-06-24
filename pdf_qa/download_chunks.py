"""
Demonstrates the query-side IAM role in action: assumes query_role
(read-only on the chunks bucket, zero access to raw_pdfs) and downloads
all chunk JSON files from S3.

This is a deliberate proof point, separate from query.py, because it's
the clearest way to show the least-privilege boundary actually working:

    python download_chunks.py                 # works: query_role can read chunks
    python download_chunks.py --try-raw-pdfs   # fails on purpose: query_role
                                                # has no permission to touch
                                                # the raw_pdfs bucket at all

Usage:
    python download_chunks.py
    python download_chunks.py --try-raw-pdfs
"""

import argparse
import sys

import config
import aws_storage


def main():
    parser = argparse.ArgumentParser(description="Download chunk files from S3 using query_role credentials.")
    parser.add_argument(
        "--try-raw-pdfs",
        action="store_true",
        help="Deliberately attempt to list the raw_pdfs bucket with query_role credentials, to prove it's denied.",
    )
    args = parser.parse_args()

    print("Assuming query_role to obtain temporary AWS credentials ...")
    s3_client = aws_storage.get_query_s3_client()
    print("Role assumed successfully.\n")

    if args.try_raw_pdfs:
        print(f"Attempting to list s3://{config.RAW_PDFS_BUCKET} using query_role (this should be DENIED) ...")
        try:
            s3_client.list_objects_v2(Bucket=config.RAW_PDFS_BUCKET)
            print("  Unexpected: the call succeeded. Check that query_role's policy excludes raw_pdfs.")
        except Exception as e:
            print(f"  Denied, as expected: {e}")
            print("\n  This confirms least-privilege is enforced: query_role can read chunks")
            print("  but has zero access to the original PDFs, exactly as designed.")
        return

    print(f"Listing chunk files in s3://{config.CHUNKS_BUCKET} ...")
    keys = aws_storage.list_chunk_files(s3_client)

    if not keys:
        print("No chunk files found. Run 'python ingest.py --to-s3' first.")
        sys.exit(1)

    print(f"Found {len(keys)} chunk file(s):\n")
    total_records = 0
    for key in keys:
        records = aws_storage.download_chunk_file(s3_client, key)
        total_records += len(records)
        print(f"  {key} -> {len(records)} chunk records")
        if records:
            preview = records[0]["text"][:80].replace("\n", " ")
            print(f"    preview: {preview}...")

    print(f"\nTotal: {total_records} chunk records retrieved from S3 using query_role credentials.")


if __name__ == "__main__":
    main()
