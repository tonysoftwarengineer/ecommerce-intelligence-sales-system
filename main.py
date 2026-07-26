from src.pipeline import run_pipeline
from src.stages.report import generate_report


def main() -> None:
    results = run_pipeline()
    generate_report(results)


if __name__ == "__main__":
    main()
