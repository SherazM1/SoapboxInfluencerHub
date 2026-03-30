from __future__ import annotations

from dataclasses import dataclass
import re

from core.mapper import (
    MappingResult,
    RecruitingRow,
    Round1Row,
    WorkflowContentCheckRow,
    WorkflowDraftStageRow,
    WorkflowInfluencerDetailsRow,
    WorkflowLiveContentRow,
)
from core.parser import InfluencerRecord


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
VALID_SEVERITIES = {SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO}

STAGE_PARSED_RECORD = "parsed_record"
STAGE_MAPPED_WORKFLOW = "mapped_workflow"
STAGE_MAPPED_ROUNDS = "mapped_rounds"
STAGE_WRITE_READY = "write_ready"
VALID_STAGES = {
    STAGE_PARSED_RECORD,
    STAGE_MAPPED_WORKFLOW,
    STAGE_MAPPED_ROUNDS,
    STAGE_WRITE_READY,
}

SECTION_GLOBAL = "global"
SECTION_WORKFLOW_INFLUENCER_DETAILS = "workflow_influencer_details"
SECTION_WORKFLOW_DRAFT_STAGES = "workflow_draft_stages"
SECTION_WORKFLOW_LIVE_CONTENT = "workflow_live_content"
SECTION_WORKFLOW_CONTENT_CHECKS = "workflow_content_checks"
SECTION_ROUND_1 = "round_1"
SECTION_RECRUITING = "recruiting"
VALID_SECTIONS = {
    SECTION_GLOBAL,
    SECTION_WORKFLOW_INFLUENCER_DETAILS,
    SECTION_WORKFLOW_DRAFT_STAGES,
    SECTION_WORKFLOW_LIVE_CONTENT,
    SECTION_WORKFLOW_CONTENT_CHECKS,
    SECTION_ROUND_1,
    SECTION_RECRUITING,
}


@dataclass(slots=True)
class TemplateConstraints:
    """Template section capacities for write-readiness checks."""

    workflow_influencer_details_max_rows: int | None = 6
    workflow_draft_stages_max_rows: int | None = 20
    workflow_live_content_max_rows: int | None = 21
    workflow_content_checks_max_rows: int | None = 21
    round_1_max_rows: int | None = 129
    recruiting_max_rows: int | None = 129


@dataclass(slots=True)
class ValidationIssue:
    """Single structured validation issue."""

    severity: str
    stage: str
    section: str
    code: str
    message: str
    record_identifier: str
    field_name: str


@dataclass(slots=True)
class ValidationResult:
    """Validation output with aggregate status flags and counts."""

    is_valid: bool
    has_errors: bool
    has_warnings: bool
    issues: list[ValidationIssue]
    error_count: int
    warning_count: int
    info_count: int

    def issues_for_stage(self, stage: str) -> list[ValidationIssue]:
        """Return issues filtered by stage."""
        return [issue for issue in self.issues if issue.stage == stage]

    def issues_for_section(self, section: str) -> list[ValidationIssue]:
        """Return issues filtered by section."""
        return [issue for issue in self.issues if issue.section == section]

    def issues_for_severity(self, severity: str) -> list[ValidationIssue]:
        """Return issues filtered by severity."""
        return [issue for issue in self.issues if issue.severity == severity]


def validate_parsed_records(records: list[InfluencerRecord]) -> ValidationResult:
    """Validate parsed influencer records from parser output."""
    issues: list[ValidationIssue] = []

    for record in records:
        issues.extend(validate_influencer_record(record))

    issues.extend(detect_duplicate_record_candidates(records))
    return build_validation_result(issues)


