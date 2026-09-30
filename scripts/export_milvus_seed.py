"""Export a Milvus collection to JSONL for the Docker bootstrap service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pymilvus import Collection, connections


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"unsupported value: {type(value).__name__}")


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if key == "sparse":
            continue
        if key == "embedding" and isinstance(value, list):
            result[key] = [round(float(item), 8) for item in value]
        else:
            result[key] = value
    return result


def export_collection(
    *,
    host: str,
    port: int,
    collection_name: str,
    output: Path,
) -> int:
    connections.connect(alias="seed_export", host=host, port=str(port))
    collection = Collection(collection_name, using="seed_export")
    fields = [
        field.name
        for field in collection.schema.fields
        if field.name != "sparse"
    ]
    if "id" not in fields:
        raise RuntimeError("collection does not have an id field")

    output.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    offset = 0
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        while True:
            rows = collection.query(
                expr='id != ""',
                output_fields=fields,
                limit=500,
                offset=offset,
            )
            if not rows:
                break
            for row in rows:
                handle.write(
                    json.dumps(
                        _compact_row(row),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=_json_default,
                    )
                )
                handle.write("\n")
            exported += len(rows)
            offset += len(rows)
            print(f"exported {exported}/{collection.num_entities}")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19531)
    parser.add_argument("--collection", default="mushroom_knowledge")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docker/milvus/mushroom_knowledge.jsonl"),
    )
    args = parser.parse_args()
    count = export_collection(
        host=args.host,
        port=args.port,
        collection_name=args.collection,
        output=args.output,
    )
    print(f"exported {count} rows to {args.output}")


if __name__ == "__main__":
    main()
