import logging
import shutil
from pathlib import Path

import kagglehub
import pandas as pd

from config import DATA_DIR, KAGGLE_DATASET, TABLE_FILES

logger = logging.getLogger(__name__)


def _all_tables_present() -> bool:
    return all((DATA_DIR / filename).exists() for filename in TABLE_FILES.values())


def download_to_local_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if _all_tables_present():
        logger.debug(
            "All %d tables already present in %s, skipping download", len(TABLE_FILES), DATA_DIR
        )
        return

    logger.info("Downloading %s via kagglehub (~43MB, first run only)", KAGGLE_DATASET)
    cache_path = kagglehub.dataset_download(KAGGLE_DATASET)
    for filename in TABLE_FILES.values():
        source = Path(cache_path) / filename
        destination = DATA_DIR / filename
        if not destination.exists():
            shutil.copy(source, destination)


def load_tables() -> dict[str, pd.DataFrame]:
    tables = {}
    for name, filename in TABLE_FILES.items():
        file_path = DATA_DIR / filename
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
