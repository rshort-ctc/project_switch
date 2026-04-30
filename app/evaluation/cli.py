import json
from pathlib import Path
from typing import Annotated

import typer

from app.evaluation.harness import EvaluationHarness, report_as_summary

app = typer.Typer(help="Run local SWITCH evaluation suites.")


@app.command("list")
def list_suites() -> None:
    typer.echo("synthetic")


@app.command("run")
def run_eval(
    suite: Annotated[str, typer.Option("--suite", help="Evaluation suite name.")] = "synthetic",
    report_dir: Annotated[
        Path,
        typer.Option("--report-dir", help="Directory for generated eval reports."),
    ] = Path("evals/reports"),
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON report.")] = False,
) -> None:
    report = EvaluationHarness(report_dir=report_dir).run(suite=suite, write_report=True)
    if json_output:
        typer.echo(json.dumps(report_as_summary(report), indent=2))
        return
    typer.echo(f"Evaluation suite: {suite}")
    typer.echo(f"Passed: {report.passed}/{report.total}")
    typer.echo(f"Failed: {report.failed}")
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        typer.echo(f"{status}\t{result.scenario_id}\t{result.name}")
        for reason in result.failure_reasons:
            typer.echo(f"  - {reason}")


if __name__ == "__main__":
    app()
