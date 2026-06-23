from __future__ import annotations
import csv
from pathlib import Path
from constants import REQUIRED_COLUMNS

def load_csv_native(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV file is missing a header row")
            missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")
            return [{k: (v or "") for k, v in row.items()} for row in reader]
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must be UTF-8 encoded") from error
    except csv.Error as error:
        raise ValueError(f"CSV could not be parsed: {error}") from error

def load_csv_pandas(path: Path) -> list[dict[str, str]]:
    import pandas as pd
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must be UTF-8 encoded") from error
    except pd.errors.EmptyDataError as error:
        raise ValueError("CSV file is missing a header row") from error
    except pd.errors.ParserError as error:
        raise ValueError(f"CSV could not be parsed: {error}") from error
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")
    return [{k: str(row.get(k, "") or "") for k in REQUIRED_COLUMNS} for row in frame.to_dict(orient="records")]

def load_csv(path: Path, engine: str = "native") -> list[dict[str, str]]:
    if engine == "pandas":
        return load_csv_pandas(path)
    if engine == "native":
        return load_csv_native(path)
    raise ValueError(f"Unsupported engine: {engine}")