def validate_mapping_result(mapping_result: MappingResult) -> ValidationResult:
    """Validate mapped workflow and rounds rows section by section."""
    issues: list[ValidationIssue] = []

    for index, row in enumerate(mapping_result.workflow_influencer_details_rows, start=1):
        issues.extend(validate_workflow_influencer_details_row(row, index))
    for index, row in enumerate(mapping_result.workflow_draft_stage_rows, start=1):
        issues.extend(validate_workflow_draft_stage_row(row, index))
    for index, row in enumerate(mapping_result.workflow_live_content_rows, start=1):
        issues.extend(validate_workflow_live_content_row(row, index))
    for index, row in enumerate(mapping_result.workflow_content_check_rows, start=1):
        issues.extend(validate_workflow_content_check_row(row, index))
    for index, row in enumerate(mapping_result.round_1_rows, start=1):
        issues.extend(validate_round_1_row(row, index))
    for index, row in enumerate(mapping_result.recruiting_rows, start=1):
        issues.extend(validate_recruiting_row(row, index))

    return build_validation_result(issues)


def validate_write_readiness(
    mapping_result: MappingResult,
    template_constraints: TemplateConstraints | None = None,
) -> ValidationResult:
    """Validate selected-set alignment and template-capacity safety."""
    constraints = template_constraints or TemplateConstraints()
    issues: list[ValidationIssue] = []

    if not mapping_result.workflow_influencer_details_rows:
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_WRITE_READY,
                section=SECTION_GLOBAL,
                code="empty_selected_set",
                message=(
                    "Selected influencer set is empty: "
                    "workflow_influencer_details_rows has no rows."
                ),
                record_identifier="",
                field_name="",
            )
        )

    issues.extend(
        detect_duplicate_selected_names(mapping_result.workflow_influencer_details_rows)
    )
    issues.extend(validate_selected_section_alignment(mapping_result))
    issues.extend(validate_template_capacity(mapping_result, constraints))

    return build_validation_result(issues)


def validate_campaign_data(
    records: list[InfluencerRecord],
    mapping_result: MappingResult,
    template_constraints: TemplateConstraints | None = None,
) -> ValidationResult:
    """Run all validator stages and merge outputs."""
    parsed_result = validate_parsed_records(records)
    mapping_result_validation = validate_mapping_result(mapping_result)
    write_ready_result = validate_write_readiness(mapping_result, template_constraints)
    return merge_validation_results(
        [parsed_result, mapping_result_validation, write_ready_result]
    )


def validate_influencer_record(record: InfluencerRecord) -> list[ValidationIssue]:
    """Validate one parsed record against parsed-record rules."""
    issues: list[ValidationIssue] = []
    record_identifier = build_record_identifier(record)

    has_name = has_text(record.canonical_name)
    has_email = has_text(record.email)
    has_handle = any(
        [
            has_text(record.instagram_handle),
            has_text(record.tiktok_handle),
            has_text(record.youtube_handle),
            has_text(record.facebook_handle),
        ]
    )
    has_phone = has_text(record.phone_raw) or has_text(record.phone_display)
    has_location = any(
        [
            has_text(record.location_display),
            has_text(record.city),
            has_text(record.state),
        ]
    )

    if not has_name:
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="missing_canonical_name",
                message="Parsed record is missing canonical_name.",
                record_identifier=record_identifier,
                field_name="canonical_name",
            )
        )

    if not has_email:
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="missing_email",
                message=f'Record "{record_identifier}" is missing email.',
                record_identifier=record_identifier,
                field_name="email",
            )
        )

    if not has_handle:
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="missing_all_handles",
                message=f'Record "{record_identifier}" is missing all handles.',
                record_identifier=record_identifier,
                field_name="handle",
            )
        )

    if not has_phone:
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="missing_phone",
                message=f'Record "{record_identifier}" is missing phone.',
                record_identifier=record_identifier,
                field_name="phone",
            )
        )

    if not has_location:
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="missing_location",
                message=f'Record "{record_identifier}" is missing location.',
                record_identifier=record_identifier,
                field_name="location",
            )
        )

    if has_name and not has_email and not has_handle and not has_phone and not has_location:
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_PARSED_RECORD,
                section=SECTION_GLOBAL,
                code="weak_partial_record",
                message=(
                    f'Record "{record_identifier}" has a name but is missing email, '
                    "all handles, phone, and location."
                ),
                record_identifier=record_identifier,
                field_name="",
            )
        )

    return issues


