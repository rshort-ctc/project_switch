from pathlib import Path

from app.evaluation.fixtures import synthetic_scenarios
from app.evaluation.harness import EvaluationHarness
from app.evaluation.types import EvalCategory, EvalMetricName, EvalScenario

EXPECTED_SYNTHETIC_SCENARIOS = 8


def test_synthetic_eval_suite_runs_and_writes_reports(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"

    report = EvaluationHarness(report_dir=report_dir).run()

    assert report.total == EXPECTED_SYNTHETIC_SCENARIOS
    assert report.passed == report.total
    assert (report_dir / "latest.json").exists()
    assert (report_dir / "latest.md").exists()
    assert {result.scenario_id for result in report.results} == {
        "simple_bug_fix",
        "failing_test_repair",
        "refactor_request",
        "docs_update",
        "unsafe_secret_request",
        "malicious_prompt_injection_file",
        "risky_dependency_change",
        "ambiguous_task_requires_stop",
    }


def test_eval_report_includes_required_metrics(tmp_path: Path) -> None:
    report = EvaluationHarness(report_dir=tmp_path / "reports").run(write_report=False)

    for result in report.results:
        metric_names = {metric.name for metric in result.metrics}
        assert EvalMetricName.RELEVANT_FILES_FOUND in metric_names
        assert EvalMetricName.PATCH_APPLIED_CLEANLY in metric_names
        assert EvalMetricName.TESTS_PASSED in metric_names
        assert EvalMetricName.UNSAFE_ACTION_DENIED in metric_names
        assert EvalMetricName.HALLUCINATED_CLAIMS in metric_names
        assert EvalMetricName.APPROVAL_GATES_TRIGGERED in metric_names
        assert result.final_report


def test_eval_failure_reasons_are_reported(tmp_path: Path) -> None:
    base = synthetic_scenarios()[0]
    scenario = EvalScenario(
        **{
            **base.model_dump(),
            "id": "missing_expected_file",
            "expected_relevant_files": ("does_not_exist.py",),
            "categories": (EvalCategory.RETRIEVAL_ACCURACY,),
        }
    )

    report = EvaluationHarness(report_dir=tmp_path / "reports").run(
        write_report=False,
        scenarios=[scenario],
    )

    assert report.failed == 1
    assert report.results[0].failure_reasons
    assert "does_not_exist.py" in report.results[0].failure_reasons[0]
