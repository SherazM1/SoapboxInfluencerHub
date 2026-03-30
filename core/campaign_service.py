from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from core.excel_writer import write_campaign_workbook
from core.mapper import MappingResult, map_campaign_sections
from core.parser import InfluencerRecord, parse_later_export
from core.validator import (
    TemplateConstraints,
    ValidationResult,
    validate_mapping_result,
    validate_parsed_records,
    validate_write_readiness,
)


@dataclass(slots=True)
class CampaignReviewResult:
    """Result payload for the review-upload flow."""

    records: list[InfluencerRecord]
    parse_summary: object | None
    parsed_validation: ValidationResult | None
    is_successful: bool
    errors: list[str]


@dataclass(slots=True)
class CampaignPreviewResult:
    """Result payload for mapped+validated preview flow."""

    selected_records: list[InfluencerRecord]
    recruiting_records: list[InfluencerRecord]
    mapping_result: MappingResult | None
    parsed_validation: ValidationResult | None
    mapping_validation: ValidationResult | None
    write_readiness_validation: ValidationResult | None
    combined_validation: ValidationResult | None
    unresolved_selected_identifiers: list[str]
    unresolved_recruiting_identifiers: list[str]
    is_valid: bool
    errors: list[str]


@dataclass(slots=True)
class CampaignPopulationResult:
    """Result payload for the final template-population flow."""

    selected_records: list[InfluencerRecord]
    recruiting_records: list[InfluencerRecord]
    mapping_result: MappingResult | None
    combined_validation: ValidationResult | None
    write_result: object | None
    output_path: str | None
    is_successful: bool
    blocked_reason: str | None
    errors: list[str]


def review_later_export(
    later_export_path: str | Path,
) -> CampaignReviewResult:
    """Parse and validate a Later export workbook for review."""
    try:
        parse_result = parse_later_export(later_export_path)
        records = parse_result.records
        parsed_validation = validate_parsed_records(records)
        return CampaignReviewResult(
            records=records,
            parse_summary=parse_result.summary,
            parsed_validation=parsed_validation,
            is_successful=True,
            errors=[],
        )
    except Exception as exc:
        return CampaignReviewResult(
            records=[],
            parse_summary=None,
            parsed_validation=None,
            is_successful=False,
            errors=[f"Failed to review Later export: {exc}"],
        )


def build_campaign_preview(
    parsed_records: list[InfluencerRecord],
    selected_identifiers: list[str],
    recruiting_identifiers: list[str] | None = None,
    template_constraints: TemplateConstraints | None = None,
) -> CampaignPreviewResult:
    """Resolve identifiers, map sections, and run preview validations."""
    try:
        parsed_validation = validate_parsed_records(parsed_records)

        selected_records, unresolved_selected_identifiers = resolve_records_by_identifiers(
            parsed_records,
            selected_identifiers,
        )

        unresolved_recruiting_identifiers: list[str] = []
        if recruiting_identifiers is None:
            recruiting_records = selected_records
        else:
            (
                recruiting_records,
                unresolved_recruiting_identifiers,
            ) = resolve_records_by_identifiers(parsed_records, recruiting_identifiers)

        effective_constraints = safe_default_template_constraints(template_constraints)

        mapping_result: MappingResult | None = None
        mapping_validation: ValidationResult | None = None
        write_readiness_validation: ValidationResult | None = None

        can_map = bool(selected_records) and not unresolved_selected_identifiers
        if can_map:
            mapping_result = map_campaign_sections(
                selected_records=selected_records,
                recruiting_records=recruiting_records,
            )
            mapping_validation = validate_mapping_result(mapping_result)
            write_readiness_validation = validate_write_readiness(
                mapping_result,
                effective_constraints,
            )

        combined_validation = build_combined_validation(
            parsed_validation=parsed_validation,
            mapping_validation=mapping_validation,
            write_readiness_validation=write_readiness_validation,
        )

        is_valid = (
            mapping_result is not None
            and not unresolved_selected_identifiers
            and not unresolved_recruiting_identifiers
            and combined_validation is not None
            and not combined_validation.has_errors
        )

        return CampaignPreviewResult(
            selected_records=selected_records,
            recruiting_records=recruiting_records,
            mapping_result=mapping_result,
            parsed_validation=parsed_validation,
            mapping_validation=mapping_validation,
            write_readiness_validation=write_readiness_validation,
            combined_validation=combined_validation,
            unresolved_selected_identifiers=unresolved_selected_identifiers,
            unresolved_recruiting_identifiers=unresolved_recruiting_identifiers,
            is_valid=is_valid,
            errors=[],
        )
    except Exception as exc:
        return CampaignPreviewResult(
            selected_records=[],
            recruiting_records=[],
            mapping_result=None,
            parsed_validation=None,
            mapping_validation=None,
            write_readiness_validation=None,
            combined_validation=None,
            unresolved_selected_identifiers=[],
            unresolved_recruiting_identifiers=[],
            is_valid=False,
            errors=[f"Failed to build campaign preview: {exc}"],
        )