def detect_duplicate_record_candidates(records: list[InfluencerRecord]) -> list[ValidationIssue]:
    """Detect approximate duplicate parsed records based on identity overlap."""
    issues: list[ValidationIssue] = []
    seen_pair_to_identifier: dict[tuple[tuple[str, str], ...], str] = {}

    for record in records:
        identifier = build_record_identifier(record)
        parts = {
            "canonical_name": normalize_identifier(record.canonical_name),
            "email": normalize_identifier(record.email),
            "primary_handle_candidate": normalize_identifier(
                record.primary_handle_candidate
            ),
        }
        non_empty_parts = [(key, value) for key, value in parts.items() if value]
        if len(non_empty_parts) < 2:
            continue

        duplicate_of: str | None = None
        for pair_key in build_identity_pair_keys(non_empty_parts):
            existing_identifier = seen_pair_to_identifier.get(pair_key)
            if existing_identifier is not None:
                duplicate_of = existing_identifier
                break

        if duplicate_of is not None:
            issues.append(
                make_issue(
                    severity=SEVERITY_WARNING,
                    stage=STAGE_PARSED_RECORD,
                    section=SECTION_GLOBAL,
                    code="duplicate_record_candidate",
                    message=(
                        f'Record "{identifier}" appears duplicate-like compared to '
                        f'"{duplicate_of}".'
                    ),
                    record_identifier=identifier,
                    field_name="",
                )
            )
            continue

        for pair_key in build_identity_pair_keys(non_empty_parts):
            seen_pair_to_identifier[pair_key] = identifier

    return issues


def validate_workflow_influencer_details_row(
    row: WorkflowInfluencerDetailsRow,
    row_index: int,
) -> list[ValidationIssue]:
    """Validate one mapped Workflow Influencer Details row."""
    issues: list[ValidationIssue] = []
    identifier = row_identifier(row.influencer_name, row_index)

    if not has_text(row.influencer_name):
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_MAPPED_WORKFLOW,
                section=SECTION_WORKFLOW_INFLUENCER_DETAILS,
                code="missing_influencer_name",
                message=(
                    f"Workflow Influencer Details row {row_index} is missing influencer_name."
                ),
                record_identifier=identifier,
                field_name="influencer_name",
            )
        )
    if not has_text(row.handle_linked):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_WORKFLOW,
                section=SECTION_WORKFLOW_INFLUENCER_DETAILS,
                code="missing_handle",
                message=(
                    f'Workflow Influencer Details row "{identifier}" is missing handle.'
                ),
                record_identifier=identifier,
                field_name="handle_linked",
            )
        )
    if not has_text(row.phone_number):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_WORKFLOW,
                section=SECTION_WORKFLOW_INFLUENCER_DETAILS,
                code="missing_phone",
                message=(
                    f'Workflow Influencer Details row "{identifier}" is missing phone.'
                ),
                record_identifier=identifier,
                field_name="phone_number",
            )
        )
    if not has_text(row.email):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_WORKFLOW,
                section=SECTION_WORKFLOW_INFLUENCER_DETAILS,
                code="missing_email",
                message=(
                    f'Workflow Influencer Details row "{identifier}" is missing email.'
                ),
                record_identifier=identifier,
                field_name="email",
            )
        )

    return issues


def validate_workflow_draft_stage_row(
    row: WorkflowDraftStageRow,
    row_index: int,
) -> list[ValidationIssue]:
    """Validate one mapped Workflow Draft Stages row."""
    if has_text(row.influencer_name):
        return []
    return [
        make_issue(
            severity=SEVERITY_ERROR,
            stage=STAGE_MAPPED_WORKFLOW,
            section=SECTION_WORKFLOW_DRAFT_STAGES,
            code="missing_influencer_name",
            message=f"Workflow Draft Stages row {row_index} is missing influencer_name.",
            record_identifier=row_identifier(row.influencer_name, row_index),
            field_name="influencer_name",
        )
    ]


