"""Checks for JSON/Parquet readers, column mapping, missing column and missing key."""
import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.errors import InputFileError
from src.json_parquet_readers import read_json_records, read_parquet_records
from src.normalize import CANONICAL_COLUMNS, map_columns, normalize_records

JSON_SETTINGS = {"record_path": "records"}
NESTED_MAP = {
    "place.land": "country", "place.kontinent": "continent", "jahr": "year",
    "measures.lebenserwartung": "lifeExp", "measures.einwohner": "pop",
    "measures.bip": "gdpPercap",
}
FLAT_MAP = {
    "land": "country", "kontinent": "continent", "jahr": "year",
    "lebenserwartung": "lifeExp", "einwohner": "pop", "bip": "gdpPercap",
}


def nested(country, continent, year, life, pop, gdp):
    return {
        "place": {"land": country, "kontinent": continent},
        "jahr": year,
        "measures": {"lebenserwartung": life, "einwohner": pop, "bip": gdp},
    }


class JsonParquetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_json(self, payload, name="a.json") -> Path:
        p = self.dir / name
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def make_parquet(self, columns: dict, name="a.parquet") -> Path:
        p = self.dir / name
        pq.write_table(pa.table(columns), p)
        return p

    # ---- JSON reader ----
    def test_json_normal_flatten_counts_positions(self):
        p = self.make_json({"meta": {"source": "x"}, "records": [
            nested(" Peru ", "Americas", 1952, 43.9, 8025700, 3758.5),
            nested("Chad", "Africa", 1957, 40.0, 3000000, 1000.0)]})
        header, recs = read_json_records(p, JSON_SETTINGS)
        self.assertIn("place.land", header)
        self.assertEqual(len(recs), 2)
        self.assertEqual([r["source_record"] for r in recs], [1, 2])
        self.assertEqual(recs[0]["values"]["place.land"], " Peru ")   # whitespace kept
        self.assertEqual(recs[0]["values"]["jahr"], "1952")           # text, not int
        self.assertEqual(recs[0]["source_file"], "a.json")

    def test_json_dotted_record_path(self):
        p = self.make_json({"data": {"records": [nested("Peru", "Americas", 1952, 1.0, 2, 3.0)]}})
        _, recs = read_json_records(p, {"record_path": "data.records"})
        self.assertEqual(len(recs), 1)

    def test_json_missing_key_records_is_file_error(self):
        p = self.make_json({"meta": {}, "rows": []})
        with self.assertRaises(InputFileError):
            read_json_records(p, JSON_SETTINGS)

    def test_json_missing_record_path_setting_is_file_error(self):
        p = self.make_json({"records": [nested("Peru", "Americas", 1952, 1.0, 2, 3.0)]})
        with self.assertRaises(InputFileError):
            read_json_records(p, {})                                # clear error, not KeyError
        with self.assertRaises(InputFileError):
            read_json_records(p, {"records_path": "records"})       # old name no longer accepted

    def test_json_record_missing_key_becomes_empty_text(self):
        bad = nested("Peru", "Americas", 1952, 1.0, 2, 3.0)
        del bad["jahr"]
        good = nested("Chad", "Africa", 1957, 1.0, 2, 3.0)
        p = self.make_json({"records": [bad, good]})
        header, recs = read_json_records(p, JSON_SETTINGS)
        self.assertIn("jahr", header)                 # key still in header
        self.assertEqual(recs[0]["values"]["jahr"], "")   # quarantined later, not a file error

    def test_json_invalid_syntax_is_file_error(self):
        p = self.dir / "broken.json"
        p.write_text('{"records": [', encoding="utf-8")
        with self.assertRaises(InputFileError):
            read_json_records(p, JSON_SETTINGS)

    def test_json_nonfinite_and_float_year_stay_visible(self):
        p = self.dir / "nan.json"
        p.write_text('{"records":[{"jahr":1952.0,"x":NaN,"y":null}]}', encoding="utf-8")
        _, recs = read_json_records(p, JSON_SETTINGS)
        self.assertEqual(recs[0]["values"]["jahr"], "1952.0")
        self.assertEqual(recs[0]["values"]["x"], "nan")
        self.assertEqual(recs[0]["values"]["y"], "")

    # ---- Parquet reader ----
    def test_parquet_normal_counts_and_text(self):
        p = self.make_parquet({"land": [" Peru ", "Chad"], "jahr": ["1952", "19x7"]})
        header, recs = read_parquet_records(p)
        self.assertEqual(header, ["land", "jahr"])
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["values"]["land"], " Peru ")
        self.assertEqual(recs[1]["values"]["jahr"], "19x7")           # validated later
        self.assertEqual(recs[1]["source_record"], 2)

    def test_parquet_null_becomes_empty_text(self):
        p = self.make_parquet({"land": ["Peru", None]})
        _, recs = read_parquet_records(p)
        self.assertEqual(recs[1]["values"]["land"], "")

    def test_parquet_corrupt_file_is_file_error(self):
        p = self.dir / "bad.parquet"
        p.write_text("not parquet")
        with self.assertRaises(InputFileError):
            read_parquet_records(p)

    def test_missing_file_and_unsupported_format(self):
        with self.assertRaises(InputFileError):
            read_json_records(self.dir / "nope.json", JSON_SETTINGS)
        txt = self.dir / "unsupported.txt"
        txt.write_text("hello")
        with self.assertRaises(InputFileError):
            read_json_records(txt, JSON_SETTINGS)

    # ---- column mapping and normalization ----
    def test_map_columns_renames_and_drops_extras(self):
        p = self.make_json({"records": [nested(" Peru ", "Americas", 1952, 43.9, 8025700, 3758.5)]})
        header, recs = read_json_records(p, JSON_SETTINGS)
        mapped = map_columns(header, recs, NESTED_MAP, "a.json")
        self.assertEqual(list(mapped[0]["values"]), CANONICAL_COLUMNS)
        self.assertEqual(mapped[0]["values"]["country"], " Peru ")     # original kept
        self.assertEqual(mapped[0]["source_record"], 1)

    def test_normalize_trims_but_keeps_original(self):
        raw = [{"source_file": "f", "source_record": 1,
                "values": {c: f"  {c} " for c in CANONICAL_COLUMNS}}]
        header = CANONICAL_COLUMNS
        out = normalize_records(map_columns(header, raw, {}, "f"))
        self.assertEqual(out[0]["clean"]["country"], "country")
        self.assertEqual(out[0]["values"]["country"], "  country ")

    def test_missing_column_is_file_error(self):
        p = self.make_parquet({"land": ["Peru"], "kontinent": ["Americas"], "jahr": ["1952"],
                               "lebenserwartung": ["1"], "einwohner": ["2"]})  # bip missing
        header, recs = read_parquet_records(p)
        with self.assertRaises(InputFileError):
            map_columns(header, recs, FLAT_MAP, "a.parquet")

    def test_two_columns_mapping_to_same_name_is_error(self):
        header = ["land", "pays", "kontinent", "jahr", "lebenserwartung", "einwohner", "bip"]
        cmap = dict(FLAT_MAP, pays="country")
        with self.assertRaises(InputFileError):
            map_columns(header, [], cmap, "x")

    def test_reversed_column_map_is_file_error(self):
        reversed_map = {v: k for k, v in FLAT_MAP.items()}   # canonical -> source (wrong way)
        with self.assertRaises(InputFileError):
            map_columns(list(FLAT_MAP), [], reversed_map, "x")

    def test_source_names_that_are_already_canonical_keep_working(self):
        header = ["country", "continent", "jahr", "lebenserwartung", "einwohner", "bip"]
        cmap = {"country": "country", "jahr": "year", "lebenserwartung": "lifeExp",
                "einwohner": "pop", "bip": "gdpPercap"}   # "continent" not listed: keeps its name
        raw = [{"source_file": "f", "source_record": 1,
                "values": dict(zip(header, ["Peru", "Americas", "1952", "43.9", "8025700", "3758.5"]))}]
        mapped = map_columns(header, raw, cmap, "f")
        self.assertEqual(mapped[0]["values"]["country"], "Peru")
        self.assertEqual(mapped[0]["values"]["continent"], "Americas")
        self.assertEqual(mapped[0]["values"]["year"], "1952")


if __name__ == "__main__":
    unittest.main()