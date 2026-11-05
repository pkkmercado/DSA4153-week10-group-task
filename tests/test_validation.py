import unittest

from src.validation import (
    ConflictingKeyError,
    ValidationRun,
    deduplicate_and_check_conflicts,
    find_conflicts,
    process_validations_and_quarantine,
)


def make_rec(**overrides):
    rec = {
        "country": "Philippines", "continent": "Asia", "year": "1987",
        "lifeExp": "65.0", "pop": "60000000", "gdpPercap": "2000.5",
        "source_file": "test.csv", "source_record": 1,
    }
    rec.update(overrides)
    return rec


def make_clean(**overrides):
    rec = {
        "country": "Philippines", "continent": "Asia", "year": 1987,
        "lifeExp": 65.0, "pop": 60000000, "gdpPercap": 2000.5,
        "source_file": "test.csv", "source_record": 1,
    }
    rec.update(overrides)
    return rec


class TestRecordValidationAndDeduplication(unittest.TestCase):
    def setUp(self):
        self.validator = ValidationRun(
            allowed_continents={"Asia", "Europe", "Africa", "Americas", "Oceania"},
            allowed_year_min=1952,
            allowed_year_max=2007,
        )

    def test_valid_record_is_trimmed_and_cast(self):
        res = self.validator.validate_record(make_rec(country="  Philippines "))
        self.assertTrue(res.is_valid)
        self.assertEqual(res.clean_record["country"], "Philippines")
        self.assertIsInstance(res.clean_record["year"], int)
        self.assertIsInstance(res.clean_record["pop"], int)

    # Category 6: unparseable number
    def test_unparseable_number(self):
        res = self.validator.validate_record(make_rec(lifeExp="INVALID_FLOAT"))
        self.assertFalse(res.is_valid)
        self.assertIn("Unparseable numeric value", res.reason)

    # Category 7: fractional year / population
    def test_fractional_year_and_population(self):
        res_year = self.validator.validate_record(make_rec(year="1987.5"))
        self.assertFalse(res_year.is_valid)
        self.assertIn("Fractional year", res_year.reason)

        res_pop = self.validator.validate_record(make_rec(pop="60000000.75"))
        self.assertFalse(res_pop.is_valid)
        self.assertIn("Fractional population", res_pop.reason)

    # Category 8: non-finite / out-of-range
    def test_non_finite_values(self):
        for bad in ("NaN", "inf", "-inf"):
            res = self.validator.validate_record(make_rec(lifeExp=bad))
            self.assertFalse(res.is_valid, bad)
            self.assertIn("Non-finite", res.reason)

    def test_out_of_range_values(self):
        res = self.validator.validate_record(make_rec(year="1800"))
        self.assertFalse(res.is_valid)
        self.assertIn("out of allowed range", res.reason)

        res = self.validator.validate_record(make_rec(continent="Atlantis"))
        self.assertFalse(res.is_valid)
        self.assertIn("Invalid continent", res.reason)

    def test_empty_identifier_and_missing_value(self):
        self.assertFalse(self.validator.validate_record(make_rec(country="  ")).is_valid)
        res = self.validator.validate_record(make_rec(pop=""))
        self.assertFalse(res.is_valid)
        self.assertIn("Missing pop", res.reason)

    def test_quarantine_keeps_original_values(self):
        records = [make_rec(), make_rec(source_record=2, year="abc")]
        valid, quarantine = process_validations_and_quarantine(records, self.validator)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(quarantine), 1)
        self.assertEqual(quarantine[0]["source_record"], 2)
        self.assertEqual(quarantine[0]["year"], "abc")

    # Category 9: exact duplicates
    def test_exact_duplicates(self):
        records = [make_clean(), make_clean(source_record=2)]
        deduped, dup_log = deduplicate_and_check_conflicts(records)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(len(dup_log), 1)
        self.assertEqual(dup_log[0]["source_record"], 2)

    # Category 10: conflicting keys
    def test_conflicting_keys(self):
        records = [make_clean(), make_clean(lifeExp=70.0, source_record=2)]
        with self.assertRaises(ConflictingKeyError):
            find_conflicts(records)
        with self.assertRaises(ConflictingKeyError):
            deduplicate_and_check_conflicts(records)


if __name__ == "__main__":
    unittest.main()
