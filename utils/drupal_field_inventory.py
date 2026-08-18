#!/usr/bin/env python3
"""Inventory tracked Drupal field tables from a SQL dump.

The parser is streaming so the 800+ MB production dump does not need to be
loaded into memory. Tracked table names come from drupal_to_hugo.py's mapping
constants, keeping this report aligned with the extractor.
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


TABLE_GROUPS = {
    "TEXT_FIELD_TABLES": "Text",
    "METADATA_FIELD_TABLES": "Metadata",
    "LINK_FIELD_TABLES": "Link",
    "FILE_FIELD_TABLES": "File",
    "REFERENCE_FIELD_TABLES": "Reference",
    "IMAGE_FIELD_TABLES": "Image",
}
CREATE_RE = re.compile(r"^CREATE TABLE `([^`]+)`")
COLUMN_RE = re.compile(r"^\s+`([^`]+)`")
INSERT_RE = re.compile(r"^INSERT INTO `([^`]+)` VALUES")
COMMON_COLUMNS = {"bundle", "deleted", "entity_id", "revision_id", "langcode", "delta"}


@dataclass
class TableInventory:
    table: str
    group: str
    columns: list[str] = field(default_factory=list)
    rows: int = 0

    @property
    def present(self) -> bool:
        return bool(self.columns)

    @property
    def value_columns(self) -> list[str]:
        return [column for column in self.columns if column not in COMMON_COLUMNS]


@dataclass
class InsertState:
    table: str
    depth: int = 0
    in_string: bool = False
    escape_next: bool = False


def load_tracked_tables(extractor_path: Path) -> dict[str, str]:
    """Read mapping literals without importing the dependency-heavy extractor."""
    tree = ast.parse(extractor_path.read_text(encoding="utf-8"))
    mappings: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in TABLE_GROUPS:
            mappings[target.id] = ast.literal_eval(node.value)

    missing = set(TABLE_GROUPS) - set(mappings)
    if missing:
        raise ValueError(f"Missing extractor mappings: {', '.join(sorted(missing))}")

    tracked: dict[str, str] = {}
    for constant, group in TABLE_GROUPS.items():
        for table in mappings[constant]:
            tracked[table] = group
    return tracked


def count_insert_rows(fragment: str, state: InsertState) -> tuple[int, bool]:
    """Count top-level SQL tuples and report whether the INSERT has ended."""
    rows = 0
    index = 0
    while index < len(fragment):
        char = fragment[index]
        if state.escape_next:
            state.escape_next = False
        elif state.in_string:
            if char == "\\":
                state.escape_next = True
            elif char == "'":
                if index + 1 < len(fragment) and fragment[index + 1] == "'":
                    index += 1
                else:
                    state.in_string = False
        elif char == "'":
            state.in_string = True
        elif char == "(":
            state.depth += 1
            if state.depth == 1:
                rows += 1
        elif char == ")":
            state.depth = max(0, state.depth - 1)
        elif char == ";" and state.depth == 0:
            return rows, True
        index += 1
    return rows, False


def inventory_dump(sql_path: Path, tracked: dict[str, str]) -> list[TableInventory]:
    inventories = {
        table: TableInventory(table=table, group=group)
        for table, group in tracked.items()
    }
    schema_table: str | None = None
    insert_state: InsertState | None = None

    with sql_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if insert_state is not None:
                rows, ended = count_insert_rows(line, insert_state)
                inventories[insert_state.table].rows += rows
                if ended:
                    insert_state = None
                continue

            if schema_table is not None:
                column_match = COLUMN_RE.match(line)
                if column_match:
                    inventories[schema_table].columns.append(column_match.group(1))
                if line.startswith(") ENGINE="):
                    schema_table = None
                continue

            create_match = CREATE_RE.match(line)
            if create_match and create_match.group(1) in inventories:
                schema_table = create_match.group(1)
                continue

            insert_match = INSERT_RE.match(line)
            if insert_match and insert_match.group(1) in inventories:
                table = insert_match.group(1)
                insert_state = InsertState(table=table)
                rows, ended = count_insert_rows(line[insert_match.end():], insert_state)
                inventories[table].rows += rows
                if ended:
                    insert_state = None

    return list(inventories.values())


def write_csv(rows: list[TableInventory], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Group", "Table", "Present", "Rows", "Value Columns"])
        for row in rows:
            writer.writerow([
                row.group,
                row.table,
                "yes" if row.present else "no",
                row.rows,
                "; ".join(row.value_columns),
            ])


def write_markdown(rows: list[TableInventory], output_path: Path, source_name: str) -> None:
    present = sum(row.present for row in rows)
    populated = sum(row.rows > 0 for row in rows)
    lines = [
        "# Drupal field inventory",
        "",
        f"- Source dump: `{source_name}`",
        f"- Tracked field tables: {len(rows)}",
        f"- Tables present in the dump: {present}",
        f"- Tables with populated rows: {populated}",
        f"- Total tracked field rows: {sum(row.rows for row in rows)}",
        "",
        "Drupal field tables share the common columns `bundle`, `deleted`,",
        "`entity_id`, `revision_id`, `langcode`, and `delta`. The table below",
        "lists the field-specific value columns and source row counts.",
        "",
        "| Group | Table | Present | Rows | Field-specific columns |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        columns = ", ".join(f"`{column}`" for column in row.value_columns) or "—"
        lines.append(
            f"| {row.group} | `{row.table}` | {'yes' if row.present else 'no'} "
            f"| {row.rows} | {columns} |"
        )
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-dump", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, default=Path("utils/drupal_to_hugo.py"))
    parser.add_argument("--output", type=Path, default=Path("reports/drupal_field_inventory.csv"))
    parser.add_argument("--summary", type=Path, default=Path("reports/drupal_field_inventory.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tracked = load_tracked_tables(args.extractor)
    rows = inventory_dump(args.sql_dump, tracked)
    write_csv(rows, args.output)
    write_markdown(rows, args.summary, args.sql_dump.name)
    print(
        f"Inventoried {len(rows)} tracked tables: "
        f"{sum(row.present for row in rows)} present, "
        f"{sum(row.rows > 0 for row in rows)} populated"
    )


if __name__ == "__main__":
    main()
