"""Readers for the CSV and Excel inputs.

Readers only parse. They keep every original field value as text, keep the
original column names, and number records by position. Column mapping,
trimming, validation, and type conversion happen in later steps.

A raw record is a dict:
    {"source_file": str, "source_record": int, "values": {column: text}}
source_record is the one-based data-record order (headers, comment lines,
and sheet/metadata rows are not counted).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from src.errors import InputFileError

SUPPORTED_FORMATS: set[str] = {".csv", ".xlsx"}

RawRecord = dict[str, Any]


def check_input_file(path: str | Path, supported: set[str] = SUPPORTED_FORMATS) -> Path:
    """Return the path as a Path, or raise InputFileError if missing/unsupported."""
    p = Path(path)
    if not p.is_file():
        raise InputFileError(f"input file not found: {p}")
    if p.suffix.lower() not in supported:
        raise InputFileError(f"unsupported file format '{p.suffix}': {p.name}")
    return p


def read_csv_records(path: str | Path, settings: dict[str, Any]) -> tuple[list[str], list[RawRecord]]:
    """Read a delimited text file; return (original column names, raw records).

    settings keys: encoding (default 'cp1252'), delimiter (default ';'),
    comment_prefix (leading lines starting with it are skipped, e.g. '#'),
    or comment_lines (a fixed number of leading lines to skip, default 0).
    """
    p = check_input_file(path, {".csv"})
    encoding = settings.get("encoding", "cp1252")
    delimiter = settings.get("delimiter", ";")
    prefix = settings.get("comment_prefix")
    skip = int(settings.get("comment_lines", 0))

    try:
        with p.open("r", encoding=encoding, newline="") as handle:
            lines = handle.read().splitlines(keepends=True)
            start = skip
            if prefix:
                while start < len(lines) and lines[start].startswith(prefix):
                    start += 1
            reader = csv.reader(lines[start:], delimiter=delimiter)
            header = next(reader, None)
            if header is None:
                raise InputFileError(f"no header row found: {p.name}")
            header = [h.strip() for h in header]
            records: list[RawRecord] = []
            for row in reader:
                if not row:  # fully blank line
                    continue
                if len(row) > len(header):
                    raise InputFileError(
                        f"{p.name}: record {len(records) + 1} has {len(row)} fields, "
                        f"header has {len(header)}"
                    )
                row = row + [""] * (len(header) - len(row))
                records.append(
                    {
                        "source_file": p.name,
                        "source_record": len(records) + 1,
                        "values": dict(zip(header, row)),
                    }
                )
    except UnicodeDecodeError as exc:
        raise InputFileError(f"{p.name}: cannot decode as {encoding}") from exc
    return header, records


def _cell_text(value: Any) -> str:
    """Convert an Excel cell to text without changing what it holds."""
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def read_excel_records(path: str | Path, settings: dict[str, Any]) -> tuple[list[str], list[RawRecord]]:
    """Read the observations sheet of a workbook; return (columns, raw records).

    settings keys: sheet (required sheet name).
    Other sheets (e.g. Readme) are ignored; a missing sheet is a file-level error.
    """
    p = check_input_file(path, {".xlsx"})
    sheet = settings["sheet"]
    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise InputFileError(f"{p.name}: sheet '{sheet}' not found")
        rows = wb[sheet].iter_rows(values_only=True)
        first = next(rows, None)
        if first is None:
            raise InputFileError(f"{p.name}: sheet '{sheet}' is empty")
        header = [_cell_text(h).strip() for h in first]
        records: list[RawRecord] = []
        for row in rows:
            if all(c is None for c in row):  # fully blank row
                continue
            texts = [_cell_text(c) for c in row][: len(header)]
            texts += [""] * (len(header) - len(texts))
            records.append(
                {
                    "source_file": p.name,
                    "source_record": len(records) + 1,
                    "values": dict(zip(header, texts)),
                }
            )
    finally:
        wb.close()
    return header, records