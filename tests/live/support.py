from __future__ import annotations

import json
import threading
from pathlib import Path


class RequestBudget:
    def __init__(self, limit: int):
        if not 1 <= limit <= 100:
            raise ValueError("request limit must be between 1 and 100")
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def before_request(self, request):
        if request.url.scheme != "https" or request.url.host != "openrouter.ai":
            raise RuntimeError("live provider tests may only contact HTTPS OpenRouter")
        with self._lock:
            if self.used >= self.limit:
                raise RuntimeError("live provider request budget exhausted")
            self.used += 1

    async def before_async_request(self, request):
        self.before_request(request)


def load_corpus(documents_path: Path, dataset_path: Path):
    documents = json.loads(documents_path.read_text(encoding="utf-8"))
    records = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(documents, list) or not 2 <= len(documents) <= 10:
        raise ValueError("provide 2 to 10 documents")
    if not isinstance(records, list) or not 1 <= len(records) <= 3:
        raise ValueError("provide 1 to 3 evaluation records for the smoke test")
    ids = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("each document must be an object")
        identifier = document.get("id")
        text = document.get("text")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("document ids must be nonempty and unique")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("document text must contain 1 to 2000 characters")
        ids.add(identifier)
    example_ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each evaluation record must be an object")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in example_ids:
            raise ValueError("example ids must be nonempty and unique")
        example_ids.add(identifier)
        for field in ("query", "reference_answer"):
            value = record.get(field)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 1000:
                raise ValueError(f"{field} must contain 1 to 1000 characters")
        relevant = record.get("relevant_document_ids")
        if (
            not isinstance(relevant, list)
            or not relevant
            or any(not isinstance(value, str) or value not in ids for value in relevant)
        ):
            raise ValueError("relevant_document_ids must reference supplied documents")
    return documents, records
