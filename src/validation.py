"""Module for record validation, quarantine logging, and duplicate/conflict detection."""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

CANONICAL_FIELDS = ("country", "continent", "year", "lifeExp", "pop", "gdpPercap")
_VALUE_FIELDS = ("continent", "lifeExp", "pop", "gdpPercap")


class ConflictingKeyError(ValueError):
    """Raised when two valid records share (country, year) but differ in another field."""


@dataclass
class ValidationResult:
    """Outcome of validating one record."""
    is_valid: bool
    clean_record: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class ValidationRun:
    """Holds the validation rules and applies them to records."""

    def __init__(self, allowed_continents: Set[str], allowed_years: Set[int],
                 max_life_exp: float = 120.0) -> None:
        self.allowed_continents = set(allowed_continents)
        self.allowed_years = set(allowed_years)
        self.max_life_exp = max_life_exp

    @staticmethod
    def _parse_number(raw: str, name: str) -> Tuple[Optional[float], Optional[str]]:
        """Parse text to a finite float; return (value, None) or (None, reason)."""
        if raw == "":
            return None, f"Missing {name}"
        if "_" in raw:
            return None, f"Unparseable numeric value for {name}: '{raw}'"
        try:
            value = float(raw)
        except ValueError:
            return None, f"Unparseable numeric value for {name}: '{raw}'"
        if not math.isfinite(value):
            return None, f"Non-finite value for {name}: '{raw}'"
        return value, None

    def validate_record(self, record: Dict[str, Any]) -> ValidationResult:
        """Validate one record as text before any integer conversion.
        """
        country = str(record.get("country", "") or "").strip()
        continent = str(record.get("continent", "") or "").strip()
        if not country:
            return ValidationResult(False, reason="Empty country identifier")
        if not continent:
            return ValidationResult(False, reason="Empty continent identifier")
        if continent not in self.allowed_continents:
            return ValidationResult(False, reason=f"Invalid continent: '{continent}'")

        raw_year = str(record.get("year", "") or "").strip()
        year_f, reason = self._parse_number(raw_year, "year")
        if reason:
            return ValidationResult(False, reason=reason)
        if not year_f.is_integer():
            return ValidationResult(False, reason=f"Fractional year: '{raw_year}'")
        year = int(year_f)
        if year not in self.allowed_years:
            return ValidationResult(False, reason=f"Year {year} not in allowed years")

        raw_pop = str(record.get("pop", "") or "").strip()
        pop_f, reason = self._parse_number(raw_pop, "pop")
        if reason:
            return ValidationResult(False, reason=reason)
        if not pop_f.is_integer():
            return ValidationResult(False, reason=f"Fractional population: '{raw_pop}'")
        if pop_f <= 0:
            return ValidationResult(False, reason=f"Out-of-range population: '{raw_pop}'")
        pop = int(pop_f)

        floats: Dict[str, float] = {}
        for field in ("lifeExp", "gdpPercap"):
            raw_val = str(record.get(field, "") or "").strip()
            val, reason = self._parse_number(raw_val, field)
            if reason:
                return ValidationResult(False, reason=reason)
            if val <= 0 or (field == "lifeExp" and val > self.max_life_exp):
                return ValidationResult(
                    False, reason=f"Out-of-range {field}: '{raw_val}'"
                )
            floats[field] = val

        clean_rec = {
            "country": country,
            "continent": continent,
            "year": year,
            "lifeExp": floats["lifeExp"],
            "pop": pop,
            "gdpPercap": floats["gdpPercap"],
            "source_file": record.get("source_file"),
            "source_record": record.get("source_record"),
        }
        return ValidationResult(True, clean_record=clean_rec)


def process_validations_and_quarantine(
    raw_records: List[Dict[str, Any]],
    validator: ValidationRun,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split flat records into (valid list, quarantine list)."""
    valid_records: List[Dict[str, Any]] = []
    quarantine_records: List[Dict[str, Any]] = []

    for rec in raw_records:
        res = validator.validate_record(rec)
        if res.is_valid and res.clean_record is not None:
            valid_records.append(res.clean_record)
        else:
            row = {
                "source_file": rec.get("source_file", ""),
                "source_record": rec.get("source_record", ""),
                "reason": res.reason,
            }
            for field in CANONICAL_FIELDS:
                row[field] = rec.get(field, "")
            quarantine_records.append(row)
    return valid_records, quarantine_records


def process_reader_records(
    records: List[Dict[str, Any]],
    validator: ValidationRun,
    source_file: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate reader output (clean/values shape); quarantine keeps original text."""
    valid_records: List[Dict[str, Any]] = []
    quarantine_records: List[Dict[str, Any]] = []

    for rec in records:
        flat = dict(rec["clean"])
        flat["source_file"] = source_file
        flat["source_record"] = rec["source_record"]
        res = validator.validate_record(flat)
        if res.is_valid and res.clean_record is not None:
            valid_records.append(res.clean_record)
        else:
            row = {
                "source_file": source_file,
                "source_record": rec["source_record"],
                "reason": res.reason,
            }
            for field in CANONICAL_FIELDS:
                row[field] = rec["values"].get(field, "")
            quarantine_records.append(row)
    return valid_records, quarantine_records


def _same_values(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Return True if two clean records have identical non-key fields."""
    return all(a[f] == b[f] for f in _VALUE_FIELDS)


def find_conflicts(valid_records: List[Dict[str, Any]]) -> None:
    """Raise ConflictingKeyError if a (country, year) key has differing values."""
    seen: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for rec in valid_records:
        key = (rec["country"], rec["year"])
        if key not in seen:
            seen[key] = rec
        elif not _same_values(rec, seen[key]):
            raise ConflictingKeyError(
                f"Conflicting key found for key {key} in file "
                f"'{rec.get('source_file')}' at record {rec.get('source_record')}."
            )


def deduplicate_and_check_conflicts(
    valid_records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Remove exact duplicate valid records; raise ConflictingKeyError on conflict.

    Returns (deduplicated records, duplicate log). Every removed copy is logged.
    """
    seen: Dict[Tuple[str, int], Dict[str, Any]] = {}
    deduped_records: List[Dict[str, Any]] = []
    duplicate_log: List[Dict[str, Any]] = []

    for rec in valid_records:
        key = (rec["country"], rec["year"])
        if key not in seen:
            seen[key] = rec
            deduped_records.append(rec)
        elif _same_values(rec, seen[key]):
            duplicate_log.append({
                "source_file": rec.get("source_file"),
                "source_record": rec.get("source_record"),
                "country": rec["country"],
                "year": rec["year"],
            })
        else:
            raise ConflictingKeyError(
                f"Conflicting key found for key {key} in file "
                f"'{rec.get('source_file')}' at record {rec.get('source_record')}."
            )
    return deduped_records, duplicate_log