def validate_workflow_live_content_row(
    row: WorkflowLiveContentRow,
    row_index: int,
) -> list[ValidationIssue]:
    """Validate one mapped Workflow Live Content row."""
    if has_text(row.influencer_name):
        return []
    return [
        make_issue(
            severity=SEVERITY_ERROR,
            stage=STAGE_MAPPED_WORKFLOW,
            section=SECTION_WORKFLOW_LIVE_CONTENT,
            code="missing_influencer_name",
            message=f"Workflow Live Content row {row_index} is missing influencer_name.",
            record_identifier=row_identifier(row.influencer_name, row_index),
            field_name="influencer_name",
        )
    ]


def validate_workflow_content_check_row(
    row: WorkflowContentCheckRow,
    row_index: int,
) -> list[ValidationIssue]:
    """Validate one mapped Workflow Content Checks row."""
    if has_text(row.influencer_name):
        return []
    return [
        make_issue(
            severity=SEVERITY_ERROR,
            stage=STAGE_MAPPED_WORKFLOW,
            section=SECTION_WORKFLOW_CONTENT_CHECKS,
            code="missing_influencer_name",
            message=(
                f"Workflow Content Checks row {row_index} is missing influencer_name."
            ),
            record_identifier=row_identifier(row.influencer_name, row_index),
            field_name="influencer_name",
        )
    ]


def validate_round_1_row(row: Round1Row, row_index: int) -> list[ValidationIssue]:
    """Validate one mapped Round 1 row."""
    issues: list[ValidationIssue] = []
    identifier = row_identifier(row.influencer_name, row_index)

    if not has_text(row.influencer_name):
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_ROUND_1,
                code="missing_influencer_name",
                message=f"Round 1 row {row_index} is missing influencer_name.",
                record_identifier=identifier,
                field_name="influencer_name",
            )
        )
    if not has_text(row.handle):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_ROUND_1,
                code="missing_handle",
                message=f'Round 1 row "{identifier}" is missing handle.',
                record_identifier=identifier,
                field_name="handle",
            )
        )
    if not has_text(row.location):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_ROUND_1,
                code="missing_location",
                message=f'Round 1 row "{identifier}" is missing location.',
                record_identifier=identifier,
                field_name="location",
            )
        )

    return issues


def validate_recruiting_row(
    row: RecruitingRow,
    row_index: int,
) -> list[ValidationIssue]:
    """Validate one mapped Recruiting row."""
    issues: list[ValidationIssue] = []
    identifier = row_identifier(row.influencer_name, row_index)

    if not has_text(row.influencer_name):
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_RECRUITING,
                code="missing_influencer_name",
                message=f"Recruiting row {row_index} is missing influencer_name.",
                record_identifier=identifier,
                field_name="influencer_name",
            )
        )
    if not has_text(row.handle):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_RECRUITING,
                code="missing_handle",
                message=f'Recruiting row "{identifier}" is missing handle.',
                record_identifier=identifier,
                field_name="handle",
            )
        )
    if not has_text(row.platform):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_RECRUITING,
                code="missing_platform",
                message=f'Recruiting row "{identifier}" is missing platform.',
                record_identifier=identifier,
                field_name="platform",
            )
        )
    if not has_text(row.email):
        issues.append(
            make_issue(
                severity=SEVERITY_WARNING,
                stage=STAGE_MAPPED_ROUNDS,
                section=SECTION_RECRUITING,
                code="missing_email",
                message=f'Recruiting row "{identifier}" is missing email.',
                record_identifier=identifier,
                field_name="email",
            )
        )

    return issues


