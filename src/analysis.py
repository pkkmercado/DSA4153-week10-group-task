"""pandas analysis and calculation checks (Member 4).

Input is the canonical table (columns country, continent, year, lifeExp,
pop, gdpPercap). Nothing here reads files or knows about input formats.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.matrix_ops import (
    ABS_TOL, PopulationIndexResult, boolean_total, build_population_index,
)

REQUIRED_COLUMNS: set[str] = {
    "country", "continent", "year", "lifeExp", "pop", "gdpPercap",
}

DEFAULT_ANALYSIS_CONFIG: dict = {
    "reporting_year": 2007,
    "region": "Asia",
    "history_country": "Philippines",
    "matrix_countries": ["Philippines", "Indonesia", "Thailand"],
    "matrix_years": [1982, 1987, 1992, 1997, 2002, 2007],
    "baseline_year": 1982,
}


def check_columns(df: pd.DataFrame) -> None:
    """Raise ValueError if a required canonical column is missing."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Canonical table missing columns: {sorted(missing)}")


def select_region_year(df: pd.DataFrame, region: str, year: int) -> pd.DataFrame:
    """Select one continent and year using ``.loc`` with a Boolean mask."""
    check_columns(df)
    mask = (df["continent"] == region) & (df["year"] == year)
    return df.loc[mask].copy()


def build_region_year_table(df: pd.DataFrame, region: str, year: int) -> pd.DataFrame:
    """Build asia_selected_year.csv: pop in millions and life-expectancy rank.

    Rank is descending with ``method="min"`` (ties share the best rank);
    rows are sorted by rank, then country.
    """
    out = select_region_year(df, region, year)
    out["pop_millions"] = out["pop"] / 1_000_000
    out["lifeExp_rank"] = (
        out["lifeExp"].rank(ascending=False, method="min").astype("int64")
    )
    out = out.sort_values(["lifeExp_rank", "country"], kind="stable")
    return out.reset_index(drop=True)


def build_country_history(df: pd.DataFrame, country: str) -> pd.DataFrame:
    """Build country_history.csv: all rows for one country sorted by year.

    Adds population in millions and life-expectancy change from the first
    observed year.
    """
    check_columns(df)
    out = df.loc[df["country"] == country].sort_values("year").copy()
    if out.empty:
        raise ValueError(f"No rows found for country {country!r}")
    out["pop_millions"] = out["pop"] / 1_000_000
    out["lifeExp_change"] = out["lifeExp"] - out["lifeExp"].iloc[0]
    return out.reset_index(drop=True)


def _row(check: str, expected, actual, tolerance, passed: bool) -> dict:
    """Make one validation record."""
    return {"check": check, "expected": expected, "actual": actual,
            "tolerance": tolerance, "pass": bool(passed)}


