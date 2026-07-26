import shutil
from pathlib import Path

import kagglehub
import pandas as pd

from config import DATA_DIR, KAGGLE_DATASET, TABLE_FILES


def _all_tables_present() -> bool:
    return all((Path(DATA_DIR) / filename).exists() for filename in TABLE_FILES.values())


def download_to_local_data_dir() -> None:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    if _all_tables_present():
        return

    cache_path = kagglehub.dataset_download(KAGGLE_DATASET)
    for filename in TABLE_FILES.values():
        source = Path(cache_path) / filename
        destination = Path(DATA_DIR) / filename
        if not destination.exists():
            shutil.copy(source, destination)


def load_tables() -> dict[str, pd.DataFrame]:
    tables = {}
    for name, filename in TABLE_FILES.items():
        file_path = Path(DATA_DIR) / filename
        try:
            tables[name] = pd.read_csv(file_path)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load required table '{name}' from {filename}: {e}"
            ) from e
    return tables


def ingest() -> dict[str, pd.DataFrame]:
    download_to_local_data_dir()
    return load_tables()
