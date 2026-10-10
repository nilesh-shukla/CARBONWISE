"""Run leakage-safe validation baselines for the C3.3.1 synthetic experiment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ml.experiment import (
    DEFAULT_DATASET_PATH,
    DatasetValidationError,
    load_dataset,
    run_baseline_experiment,
    run_candidate_comparison,
    run_final_test_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="validated v1 CSV path (defaults to the repository dataset)",
    )
    parser.add_argument(
        "--split-seed", type=int, default=42, help="train/validation/test split seed"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--compare-models",
        action="store_true",
        help="fit candidate models on the train partition and compare on validation",
    )
    modes.add_argument(
        "--final-test",
        action="store_true",
        help="evaluate the frozen model configurations and baselines on the held-out test partition",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional new JSON result path; existing files are never overwritten",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = load_dataset(args.dataset)
        if args.final_test:
            results = run_final_test_evaluation(data, split_seed=args.split_seed)
        elif args.compare_models:
            results = run_candidate_comparison(data, split_seed=args.split_seed)
        else:
            results = run_baseline_experiment(data, split_seed=args.split_seed)
        results["dataset"] = {
            "path": str(args.dataset.expanduser().resolve()),
            "rows": len(data),
        }
        rendered = json.dumps(results, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            output = args.output.expanduser().resolve()
            source = args.dataset.expanduser().resolve()
            if output == source:
                raise ValueError(
                    "result output path must not overwrite the source dataset"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                with output.open("x", encoding="utf-8", newline="\n") as result_file:
                    result_file.write(rendered)
            except FileExistsError as exc:
                raise ValueError(
                    f"result file already exists and will not be overwritten: {output}"
                ) from exc
            result_kind = (
                "final test evaluation" if args.final_test else "validation results"
            )
            print(f"Wrote {result_kind} to {output}")
    except (DatasetValidationError, ValueError, OSError) as exc:
        print(f"ML baseline experiment failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
