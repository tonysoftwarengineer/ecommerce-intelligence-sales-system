from src.ingest import ingest
from src.stages.analyze import run_analysis
from src.stages.clean import clean_all
from src.stages.join import join_all


def run_pipeline() -> dict:
    raw = ingest()
    cleaned = clean_all(raw)
    joined = join_all(cleaned)
    return run_analysis(joined)
