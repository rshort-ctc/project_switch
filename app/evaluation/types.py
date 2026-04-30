from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class EvalCategory(StrEnum):
    RETRIEVAL_ACCURACY = "retrieval_accuracy"
    FILE_LOCALIZATION = "file_localization"
    PATCH_CORRECTNESS = "patch_correctness"
    TEST_PASS_RATE = "test_pass_rate"
    REGRESSION_AVOIDANCE = "regression_avoidance"
    POLICY_COMPLIANCE = "policy_compliance"
    SECRET_HANDLING = "secret_handling"
    PROMPT_INJECTION_RESISTANCE = "prompt_injection_resistance"
    DIFF_REVIEW_QUALITY = "diff_review_quality"
    FINAL_REPORT_TRUTHFULNESS = "final_report_truthfulness"


class EvalMetricName(StrEnum):
    RELEVANT_FILES_FOUND = "relevant_files_found"
    PATCH_APPLIED_CLEANLY = "patch_applied_cleanly"
    TESTS_PASSED = "tests_passed"
    UNSAFE_ACTION_DENIED = "unsafe_action_denied"
    HALLUCINATED_CLAIMS = "hallucinated_claims_count"
    APPROVAL_GATES_TRIGGERED = "approval_gates_triggered_correctly"


class PatchPlan(BaseModel):
    path: Path
    original_text: str
    replacement_text: str
    human_approved: bool = False


class EvalScenario(BaseModel):
    id: str
    name: str
    task: str
    categories: tuple[EvalCategory, ...]
    files: dict[str, str]
    expected_relevant_files: tuple[str, ...]
    patch: PatchPlan | None = None
    validation_command: tuple[str, ...] | None = None
    expect_tests_pass: bool = False
    expect_unsafe_denied: bool = False
    expect_approval_required: bool = False
    expect_stop: bool = False
    secret_markers: tuple[str, ...] = ()


class EvalMetric(BaseModel):
    name: EvalMetricName
    passed: bool
    value: int | bool | str
    reason: str


class EvalScenarioResult(BaseModel):
    scenario_id: str
    name: str
    categories: tuple[EvalCategory, ...]
    passed: bool
    metrics: list[EvalMetric]
    failure_reasons: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    validation_exit_code: int | None = None
    final_report: str = ""


class EvalReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total: int
    passed: int
    failed: int
    results: list[EvalScenarioResult]

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total
