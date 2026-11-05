"""Reader checks. Fixtures are built in a temp folder, never in data/."""
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from src.csv_excel_readers import (
    check_input_file,
    read_csv_records,
    read_excel_records,
)
from src.errors import InputFileError

CSV_SETTINGS = {"encoding": "cp1252", "delimiter": ";", "comment_prefix": "#"}
HEADER = ["land", "kontinent", "jahr", "meta"]


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_csv(self, name="a.csv", rows=("Côte;Africa;1952;x", "Peru;Americas;1957;y")):
        p = self.dir / name
        text = "# comment 1\n# comment 2\n" + ";".join(HEADER) + "\n" + "\n".join(rows) + "\n"
        p.write_bytes(text.encode("cp1252"))
        return p

    def test_normal_csv_counts_and_positions(self):
        header, recs = read_csv_records(self.make_csv(), CSV_SETTINGS)
        self.assertEqual(header, HEADER)
        self.assertEqual(len(recs), 2)
        self.assertEqual([r["source_record"] for r in recs], [1, 2])
        self.assertEqual(recs[0]["values"]["land"], "Côte")  # CP1252 decoded
        self.assertEqual(recs[1]["values"]["jahr"], "1957")  # kept as text

    def test_comment_line_count_setting(self):
        settings = {"encoding": "cp1252", "delimiter": ";", "comment_lines": 2}
        _, recs = read_csv_records(self.make_csv(), settings)
        self.assertEqual(len(recs), 2)

    def test_csv_keeps_whitespace_and_bad_values_raw(self):
        p = self.make_csv(rows=(" Peru ;Americas;19x2;y",))
        _, recs = read_csv_records(p, CSV_SETTINGS)
        self.assertEqual(recs[0]["values"]["land"], " Peru ")
        self.assertEqual(recs[0]["values"]["jahr"], "19x2")

    def test_normal_excel_counts_and_readme_ignored(self):
        p = self.dir / "a.xlsx"
        wb = Workbook()
        wb.active.title = "Readme"
        wb.active.append(["notes only"])
        obs = wb.create_sheet("observations")
        obs.append(HEADER)
        obs.append(["Peru", "Americas", 1952, "x"])
        obs.append(["Chad", "Africa", 1957, "y"])
        wb.save(p)
        header, recs = read_excel_records(p, {"sheet": "observations"})
        self.assertEqual(header, HEADER)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["values"]["jahr"], "1952")
        self.assertEqual(recs[1]["source_record"], 2)

    def test_excel_missing_sheet_is_file_error(self):
        p = self.dir / "b.xlsx"
        wb = Workbook()
        wb.active.title = "Readme"
        wb.save(p)
        with self.assertRaises(InputFileError):
            read_excel_records(p, {"sheet": "observations"})

    def test_missing_file(self):
        with self.assertRaises(InputFileError):
            check_input_file(self.dir / "nope.csv")

    def test_unsupported_existing_format(self):
        p = self.dir / "unsupported.txt"
        p.write_text("hello")
        with self.assertRaises(InputFileError):
            check_input_file(p)


if __name__ == "__main__":
    unittest.main()