def calculation_checks(
    df: pd.DataFrame,
    region_table: pd.DataFrame,
    history: pd.DataFrame,
    result: PopulationIndexResult,
    cfg: dict,
    controls: dict | None = None,
) -> list[dict]:
    """Return validation rows (check, expected, actual, tolerance, pass).

    ``controls`` is the manifest's ``controls`` dict; the 2007 control values
    are only compared when the reporting year is 2007.
    """
    year, region = cfg["reporting_year"], cfg["region"]
    country = cfg["history_country"]
    rows: list[dict] = []

    # Independent NumPy Boolean selection / aggregation
    np_count, np_total = boolean_total(
        df["continent"].to_numpy(dtype=object), df["year"].to_numpy(),
        df["pop"].to_numpy(), region, year)
    pd_total = int(region_table["pop"].sum())
    rows.append(_row(f"{region} {year} rows: NumPy mask vs pandas .loc",
                     np_count, len(region_table), 0, np_count == len(region_table)))
    rows.append(_row(f"{region} {year} population: NumPy vs pandas",
                     np_total, pd_total, 0, np_total == pd_total))
    rows.append(_row("Region table life-expectancy rank starts at 1",
                     1, int(region_table["lifeExp_rank"].min()), 0,
                     int(region_table["lifeExp_rank"].min()) == 1))
    sorted_ok = region_table[["lifeExp_rank", "country"]].equals(
        region_table[["lifeExp_rank", "country"]].sort_values(
            ["lifeExp_rank", "country"]).reset_index(drop=True))
    rows.append(_row("Region table sorted by rank then country", True, sorted_ok, 0, sorted_ok))
    millions_err = float(np.max(np.abs(
        region_table["pop_millions"] * 1e6 - region_table["pop"])))
    rows.append(_row("Region table pop_millions * 1e6 equals pop", 0, millions_err,
                     ABS_TOL, millions_err <= ABS_TOL))

    # Country history
    rows.append(_row(f"{country} history rows", len(df.loc[df["country"] == country]),
                     len(history), 0, len(history) == int((df["country"] == country).sum())))
    first_change = float(history["lifeExp_change"].iloc[0])
    rows.append(_row(f"{country} first life-expectancy change is 0", 0.0, first_change,
                     ABS_TOL, abs(first_change) <= ABS_TOL))
    rows.append(_row(f"{country} history sorted by year", True,
                     bool(history["year"].is_monotonic_increasing), 0,
                     bool(history["year"].is_monotonic_increasing)))

    # Philippine population in reporting year (from NumPy and pandas)
    ph_pd = int(history.loc[history["year"] == year, "pop"].iloc[0])
    ph_np = int(boolean_total(
        df["country"].to_numpy(dtype=object), df["year"].to_numpy(),
        df["pop"].to_numpy(), country, year)[1])
    rows.append(_row(f"{country} {year} population: NumPy vs pandas", ph_np, ph_pd, 0,
                     ph_np == ph_pd))

    # Manifest controls apply to the 2007 snapshot only
    if controls and year == 2007:
        rows.append(_row("Asia 2007 rows (manifest control)",
                         controls["asia_2007_rows"], len(region_table), 0,
                         len(region_table) == controls["asia_2007_rows"]))
        rows.append(_row("Asia 2007 population (manifest control)",
                         controls["asia_2007_population"], np_total, 0,
                         np_total == controls["asia_2007_population"]))
        rows.append(_row("Philippines 2007 population (manifest control)",
                         controls["philippines_2007_population"], ph_np, 0,
                         ph_np == controls["philippines_2007_population"]))
        rows.append(_row("Philippines history rows (manifest control)",
                         controls["philippines_rows"], len(history), 0,
                         len(history) == controls["philippines_rows"]))

    # NumPy matrix checks
    n_c, n_y = len(result.countries), len(result.years)
    rows.append(_row("Population matrix shape", f"({n_c}, {n_y})",
                     str(result.shapes["matrix"]), 0, result.shapes["matrix"] == (n_c, n_y)))
    rows.append(_row("Baseline shape before broadcasting", f"({n_c}, 1)",
                     str(result.shapes["baseline_before_broadcast"]), 0,
                     result.shapes["baseline_before_broadcast"] == (n_c, 1)))
    rows.append(_row("Index shape after broadcasting", f"({n_c}, {n_y})",
                     str(result.shapes["index_after_broadcast"]), 0,
                     result.shapes["index_after_broadcast"] == (n_c, n_y)))
    base_col = result.years.index(result.baseline_year)
    base_err = float(np.max(np.abs(result.index[:, base_col] - 100.0)))
    rows.append(_row(f"Index baseline column ({result.baseline_year}) equals 100", 100.0,
                     100.0 + base_err, ABS_TOL, base_err <= ABS_TOL))
    rows.append(_row("Broadcast index vs independent loop (max abs diff)", 0.0,
                     result.max_abs_diff, ABS_TOL, result.max_abs_diff <= ABS_TOL))
    pivot = (df.loc[df["country"].isin(result.countries)
                    & df["year"].isin(result.years)]
             .pivot(index="country", columns="year", values="pop")
             .loc[result.countries, result.years].to_numpy(dtype=np.int64))
    rows.append(_row("Matrix equals pandas pivot of canonical pop", True,
                     bool(np.array_equal(pivot, result.matrix)), 0,
                     bool(np.array_equal(pivot, result.matrix))))
    return rows


def run_analysis(
    df: pd.DataFrame,
    analysis_config: dict | None = None,
    controls: dict | None = None,
) -> dict:
    """Run the full analysis and return tables, matrix result, checks, audit.

    The reporting year and all selections come from ``analysis_config`` so a
    different year needs no code change.
    """
    cfg = {**DEFAULT_ANALYSIS_CONFIG, **(analysis_config or {})}
    check_columns(df)
    n = len(df)
    region_table = build_region_year_table(df, cfg["region"], cfg["reporting_year"])
    history = build_country_history(df, cfg["history_country"])
    result = build_population_index(
        df, cfg["matrix_countries"], cfg["matrix_years"], cfg["baseline_year"])
    checks = calculation_checks(df, region_table, history, result, cfg, controls)
    audit: list[dict] = [
        {"step": "analysis.region_year", "source_file": "canonical",
         "operation": "select with .loc, add pop_millions and lifeExp_rank",
         "rule": f"continent == {cfg['region']} and year == {cfg['reporting_year']}",
         "rows_before": n, "rows_after": len(region_table)},
        {"step": "analysis.country_history", "source_file": "canonical",
         "operation": "select country, sort by year, add lifeExp_change",
         "rule": f"country == {cfg['history_country']}",
         "rows_before": n, "rows_after": len(history)},
        {"step": "analysis.population_index", "source_file": "canonical",
         "operation": "NumPy matrix, broadcast index, loop verification",
         "rule": f"{result.baseline_year} = 100",
         "rows_before": n, "rows_after": len(result.countries)},
    ]
    return {"config": cfg, "region_table": region_table, "history": history,
            "index_result": result, "index_table": result.to_frame(),
            "checks": checks, "audit": audit}


def write_analysis_outputs(outputs: dict, folder: str | Path) -> list[Path]:
    """Write the three analysis CSVs into ``folder`` (a staging folder)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    targets = {"asia_selected_year.csv": outputs["region_table"],
               "country_history.csv": outputs["history"],
               "population_index.csv": outputs["index_table"]}
    paths = []
    for name, frame in targets.items():
        path = folder / name
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths
