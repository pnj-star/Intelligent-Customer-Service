"""检查 Milvus 集合 schema 与租户数据，定位 RAG 检索为空的原因。

用法：python scripts/check_milvus.py [collection_name]
"""

from __future__ import annotations

import json
import sys

from pymilvus import Collection, connections


def main() -> None:
    collection_name = sys.argv[1] if len(sys.argv) > 1 else "mushroom_knowledge"
    connections.connect(host="127.0.0.1", port=19531)
    collection = Collection(collection_name)
    print("schema fields:", [field.name for field in collection.schema.fields])
    print("num_entities:", collection.num_entities)
    for expr in ('tenant_id != ""', 'id != ""'):
        try:
            rows = collection.query(expr=expr, output_fields=["tenant_id", "kb_id", "content"], limit=5)
        except Exception as exc:  # noqa: BLE001
            print(f"query {expr!r} failed: {type(exc).__name__}: {exc}")
            continue
        print(f"query {expr!r} rows:")
        for row in rows:
            compact = {
                key: (str(value)[:80] if isinstance(value, str) else value)
                for key, value in row.items()
            }
            print(json.dumps(compact, ensure_ascii=False))
        break


if __name__ == "__main__":
    main()