def validate_selected_section_alignment(
    mapping_result: MappingResult,
) -> list[ValidationIssue]:
    """Validate selected-section row counts and name order alignment."""
    issues: list[ValidationIssue] = []

    section_counts = {
        SECTION_WORKFLOW_INFLUENCER_DETAILS: len(
            mapping_result.workflow_influencer_details_rows
        ),
        SECTION_WORKFLOW_DRAFT_STAGES: len(mapping_result.workflow_draft_stage_rows),
        SECTION_WORKFLOW_LIVE_CONTENT: len(mapping_result.workflow_live_content_rows),
        SECTION_WORKFLOW_CONTENT_CHECKS: len(
            mapping_result.workflow_content_check_rows
        ),
        SECTION_ROUND_1: len(mapping_result.round_1_rows),
    }

    if len(set(section_counts.values())) > 1:
        counts_text = ", ".join(
            f"{section}={count}" for section, count in section_counts.items()
        )
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_WRITE_READY,
                section=SECTION_GLOBAL,
                code="selected_section_count_mismatch",
                message=f"Selected section row counts do not match: {counts_text}.",
                record_identifier="",
                field_name="",
            )
        )
        return issues

    expected_names = [
        alignment_name(row.influencer_name)
        for row in mapping_result.workflow_influencer_details_rows
    ]

    sections_to_compare: list[tuple[str, list[str]]] = [
        (
            SECTION_WORKFLOW_DRAFT_STAGES,
            [
                alignment_name(row.influencer_name)
                for row in mapping_result.workflow_draft_stage_rows
            ],
        ),
        (
            SECTION_WORKFLOW_LIVE_CONTENT,
            [
                alignment_name(row.influencer_name)
                for row in mapping_result.workflow_live_content_rows
            ],
        ),
        (
            SECTION_WORKFLOW_CONTENT_CHECKS,
            [
                alignment_name(row.influencer_name)
                for row in mapping_result.workflow_content_check_rows
            ],
        ),
        (
            SECTION_ROUND_1,
            [alignment_name(row.influencer_name) for row in mapping_result.round_1_rows],
        ),
    ]

    mismatched_sections = [
        section
        for section, section_names in sections_to_compare
        if section_names != expected_names
    ]

    if mismatched_sections:
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_WRITE_READY,
                section=SECTION_GLOBAL,
                code="selected_section_name_alignment_mismatch",
                message=(
                    "Selected influencer names are not aligned across sections: "
                    + ", ".join(mismatched_sections)
                    + "."
                ),
                record_identifier="",
                field_name="influencer_name",
            )
        )

    return issues


def detect_duplicate_selected_names(
    rows: list[WorkflowInfluencerDetailsRow],
) -> list[ValidationIssue]:
    """Detect duplicate selected influencer names from workflow details rows."""
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    duplicates: set[str] = set()

    for row in rows:
        normalized = normalize_identifier(row.influencer_name)
        if not normalized:
            continue
        if normalized in seen:
            duplicates.add(normalized)
        else:
            seen.add(normalized)

    for duplicate_name in sorted(duplicates):
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_WRITE_READY,
                section=SECTION_GLOBAL,
                code="duplicate_selected_influencer_name",
                message=f'Duplicate selected influencer name detected: "{duplicate_name}".',
                record_identifier=duplicate_name,
                field_name="influencer_name",
            )
        )

    return issues


