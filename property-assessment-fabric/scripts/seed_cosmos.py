from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.cosmos import CosmosClient
from azure.identity import AzureCliCredential, DefaultAzureCredential


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    try:
        credential = AzureCliCredential()
        credential.get_token("https://cosmos.azure.com/.default")
    except Exception:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    container = CosmosClient(args.endpoint, credential=credential).get_database_client(args.database).get_container_client(args.container)
    records = json.loads(args.file.read_text(encoding="utf-8"))
    for record in records:
        container.upsert_item(record)
    print(f"Upserted {len(records)} synthetic property profiles.")


if __name__ == "__main__":
    main()

