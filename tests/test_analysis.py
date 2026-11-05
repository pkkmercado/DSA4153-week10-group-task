import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import (
    build_country_history, build_region_year_table, run_analysis,
    write_analysis_outputs,
)
from src.matrix_ops import (
    boolean_total, broadcast_index, build_population_index, loop_index,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COLS = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]


def load_canonical_standin() -> pd.DataFrame:
    """Return a clean canonical table for testing, or skip the test."""
    override = os.environ.get("CANONICAL_CSV")
    if override:
        return pd.read_csv(override)
    path = DATA / "country_records.csv"
    if not path.exists():
        raise unittest.SkipTest("data/country_records.csv not found")
    raw = pd.read_csv(path, sep=";", encoding="cp1252", comment="#", dtype=str)
    raw = raw.rename(columns={
        "CountryName": "country", "ContinentName": "continent",
        "ObservationYear": "year", "LifeYears": "lifeExp",
        "PopulationPersons": "pop", "GDPPerPerson": "gdpPercap"})[COLS]
    for c in ("year", "lifeExp", "pop", "gdpPercap"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.dropna()
    raw = raw[raw["continent"].isin(
        ["Africa", "Americas", "Asia", "Europe", "Oceania"])]
    raw = raw[(raw["lifeExp"] > 0) & (raw["lifeExp"] <= 120)
              & (raw["pop"] > 0) & (raw["gdpPercap"] > 0)]
    raw = raw[(raw["year"] % 1 == 0) & (raw["pop"] % 1 == 0)]
    raw = raw.astype({"year": "int64", "pop": "int64"}).drop_duplicates()
    return raw.sort_values(["country", "year"]).reset_index(drop=True)


def controls() -> dict:
    """Read the manifest control values."""
    return json.loads((DATA / "manifest.json").read_text())["controls"]


class SyntheticTests(unittest.TestCase):
    """Small hand-made tables where the answer is known by inspection."""

    def setUp(self):
        self.df = pd.DataFrame({
            "country": ["A", "B", "C", "D", "E"],
            "continent": ["Asia", "Asia", "Asia", "Asia", "Europe"],
            "year": [2007] * 5,
            "lifeExp": [70.0, 80.0, 80.0, 60.0, 90.0],
            "pop": [1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000],
            "gdpPercap": [1.0] * 5})

    def test_rank_method_min_with_ties(self):
        out = build_region_year_table(self.df, "Asia", 2007)
        self.assertEqual(list(out["country"]), ["B", "C", "A", "D"])
        self.assertEqual(list(out["lifeExp_rank"]), [1, 1, 3, 4])

    def test_millions_and_selection(self):
        out = build_region_year_table(self.df, "Asia", 2007)
        self.assertEqual(len(out), 4)
        self.assertNotIn("E", set(out["country"]))
        self.assertAlmostEqual(out["pop_millions"].sum(), 10.0)

    def test_boolean_total(self):
        n, total = boolean_total(
            self.df["continent"].to_numpy(dtype=object),
            self.df["year"].to_numpy(), self.df["pop"].to_numpy(), "Asia", 2007)
        self.assertEqual((n, total), (4, 10_000_000))

    def test_broadcast_known_values(self):
        m = np.array([[100, 150, 200], [50, 50, 100]], dtype=np.int64)
        base, idx = broadcast_index(m, 0)
        self.assertEqual(base.shape, (2, 1))
        self.assertEqual(idx.shape, (2, 3))
        np.testing.assert_allclose(idx, [[100, 150, 200], [100, 100, 200]],
                                   rtol=0, atol=1e-8)
        np.testing.assert_allclose(idx, loop_index(m, 0), rtol=0, atol=1e-8)

    def test_missing_country_year_raises(self):
        with self.assertRaises(ValueError):
            build_population_index(self.df, ["A", "Z"], [2007], 2007)

    def test_baseline_not_in_years_raises(self):
        with self.assertRaises(ValueError):
            build_population_index(self.df, ["A"], [2007], 1982)

    def test_missing_column_raises(self):
        with self.assertRaises(ValueError):
            build_region_year_table(self.df.drop(columns=["pop"]), "Asia", 2007)

    def test_unknown_country_history_raises(self):
        with self.assertRaises(ValueError):
            build_country_history(self.df, "Atlantis")


class RealDataTests(unittest.TestCase):
    """Checks against the supplied Gapminder control values."""

    @classmethod
    def setUpClass(cls):
        cls.df = load_canonical_standin()
        cls.out = run_analysis(cls.df, {"reporting_year": 2007}, controls())

    def test_standin_has_1704_rows(self):
        self.assertEqual(len(self.df), 1704)

    def test_asia_2007_has_33_rows(self):
        self.assertEqual(len(self.out["region_table"]), 33)

    def test_asia_2007_population(self):
        self.assertEqual(int(self.out["region_table"]["pop"].sum()), 3_811_953_827)
        n, total = boolean_total(
            self.df["continent"].to_numpy(dtype=object),
            self.df["year"].to_numpy(), self.df["pop"].to_numpy(), "Asia", 2007)
        self.assertEqual((n, total), (33, 3_811_953_827))

    def test_philippines_2007_population(self):
        h = self.out["history"]
        self.assertEqual(len(h), 12)
        self.assertEqual(int(h.loc[h["year"] == 2007, "pop"].iloc[0]), 91_077_287)

    def test_history_change_starts_at_zero(self):
        h = self.out["history"]
        self.assertEqual(h["lifeExp_change"].iloc[0], 0.0)
        self.assertTrue(h["year"].is_monotonic_increasing)

    def test_index_baseline_is_100_and_shape(self):
        r = self.out["index_result"]
        self.assertEqual(r.shapes["matrix"], (3, 6))
        self.assertEqual(r.shapes["baseline_before_broadcast"], (3, 1))
        self.assertEqual(r.shapes["index_after_broadcast"], (3, 6))
        np.testing.assert_allclose(r.index[:, 0], 100.0, rtol=0, atol=1e-8)
        self.assertEqual(list(self.out["index_table"].columns),
                         ["country", "1982", "1987", "1992", "1997", "2002", "2007"])
        self.assertEqual(list(self.out["index_table"]["country"]),
                         ["Philippines", "Indonesia", "Thailand"])

    def test_broadcast_matches_loop(self):
        self.assertLessEqual(self.out["index_result"].max_abs_diff, 1e-8)

    def test_all_validation_rows_pass(self):
        failed = [c for c in self.out["checks"] if not c["pass"]]
        self.assertEqual(failed, [])
        self.assertEqual(set(self.out["checks"][0]),
                         {"check", "expected", "actual", "tolerance", "pass"})

    def test_reporting_year_1997_needs_no_code_change(self):
        out = run_analysis(self.df, {"reporting_year": 1997}, controls())
        self.assertEqual(out["region_table"]["year"].unique().tolist(), [1997])
        self.assertEqual(len(out["region_table"]), 33)
        self.assertTrue(all(c["pass"] for c in out["checks"]))
        # manifest 2007 controls must not be applied to a 1997 run
        self.assertFalse(any("manifest" in c["check"] for c in out["checks"]))

    def test_tampered_value_is_caught(self):
        bad = self.df.copy()
        i = bad.index[(bad["country"] == "Philippines") & (bad["year"] == 2007)][0]
        bad.loc[i, "pop"] += 1
        out = run_analysis(bad, {"reporting_year": 2007}, controls())
        self.assertTrue(any(not c["pass"] for c in out["checks"]))

    def test_write_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_analysis_outputs(self.out, tmp)
            self.assertEqual(sorted(p.name for p in paths),
                             ["asia_selected_year.csv", "country_history.csv",
                              "population_index.csv"])
            back = pd.read_csv(Path(tmp) / "population_index.csv")
            self.assertEqual(back.shape, (3, 7))


if __name__ == "__main__":
    unittest.main()