def validate_template_capacity(
    mapping_result: MappingResult,
    template_constraints: TemplateConstraints,
) -> list[ValidationIssue]:
    """Validate section row counts against template constraints."""
    issues: list[ValidationIssue] = []

    capacity_checks = [
        (
            SECTION_WORKFLOW_INFLUENCER_DETAILS,
            len(mapping_result.workflow_influencer_details_rows),
            template_constraints.workflow_influencer_details_max_rows,
        ),
        (
            SECTION_WORKFLOW_DRAFT_STAGES,
            len(mapping_result.workflow_draft_stage_rows),
            template_constraints.workflow_draft_stages_max_rows,
        ),
        (
            SECTION_WORKFLOW_LIVE_CONTENT,
            len(mapping_result.workflow_live_content_rows),
            template_constraints.workflow_live_content_max_rows,
        ),
        (
            SECTION_WORKFLOW_CONTENT_CHECKS,
            len(mapping_result.workflow_content_check_rows),
            template_constraints.workflow_content_checks_max_rows,
        ),
        (
            SECTION_ROUND_1,
            len(mapping_result.round_1_rows),
            template_constraints.round_1_max_rows,
        ),
        (
            SECTION_RECRUITING,
            len(mapping_result.recruiting_rows),
            template_constraints.recruiting_max_rows,
        ),
    ]

    for section, count, max_rows in capacity_checks:
        if max_rows is None:
            continue
        if count <= max_rows:
            continue
        issues.append(
            make_issue(
                severity=SEVERITY_ERROR,
                stage=STAGE_WRITE_READY,
                section=section,
                code="template_capacity_exceeded",
                message=(
                    f'Section "{section}" has {count} rows, exceeding max_rows={max_rows}.'
                ),
                record_identifier="",
                field_name="",
            )
        )

    return issues


def make_issue(
    severity: str,
    stage: str,
    section: str,
    code: str,
    message: str,
    record_identifier: str,
    field_name: str,
) -> ValidationIssue:
    """Create a ValidationIssue with safe fallback enum values."""
    return ValidationIssue(
        severity=severity if severity in VALID_SEVERITIES else SEVERITY_WARNING,
        stage=stage if stage in VALID_STAGES else STAGE_PARSED_RECORD,
        section=section if section in VALID_SECTIONS else SECTION_GLOBAL,
        code=compact_text(code),
        message=compact_text(message),
        record_identifier=compact_text(record_identifier),
        field_name=compact_text(field_name),
    )


def build_validation_result(issues: list[ValidationIssue]) -> ValidationResult:
    """Build aggregate validation status and counts from issue list."""
    error_count = sum(issue.severity == SEVERITY_ERROR for issue in issues)
    warning_count = sum(issue.severity == SEVERITY_WARNING for issue in issues)
    info_count = sum(issue.severity == SEVERITY_INFO for issue in issues)

    return ValidationResult(
        is_valid=error_count == 0,
        has_errors=error_count > 0,
        has_warnings=warning_count > 0,
        issues=issues,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def merge_validation_results(results: list[ValidationResult]) -> ValidationResult:
    """Merge multiple ValidationResult objects into one."""
    merged_issues: list[ValidationIssue] = []
    for result in results:
        merged_issues.extend(result.issues)
    return build_validation_result(merged_issues)


def build_identity_pair_keys(
    identity_items: list[tuple[str, str]],
) -> list[tuple[tuple[str, str], ...]]:
    """Build deterministic pair keys from non-empty identity parts."""
    keys: list[tuple[tuple[str, str], ...]] = []
    for left_index in range(len(identity_items)):
        for right_index in range(left_index + 1, len(identity_items)):
            pair = sorted([identity_items[left_index], identity_items[right_index]])
            keys.append(tuple(pair))
    return keys


def build_record_identifier(record: InfluencerRecord) -> str:
    """Build parsed-record identifier preferring canonical name."""
    canonical = compact_text(record.canonical_name)
    if canonical:
        return canonical
    return f"row_{record.source_row_index}"


def row_identifier(influencer_name: str, row_index: int) -> str:
    """Build mapped-row identifier from influencer name or row index."""
    name = compact_text(influencer_name)
    if name:
        return name
    return f"row_{row_index}"


def alignment_name(value: str) -> str:
    """Normalize influencer names for alignment comparison."""
    return compact_text(value)


def normalize_identifier(value: str | None) -> str:
    """Normalize identifiers for duplicate-like comparisons."""
    text = compact_text(value).lower()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def has_text(value: str | None) -> bool:
    """Return whether value has non-empty text."""
    return bool(compact_text(value))


def compact_text(value: str | None) -> str:
    """Normalize optional text to stripped single-string form."""
    if value is None:
        return ""
    return str(value).strip()