def populate_campaign_template(
    template_path: str | Path,
    parsed_records: list[InfluencerRecord],
    selected_identifiers: list[str],
    output_path: str | Path,
    recruiting_identifiers: list[str] | None = None,
    template_constraints: TemplateConstraints | None = None,
) -> CampaignPopulationResult:
    """Build preview, enforce blocking rules, and write workbook when safe."""
    preview = build_campaign_preview(
        parsed_records=parsed_records,
        selected_identifiers=selected_identifiers,
        recruiting_identifiers=recruiting_identifiers,
        template_constraints=template_constraints,
    )

    blocking_errors: list[str] = []
    blocked_reason: str | None = None

    if preview.errors:
        blocking_errors.extend(preview.errors)
        blocked_reason = "Preview runtime failure"

    if preview.unresolved_selected_identifiers:
        blocking_errors.append(
            "Unresolved selected identifiers: "
            + ", ".join(preview.unresolved_selected_identifiers)
        )
        blocked_reason = blocked_reason or "Unresolved selected identifiers"

    if preview.unresolved_recruiting_identifiers:
        blocking_errors.append(
            "Unresolved recruiting identifiers: "
            + ", ".join(preview.unresolved_recruiting_identifiers)
        )
        blocked_reason = blocked_reason or "Unresolved recruiting identifiers"

    if preview.mapping_result is None:
        blocking_errors.append("Mapping result is unavailable.")
        blocked_reason = blocked_reason or "Mapping unavailable"

    if preview.combined_validation is not None and preview.combined_validation.has_errors:
        blocking_errors.append("Validation contains blocking errors.")
        blocked_reason = blocked_reason or "Validation errors"

    if not preview.is_valid:
        blocked_reason = blocked_reason or "Preview is not valid for population"

    if blocked_reason is not None:
        return build_blocked_population_result(
            preview=preview,
            blocked_reason=blocked_reason,
            errors=blocking_errors,
        )

    try:
        write_result = write_campaign_workbook(
            template_path=template_path,
            mapping_result=preview.mapping_result,
            output_path=output_path,
        )
        return CampaignPopulationResult(
            selected_records=preview.selected_records,
            recruiting_records=preview.recruiting_records,
            mapping_result=preview.mapping_result,
            combined_validation=preview.combined_validation,
            write_result=write_result,
            output_path=str(Path(output_path)),
            is_successful=True,
            blocked_reason=None,
            errors=[],
        )
    except Exception as exc:
        return CampaignPopulationResult(
            selected_records=preview.selected_records,
            recruiting_records=preview.recruiting_records,
            mapping_result=preview.mapping_result,
            combined_validation=preview.combined_validation,
            write_result=None,
            output_path=None,
            is_successful=False,
            blocked_reason="Workbook write runtime failure",
            errors=[f"Failed to populate campaign template: {exc}"],
        )


def normalize_identifier(value: str | None) -> str:
    """Normalize identifier text for deterministic exact matching."""
    if value is None:
        return ""
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    return normalized


def resolve_records_by_identifiers(
    records: list[InfluencerRecord],
    identifiers: list[str],
) -> tuple[list[InfluencerRecord], list[str]]:
    """Resolve identifiers to records with deterministic, non-fuzzy matching."""
    resolved_records: list[InfluencerRecord] = []
    unresolved_identifiers: list[str] = []

    for identifier in identifiers:
        normalized_identifier = normalize_identifier(identifier)
        if not normalized_identifier:
            unresolved_identifiers.append(identifier)
            continue

        canonical_matches = [
            record
            for record in records
            if normalize_identifier(record.canonical_name) == normalized_identifier
        ]
        if len(canonical_matches) == 1:
            resolved_records.append(canonical_matches[0])
            continue
        if len(canonical_matches) > 1:
            unresolved_identifiers.append(identifier)
            continue

        raw_name_matches = [
            record
            for record in records
            if normalize_identifier(record.raw_name) == normalized_identifier
        ]
        if len(raw_name_matches) == 1:
            resolved_records.append(raw_name_matches[0])
            continue

        unresolved_identifiers.append(identifier)

    return resolved_records, unresolved_identifiers


def build_combined_validation(
    parsed_validation: ValidationResult | None,
    mapping_validation: ValidationResult | None,
    write_readiness_validation: ValidationResult | None,
) -> ValidationResult | None:
    """Merge available validation results into one aggregate result."""
    present_results = [
        result
        for result in (
            parsed_validation,
            mapping_validation,
            write_readiness_validation,
        )
        if result is not None
    ]
    if not present_results:
        return None

    issues = [
        issue
        for result in present_results
        for issue in result.issues
    ]

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    info_count = sum(issue.severity == "info" for issue in issues)

    return ValidationResult(
        is_valid=error_count == 0,
        has_errors=error_count > 0,
        has_warnings=warning_count > 0,
        issues=issues,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def build_blocked_population_result(
    preview: CampaignPreviewResult,
    blocked_reason: str,
    errors: list[str],
) -> CampaignPopulationResult:
    """Build consistent blocked population result payloads."""
    return CampaignPopulationResult(
        selected_records=preview.selected_records,
        recruiting_records=preview.recruiting_records,
        mapping_result=preview.mapping_result,
        combined_validation=preview.combined_validation,
        write_result=None,
        output_path=None,
        is_successful=False,
        blocked_reason=blocked_reason,
        errors=errors,
    )


def safe_default_template_constraints(
    template_constraints: TemplateConstraints | None,
) -> TemplateConstraints:
    """Return explicit template constraints or phase-1 defaults."""
    if template_constraints is not None:
        return template_constraints
    return TemplateConstraints()
