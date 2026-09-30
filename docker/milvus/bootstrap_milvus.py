"""Create and seed the Milvus collection used by the customer-service app."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pymilvus import DataType, Function, FunctionType, MilvusClient


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid JSONL at line {line_no}: {exc}") from exc
    return rows


def _connect(host: str, port: int) -> MilvusClient:
    deadline = time.time() + _env_int("MILVUS_SEED_WAIT_SECONDS", 120)
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            client = MilvusClient(uri=f"http://{host}:{port}")
            client.list_collections()
            return client
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(3)
    raise RuntimeError(f"Milvus is not ready at {host}:{port}: {last_error}")


def _create_collection(client: MilvusClient, name: str, dim: int) -> None:
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
    schema.add_field("kb_id", DataType.VARCHAR, max_length=64)
    schema.add_field("product_id", DataType.VARCHAR, max_length=128)
    schema.add_field(
        "content",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params={"type": "chinese"},
    )
    schema.add_field("source", DataType.VARCHAR, max_length=512)
    schema.add_field("category", DataType.VARCHAR, max_length=128)
    schema.add_field("parent_id", DataType.VARCHAR, max_length=256)
    schema.add_field("chunk_index", DataType.INT32)
    schema.add_field("doc_version", DataType.INT64)
    schema.add_field("is_current", DataType.BOOL, default_value=True)
    schema.add_field("mushroom_type", DataType.VARCHAR, max_length=128)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR, is_function_output=True)
    schema.add_function(
        Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names=["sparse"],
        )
    )

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_name="embedding",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )
    index_params.add_index(
        field_name="sparse",
        index_name="sparse",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
        params={"bm25_k1": 1.2, "bm25_b": 0.75},
    )
    client.create_collection(collection_name=name, schema=schema, index_params=index_params)


def main() -> None:
    host = os.getenv("MILVUS_HOST", "127.0.0.1")
    port = _env_int("MILVUS_PORT", 19530)
    collection = os.getenv("MILVUS_TEXT_COLLECTION", "mushroom_knowledge")
    dim = _env_int("MILVUS_DIM", 512)
    seed_path = Path(
        os.getenv("MILVUS_SEED_PATH", "/app/docker/milvus/mushroom_knowledge.jsonl")
    )

    client = _connect(host, port)
    existing = set(client.list_collections())
    if collection in existing:
        stats = client.get_collection_stats(collection)
        count = int(stats.get("row_count", 0) or 0)
        if count > 0:
            print(f"[milvus-seed] {collection} already contains {count} rows; skipping")
            return
        client.drop_collection(collection)

    rows = _load_rows(seed_path)
    if not rows:
        raise RuntimeError(f"Milvus seed file is empty: {seed_path}")

    print(f"[milvus-seed] creating {collection} with {len(rows)} rows from {seed_path}")
    _create_collection(client, collection, dim)

    batch_size = _env_int("MILVUS_SEED_BATCH_SIZE", 100)
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        client.insert(collection_name=collection, data=batch)
        print(f"[milvus-seed] inserted {min(start + batch_size, len(rows))}/{len(rows)}")

    client.flush(collection)
    client.load_collection(collection)
    stats = client.get_collection_stats(collection)
    print(f"[milvus-seed] complete: {stats}")


if __name__ == "__main__":
    main()
