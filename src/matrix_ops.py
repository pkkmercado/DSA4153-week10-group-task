
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ABS_TOL: float = 1e-8  # absolute tolerance, relative tolerance is 0


@dataclass
class PopulationIndexResult:
    
    countries: list[str]
    years: list[int]
    baseline_year: int
    matrix: np.ndarray            # (n_countries, n_years) population, persons
    baseline: np.ndarray          # (n_countries, 1) baseline-year population
    index: np.ndarray             # (n_countries, n_years) broadcast result
    loop_index: np.ndarray        # independent loop calculation
    shapes: dict[str, tuple[int, ...]] = field(default_factory=dict)

    @property
    def max_abs_diff(self) -> float:
        """Largest absolute difference between broadcast and loop results."""
        return float(np.max(np.abs(self.index - self.loop_index)))

    def to_frame(self) -> pd.DataFrame:
        """Return country labels plus one named column per year."""
        frame = pd.DataFrame(self.index, columns=[str(y) for y in self.years])
        frame.insert(0, "country", list(self.countries))
        return frame


def boolean_total(
    continent: np.ndarray, year: np.ndarray, pop: np.ndarray,
    target_continent: str, target_year: int,
) -> tuple[int, int]:
    """Boolean-select a continent/year and return (row count, population sum).

    Uses only NumPy masks, so it does not rely on the pandas summary.
    """
    mask = (continent == target_continent) & (year == target_year)
    return int(mask.sum()), int(pop[mask].astype(np.int64).sum())


def build_population_matrix(
    df: pd.DataFrame, countries: list[str], years: list[int],
) -> np.ndarray:
    """Build the (countries x years) population matrix with Boolean masks.

    Raises ValueError if any country/year cell is missing or ambiguous.
    """
    country_arr = df["country"].to_numpy(dtype=object)
    year_arr = df["year"].to_numpy(dtype=np.int64)
    pop_arr = df["pop"].to_numpy(dtype=np.int64)
    matrix = np.zeros((len(countries), len(years)), dtype=np.int64)
    for i, country in enumerate(countries):
        for j, yr in enumerate(years):
            mask = (country_arr == country) & (year_arr == yr)
            if int(mask.sum()) != 1:
                raise ValueError(
                    f"Expected exactly 1 row for ({country}, {yr}), "
                    f"found {int(mask.sum())}"
                )
            matrix[i, j] = pop_arr[mask][0]
    return matrix


def broadcast_index(
    matrix: np.ndarray, baseline_col: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Express each row relative to its baseline column (baseline = 100).

    The (n, 1) baseline column is broadcast across the (n, m) matrix.
    """
    baseline = matrix[:, [baseline_col]].astype(np.float64)  # shape (n, 1)
    index = matrix.astype(np.float64) / baseline * 100.0     # (n,m)/(n,1)
    return baseline, index


def loop_index(matrix: np.ndarray, baseline_col: int) -> np.ndarray:
    """Independently compute the index with plain Python loops."""
    n_rows, n_cols = matrix.shape
    out = np.zeros((n_rows, n_cols), dtype=np.float64)
    for i in range(n_rows):
        base = float(matrix[i, baseline_col])
        for j in range(n_cols):
            out[i, j] = float(matrix[i, j]) / base * 100.0
    return out


def build_population_index(
    df: pd.DataFrame,
    countries: list[str],
    years: list[int],
    baseline_year: int = 1982,
) -> PopulationIndexResult:
    """Build the population matrix, broadcast index and loop verification."""
    if baseline_year not in years:
        raise ValueError(f"baseline_year {baseline_year} not in years {years}")
    matrix = build_population_matrix(df, countries, years)
    col = years.index(baseline_year)
    baseline, index = broadcast_index(matrix, col)
    check = loop_index(matrix, col)
    shapes = {
        "matrix": matrix.shape,
        "baseline_before_broadcast": baseline.shape,
        "index_after_broadcast": index.shape,
    }
    return PopulationIndexResult(
        countries=list(countries), years=list(years),
        baseline_year=baseline_year, matrix=matrix, baseline=baseline,
        index=index, loop_index=check, shapes=shapes,
    )
