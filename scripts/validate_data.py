#!/usr/bin/env python3
"""Validate repository data, source coverage, and local Markdown links."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ERRORS: list[str] = []


def load_list(name: str) -> list[dict]:
    path = DATA / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ERRORS.append(f"{path.relative_to(ROOT)}: cannot parse JSON: {exc}")
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        ERRORS.append(f"{path.relative_to(ROOT)}: expected a list of objects")
        return []
    return value


def require_fields(label: str, records: list[dict], fields: set[str]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        record_id = record.get("id")
        where = f"{label}[{index}]"
        if not isinstance(record_id, str) or not record_id.strip():
            ERRORS.append(f"{where}: missing non-empty id")
        elif record_id in seen:
            ERRORS.append(f"{where}: duplicate id {record_id}")
        else:
            seen.add(record_id)
        missing = sorted(field for field in fields if record.get(field) in (None, "", []))
        if missing:
            ERRORS.append(f"{where}: missing required fields: {', '.join(missing)}")


def validate_urls(label: str, records: list[dict]) -> None:
    for record in records:
        values = record.get("source_urls", [])
        if record.get("url"):
            values = [*values, record["url"]]
        for value in values:
            parsed = urlsplit(value) if isinstance(value, str) else None
            if not parsed or parsed.scheme != "https" or not parsed.netloc:
                ERRORS.append(f"{label}/{record.get('id', '?')}: invalid HTTPS source URL {value!r}")


def source_keys(record: dict) -> set[str]:
    keys: set[str] = set()
    for field in ("doi", "pmid", "pmcid"):
        value = record.get(field)
        if value:
            keys.add(f"{field}:{str(value).strip().lower()}")
    urls = record.get("source_urls", [])
    if record.get("url"):
        urls = [*urls, record["url"]]
    for value in urls:
        if isinstance(value, str):
            keys.add(f"url:{value.rstrip('/').lower()}")
    return keys


def validate_source_coverage(records: list[dict], registry: list[dict]) -> None:
    registry_keys = [source_keys(item) for item in registry]
    for record in records:
        keys = source_keys(record)
        if not any(keys & candidate for candidate in registry_keys):
            ERRORS.append(f"{record.get('id', '?')}: no matching entry in data/source-registry.json")


def validate_markdown_links() -> None:
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            target = target.strip().split(" ", 1)[0].strip("<>")
            if not target or target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            local = (path.parent / target.split("#", 1)[0]).resolve()
            try:
                local.relative_to(ROOT)
            except ValueError:
                ERRORS.append(f"{path.relative_to(ROOT)}: link escapes repository: {target}")
                continue
            if not local.exists():
                ERRORS.append(f"{path.relative_to(ROOT)}: missing local link target: {target}")


def main() -> int:
    publications = load_list("publications.json")
    regulatory = load_list("regulatory.json")
    registry = load_list("source-registry.json")

    require_fields(
        "publications",
        publications,
        {"id", "title", "year", "domain", "topic", "evidence_role", "source_urls", "verification_status"},
    )
    require_fields(
        "regulatory",
        regulatory,
        {"id", "title", "authority", "domain", "topic", "evidence_role", "source_urls", "verification_status"},
    )
    require_fields(
        "source-registry",
        registry,
        {"id", "source_type", "title", "url", "domains", "topics", "verification_status"},
    )
    validate_urls("publications", publications)
    validate_urls("regulatory", regulatory)
    validate_urls("source-registry", registry)
    validate_source_coverage([*publications, *regulatory], registry)
    validate_markdown_links()

    if ERRORS:
        print("Validation failed:", file=sys.stderr)
        for error in ERRORS:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Validated "
        f"{len(publications)} publications, {len(regulatory)} regulatory records, "
        f"{len(registry)} source-registry entries, and local Markdown links."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
