"""YAML 규제 체크리스트 로딩."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ChecklistItem:
    id: str
    category: str
    title: str
    requirement: str
    reference: str
    source_file: str
    notes: str = ""


def load_checklist(path: str | Path) -> list[ChecklistItem]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))

    items: list[ChecklistItem] = []
    for category_block in data.get("categories", []):
        category = category_block["name"]
        for raw in category_block.get("items", []):
            items.append(
                ChecklistItem(
                    id=raw["id"],
                    category=category,
                    title=raw["title"],
                    requirement=raw["requirement"],
                    reference=raw.get("reference", ""),
                    notes=raw.get("notes", ""),
                    source_file=p.name,
                )
            )
    return items


def load_checklists(paths: list[str | Path]) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    seen_ids: set[str] = set()
    for path in paths:
        for item in load_checklist(path):
            if item.id in seen_ids:
                raise ValueError(
                    f"체크리스트 항목 ID 중복: '{item.id}' ({item.source_file})"
                )
            seen_ids.add(item.id)
            items.append(item)
    return items
