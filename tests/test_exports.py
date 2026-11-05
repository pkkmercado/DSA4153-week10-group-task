
import unittest
import tempfile
import copy
from pathlib import Path
import pandas as pd

from src.exports import (
    compare_tables,
    export_canonical,
    reload_and_check,
    create_staging_folder,
    finalize_outputs,
    write_audit_log,
    write_validation_report,
    write_failure_report
)


class TestExports(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.output = Path(self.folder.name) / "outputs"

        self.sample = [
            {
                "country": "Philippines",
                "continent": "Asia",
                "year": 2007,
                "lifeExp": 71.688,
                "pop": 91077287,
                "gdpPercap": 3190.481016
            },
            {
                "country": "Thailand",
                "continent": "Asia",
                "year": 2007,
                "lifeExp": 70.616,
                "pop": 65068149,
                "gdpPercap": 7458.396327
            }]

    def tearDown(self):
        self.folder.cleanup()

    def test_normal_recovery(self):
        tables = [copy.deepcopy(self.sample) for _ in range(4)]

        canonical = compare_tables(tables)
        self.assertEqual(len(canonical), 2)

        export_canonical(canonical, self.output)
        self.assertTrue(reload_and_check(canonical, self.output))

        for extension in ["csv", "xlsx", "json", "parquet"]:
            self.assertTrue(
                (self.output / f"canonical.{extension}").exists()
            )

    def test_reordered_records(self):
        tables = [copy.deepcopy(self.sample) for _ in range(4)]

        tables[1].reverse()
        tables[3].reverse()

        canonical = compare_tables(tables)
        self.assertEqual(len(canonical), 2)

    def test_corrupted_export(self):
        export_canonical(self.sample, self.output)

        csv_file = self.output / "canonical.csv"
        data = pd.read_csv(csv_file)
        data.loc[0, "pop"] = 999999
        data.to_csv(csv_file, index=False)

        with self.assertRaises(ValueError):
            reload_and_check(self.sample, self.output)

    def test_mismatched_values(self):
        tables = [copy.deepcopy(self.sample) for _ in range(4)]
        tables[2][0]["pop"] = 999999

        with self.assertRaises(ValueError):
            compare_tables(tables)

    def test_staging(self):
        staging = create_staging_folder(self.output)

        export_canonical(self.sample, staging)
        self.assertTrue(reload_and_check(self.sample, staging))

        finalize_outputs(staging, self.output)

        self.assertTrue((self.output / "canonical.csv").exists())
        self.assertTrue((self.output / "canonical.parquet").exists())

    def test_reports(self):
        write_audit_log(
            [{"step": "export", "status": "PASS", "details": "Done"}],
            self.output
        )

        write_validation_report(
            [{"check": "comparison", "status": "PASS", "details": "Match"}],
            self.output
        )

        self.assertTrue((self.output / "audit_log.csv").exists())
        self.assertTrue((self.output / "validation.csv").exists())

    def test_failure_handling(self):
        self.output.mkdir()

        original = self.output / "canonical.csv"
        original.write_text("previous successful data")

        write_failure_report("Test failure", self.output)

        self.assertEqual(
            original.read_text(),
            "previous successful data"
        )

        failure_report = self.output.parent / "outputs_failed_validation.csv"
        self.assertTrue(failure_report.exists())

    def test_duplicate_records(self):
        duplicate_data = copy.deepcopy(self.sample)
        duplicate_data.append(copy.deepcopy(self.sample[0]))

        tables = [
            duplicate_data,
            copy.deepcopy(self.sample),
            copy.deepcopy(self.sample),
            copy.deepcopy(self.sample)
        ]

        with self.assertRaisesRegex(
            ValueError, "Duplicate country-year key"
        ):
            compare_tables(tables)

    def test_staging_rollback(self):
        self.output.mkdir()

        original = self.output / "canonical.csv"
        original.write_text("previous successful data")

        staging = Path(create_staging_folder(self.output))
        (staging / "canonical.csv").write_text("new data")

        backup = self.output.with_name("outputs_backup")
        backup.mkdir()

        with self.assertRaises(FileExistsError):
            finalize_outputs(staging, self.output)

        self.assertEqual(
            original.read_text(),
            "previous successful data"
        )


if __name__ == "__main__":
    unittest.main()
