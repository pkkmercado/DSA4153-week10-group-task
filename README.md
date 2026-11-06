# DSA4153-week10-group-task


# Four-Format Data Recovery and Validation

## Project Description

This project was developed for the DSA4153 Programming for Data Science Week 10 Group Programming Challenge. It focuses on reading, cleaning, validating, comparing, and exporting data from four different file formats: CSV, Excel, JSON, and Parquet.

The program processes the provided Gapminder dataset, which contains information about countries, population, life expectancy, and GDP per capita across different years. It checks the records for missing values, invalid data, duplicates, and inconsistencies between formats.

After successful validation, the program creates a canonical dataset and generates the required analysis results and reports.

## Group Members and Assigned Tasks

| Group Member | Assigned Task |
|---|---|
| Princess Kassy Mercado | Task 1 – CSV and Excel Readers |
| Arianne Sumalinog | Task 2 – JSON and Parquet Readers and Normalization |
| Rianne Rose Mendoza | Task 3 – Data Validation |
| Keanna Polvoriza | Task 4 – Data Analysis |
| Olivia Baña | Task 5 – Exports, Comparison, and Pipeline Integration |

## Program Features

1. **Data Reading** – Reads the supplied CSV, Excel, JSON, and Parquet files.
2. **Data Normalization** – Converts the records into a consistent structure with standardized column names and data types.
3. **Data Validation** – Checks for missing or invalid values, duplicate records, and conflicting country-year keys.
4. **Cross-Format Comparison** – Compares the cleaned datasets to check whether all four formats contain consistent records.
5. **Data Analysis** – Generates selected-year records, country history, and population index results.
6. **Data Exporting** – Saves the canonical dataset in four formats and generates validation and audit reports.
7. **Error Handling** – Reports processing failures and prevents incomplete results from replacing previously successful outputs.

## Project Structure

```text
DSA4153-week10-group-task/
│
├── data/
│   ├── README.txt
│   ├── country_records.csv
│   ├── country_records.xlsx
│   ├── country_records.json
│   ├── country_records.parquet
│   ├── manifest.json
│   ├── conflicting_key.csv
│   ├── missing_column.csv
│   └── unsupported.txt
│
├── src/
│   ├── __init__.py
│   ├── analysis.py
│   ├── csv_excel_readers.py
│   ├── errors.py
│   ├── exports.py
│   ├── json_parquet_readers.py
│   ├── matrix_ops.py
│   ├── normalize.py
│   └── validation.py
│
├── tests/
│   ├── test_analysis.py
│   ├── test_csv_excel_readers.py
│   ├── test_exports.py
│   ├── test_json_parquet_mapping.py
│   └── test_validation.py
│
├── main.py
├── config.json
├── requirements.txt
└── README.md
```

The `outputs/` directory is generated after a successful program execution.

## Requirements

The project uses Python 3.11 and the following libraries:

- pandas
- numpy
- openpyxl
- pyarrow

Install the required libraries using:

```bash
py -m pip install -r requirements.txt
```

For systems that use the `python` command instead of `py`, replace `py` with `python`.

## How to Run the Program

### Step 1: Download the Repository

Download the project ZIP from GitHub or clone the repository:

```bash
git clone https://github.com/pkkmercado/DSA4153-week10-group-task.git
```

### Step 2: Open the Project

Open the project folder in Visual Studio Code or another Python development environment.

### Step 3: Install the Dependencies

Open the terminal in the project directory and run:

```bash
py -m pip install -r requirements.txt
```

### Step 4: Check the Configuration

The `config.json` file contains the program's input and output paths.

```json
{
  "data_dir": "data",
  "output_dir": "outputs",
  "manifest_path": "data/manifest.json",
  "reporting_year": 2007
}
```

The program reads the input and output paths from this file. The dataset manifest provides the analysis settings.

### Step 5: Run the Program

Execute the following command:

```bash
py main.py --config config.json
```

The program can also run using its default directory settings:

```bash
py main.py
```

After successful execution, the program displays a success message and saves the generated files in the `outputs/` directory.

## Data Processing and Validation

The program processes four versions of the same dataset. Each input format contains 1,712 raw records.

The validation process identifies six invalid records and two exact duplicate records per format. After cleaning, each format contains 1,704 valid records.

The program then compares the cleaned datasets across all four formats. Since they represent the same underlying data, the final canonical dataset contains **1,704 records**, rather than combining all four copies into one larger dataset.

The canonical dataset uses the following columns:

- `country`
- `continent`
- `year`
- `lifeExp`
- `pop`
- `gdpPercap`

The program uses `country` and `year` as the record key when checking consistency.

## Generated Output Files

After successful execution, the program generates 11 output files.

| Output File | Description |
|---|---|
| `canonical.csv` | Cleaned canonical dataset in CSV format |
| `canonical.xlsx` | Cleaned canonical dataset in Excel format |
| `canonical.json` | Cleaned canonical dataset in JSON format |
| `canonical.parquet` | Cleaned canonical dataset in Parquet format |
| `quarantine.csv` | Records excluded during validation |
| `duplicate_log.csv` | Duplicate records identified during processing |
| `validation.csv` | Results of validation and consistency checks |
| `audit_log.csv` | Record of processing and validation activities |
| `asia_selected_year.csv` | Records of Asian countries for 2007 |
| `country_history.csv` | Historical records for the Philippines |
| `population_index.csv` | Population index results for the Philippines, Indonesia, and Thailand |

The population index analysis uses 1982 as the base year, with an index value of 100.

## Running the Tests

The project includes unit tests for the different program components. These tests check data reading, normalization, validation, analysis, and exporting.

Run all available unit tests using:

```bash
py -m unittest discover -s tests -p "test_*.py" -v
```

The terminal displays the results of each test, including any errors or failures.

The group records its verified test results in `test_results.txt`.

## Error Handling

The program includes error handling for invalid inputs, processing failures, and inconsistencies between datasets.

When processing fails, the program reports the error and returns a nonzero exit status. It also creates `outputs_failed_validation.csv` in the project root directory.

The program uses a temporary staging directory while generating its outputs. It publishes the completed files only after successful processing and validation. This prevents incomplete results from replacing previously successful outputs.

The provided `conflicting_key.csv`, `missing_column.csv`, and `unsupported.txt` files are available for testing invalid or unsupported input scenarios.

## GitHub Repository and Contributions

The group uses GitHub for version control and collaboration. Members develop their assigned components, create commits, and review changes before integration.

**Repository:** https://github.com/pkkmercado/DSA4153-week10-group-task

Individual contributions, code references, test files, and review records are documented in `contributions.csv`.

## Dataset

The project uses the historical Gapminder dataset supplied by the instructor for the DSA4153 Week 10 Group Programming Challenge.

The dataset contains country-level observations, including population, life expectancy, and GDP per capita, across multiple years.

The provided files include modified records and additional test inputs for evaluating the program's data recovery and validation capabilities.
