from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.csv_excel_readers import check_input_file
from src.errors import InputFileError

RawRecord = dict[str, Any]


def to_text(value: Any) -> str:
    """Convert a parsed JSON/Parquet value to text without changing what it holds."""
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)  # keeps nan / inf visible for later validation
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def flatten_record(obj: dict[str, Any], prefix: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten nested dicts into one level: {'a': {'b': 1}} -> {'a.b': 1}."""
    flat: dict[str, Any] = {}
    for key, value in obj.items():
        name = f"{prefix}{sep}{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_record(value, name, sep))
        else:
            flat[name] = value
    return flat


def find_records(document: Any, records_path: str | list[str], file_name: str) -> list[Any]:
    """Walk a dotted path (e.g. 'data.records') to the record list; missing key is a file error."""
    keys = records_path.split(".") if isinstance(records_path, str) else list(records_path)
    node = document
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            raise InputFileError(f"{file_name}: missing key '{key}' in path '{records_path}'")
        node = node[key]
    if not isinstance(node, list):
        raise InputFileError(f"{file_name}: '{records_path}' is not a list of records")
    return node


def read_json_records(path: str | Path, settings: dict[str, Any]) -> tuple[list[str], list[RawRecord]]:
    """Read a JSON file with an outer metadata object; return (columns, raw records).

    settings keys: records_path (required, e.g. 'records'), encoding (default 'utf-8-sig').
    Nested record objects are flattened into dotted column names. The header is the
    ordered union of all keys; a record lacking a key gets "" so it can be quarantined.
    """
    p = check_input_file(path, {".json"})
    encoding = settings.get("encoding", "utf-8-sig")
    try:
        with p.open("r", encoding=encoding) as handle:
            document = json.load(handle)
    except UnicodeDecodeError as exc:
        raise InputFileError(f"{p.name}: cannot decode as {encoding}") from exc
    except json.JSONDecodeError as exc:
        raise InputFileError(f"{p.name}: invalid JSON ({exc.msg})") from exc

    items = find_records(document, settings["records_path"], p.name)
    flat_items: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise InputFileError(f"{p.name}: record {position} is not an object")
        flat_items.append({k.strip(): v for k, v in flatten_record(item).items()})

    header: list[str] = list(dict.fromkeys(k for item in flat_items for k in item))
    records: list[RawRecord] = []
    for position, item in enumerate(flat_items, start=1):
        records.append(
            {
                "source_file": p.name,
                "source_record": position,
                "values": {col: to_text(item.get(col)) for col in header},
            }
        )
    return header, records


def read_parquet_records(path: str | Path, settings: dict[str, Any] | None = None) -> tuple[list[str], list[RawRecord]]:
    """Read a Parquet file; return (columns, raw records). Values stay text; nulls become ""."""
    p = check_input_file(path, {".parquet"})
    try:
        table = pq.read_table(p)
    except (pa.ArrowException, OSError) as exc:
        raise InputFileError(f"{p.name}: cannot read Parquet ({exc})") from exc

    header = [str(name).strip() for name in table.column_names]
    columns = [table.column(i).to_pylist() for i in range(table.num_columns)]
    records: list[RawRecord] = []
    for row_index in range(table.num_rows):
        records.append(
            {
                "source_file": p.name,
                "source_record": row_index + 1,
                "values": {header[j]: to_text(columns[j][row_index]) for j in range(len(header))},
            }
        )
    return header, records