import pandas as pd

from src.ingest import ingest
from src.stages.analyze import run_analysis
from src.stages.clean import clean_all
from src.stages.join import join_all


def build_dataset() -> pd.DataFrame:
    raw = ingest()
    cleaned = clean_all(raw)
    return join_all(cleaned)


def run_pipeline() -> dict:
    return run_analysis(build_dataset())
