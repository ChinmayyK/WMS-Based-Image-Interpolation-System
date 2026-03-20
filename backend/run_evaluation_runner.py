from app.services.evaluation import run_evaluation_suite


def main() -> None:
    report = run_evaluation_suite()
    print("Evaluation complete")
    print(f"Datasets: {report['datasetCount']}")
    print(f"Samples: {report['sampleCount']}")
    print(f"JSON: {report['reportPaths']['latestJsonPath']}")
    print(f"HTML: {report['reportPaths']['latestHtmlPath']}")


if __name__ == "__main__":
    main()
