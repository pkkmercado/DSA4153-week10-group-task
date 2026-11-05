"""Module for record validation, quarantine logging, and duplicate/conflict detection."""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


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

    def __init__(self, allowed_continents: Set[str], allowed_year_min: int,
                 allowed_year_max: int) -> None:
        self.allowed_continents = set(allowed_continents)
        self.allowed_year_min = allowed_year_min
        self.allowed_year_max = allowed_year_max

    @staticmethod
    def _parse_number(raw: str, name: str) -> Tuple[Optional[float], Optional[str]]:
        """Parse text to a finite float; return (value, None) or (None, reason)."""
        if raw == "":
            return None, f"Missing {name}"
        try:
            value = float(raw)
        except ValueError:
            return None, f"Unparseable numeric value for {name}: '{raw}'"
        if not math.isfinite(value):
            return None, f"Non-finite value for {name}: '{raw}'"
        return value, None

    def validate_record(self, record: Dict[str, Any]) -> ValidationResult:
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
        if not (self.allowed_year_min <= year <= self.allowed_year_max):
            return ValidationResult(
                False,
                reason=f"Year {year} out of allowed range "
                       f"[{self.allowed_year_min}, {self.allowed_year_max}]")

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
            if val <= 0:
                return ValidationResult(
                    False, reason=f"Out-of-range value for {field}: '{raw_val}'")
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
    """Split records into (valid list, quarantine list)."""
    valid_records: List[Dict[str, Any]] = []
    quarantine_records: List[Dict[str, Any]] = []

    for rec in raw_records:
        res = validator.validate_record(rec)
        if res.is_valid:
            valid_records.append(res.clean_record)
        else:
            quarantine_records.append({
                "source_file": rec.get("source_file", ""),
                "source_record": rec.get("source_record", ""),
                "reason": res.reason,
                "country": rec.get("country", ""),
                "continent": rec.get("continent", ""),
                "year": rec.get("year", ""),
                "lifeExp": rec.get("lifeExp", ""),
                "pop": rec.get("pop", ""),
                "gdpPercap": rec.get("gdpPercap", ""),
            })
    return valid_records, quarantine_records


_VALUE_FIELDS = ("continent", "lifeExp", "pop", "gdpPercap")


def find_conflicts(valid_records: List[Dict[str, Any]]) -> None:
    """Raise ConflictingKeyError if a (country, year) key has differing values."""
    seen: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for rec in valid_records:
