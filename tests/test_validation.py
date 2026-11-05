import unittest

from src.validation import (
    ConflictingKeyError,
    ValidationRun,
    deduplicate_and_check_conflicts,
    find_conflicts,
    process_reader_records,
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
            allowed_years=set(range(1952, 2008, 5)),
            max_life_exp=120.0,
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

    def test_whole_numbers_written_with_decimal_point(self):
        res = self.validator.validate_record(make_rec(year="1987.0", pop="60000000.0"))
        self.assertTrue(res.is_valid)
        self.assertEqual(res.clean_record["year"], 1987)
        self.assertIsInstance(res.clean_record["year"], int)
        self.assertEqual(res.clean_record["pop"], 60000000)
        self.assertIsInstance(res.clean_record["pop"], int)
        self.assertFalse(self.validator.validate_record(make_rec(year="1987.5")).is_valid)

    # Category 8: non-finite / out-of-range
    def test_non_finite_values(self):
        for bad in ("NaN", "inf", "-inf"):
            res = self.validator.validate_record(make_rec(lifeExp=bad))
            self.assertFalse(res.is_valid, bad)
            self.assertIn("Non-finite", res.reason)

    def test_out_of_range_values(self):
        res = self.validator.validate_record(make_rec(year="1800"))
        self.assertFalse(res.is_valid)
        self.assertIn("not in allowed years", res.reason)

        res = self.validator.validate_record(make_rec(continent="Atlantis"))
        self.assertFalse(res.is_valid)
        self.assertIn("Invalid continent", res.reason)

    def test_year_must_be_one_of_allowed_years(self):
        for bad in ("1953", "1999"):
            res = self.validator.validate_record(make_rec(year=bad))
            self.assertFalse(res.is_valid, bad)
            self.assertIn("not in allowed years", res.reason)
        self.assertTrue(self.validator.validate_record(make_rec(year="1997")).is_valid)

    def test_life_exp_upper_bound(self):
        res = self.validator.validate_record(make_rec(lifeExp="150"))
        self.assertFalse(res.is_valid)
        self.assertEqual(res.reason, "Out-of-range lifeExp: '150'")
        self.assertTrue(self.validator.validate_record(make_rec(lifeExp="120")).is_valid)
        self.assertFalse(self.validator.validate_record(make_rec(lifeExp="120.1")).is_valid)

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

    def test_reader_records_keep_original_text(self):
        clean = {"country": "Peru", "continent": "Americas", "year": "abc",
                 "lifeExp": "65.0", "pop": "60000000", "gdpPercap": "2000.5"}
        values = dict(clean, country=" Peru ")
        records = [{"source_file": "f", "source_record": 1,
                    "clean": clean, "values": values}]
        valid, quarantine = process_reader_records(records, self.validator, "f")
        self.assertEqual(valid, [])
        self.assertEqual(quarantine[0]["country"], " Peru ")
        self.assertEqual(quarantine[0]["source_record"], 1)
        self.assertEqual(quarantine[0]["year"], "abc")

    def test_reader_records_valid_path(self):
        clean = {"country": "Peru", "continent": "Americas", "year": "1987",
                 "lifeExp": "65.0", "pop": "60000000", "gdpPercap": "2000.5"}
        records = [{"source_record": 7, "clean": clean, "values": clean}]
        valid, quarantine = process_reader_records(records, self.validator, "f.json")
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["source_file"], "f.json")
        self.assertEqual(valid[0]["source_record"], 7)
        self.assertEqual(quarantine, [])

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
        with
