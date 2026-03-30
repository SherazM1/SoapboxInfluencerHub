from __future__ import annotations

from dataclasses import dataclass
import re

from core.parser import InfluencerRecord


GENERIC_NOTE_VALUES = {
    "yes",
    "no",
    "y",
    "n",
    "ok",
    "okay",
    "agreed",
    "i agree",
    "sounds good",
    "looks good",
    "confirmed",
    "thank you",
    "thanks",
    "n/a",
    "na",
}


@dataclass(slots=True)
class WorkflowInfluencerDetailsRow:
    """Mapped row object for Workflow Influencer Details."""

    influencer_name: str
    handle_linked: str
    phone_number: str
    email: str
    contract_sent: str
    contract_signed: str
    payment_amount: str
    deliverable: str
    product: str
    invoiced: str
    w9: str
    notes: str


@dataclass(slots=True)
class WorkflowDraftStageRow:
    """Mapped row object for Workflow Draft Stages."""

    influencer_name: str
    draft_due_date: str
    draft_status: str
    final_approval: str
    notes: str


@dataclass(slots=True)
class WorkflowLiveContentRow:
    """Mapped row object for Workflow Live Content."""

    influencer_name: str
    deliverable: str
    live_date: str
    live_date_confirmed: str
    link_to_live_content: str
    notes: str


@dataclass(slots=True)
class WorkflowContentCheckRow:
    """Mapped row object for Workflow Content Checks."""

    influencer_name: str
    likes_unhidden: str
    link_in_caption: str
    link_in_bio: str
    hashtag_lindt_love: str
    hashtag_walmart: str
    mention_lindt_usa: str
    story_count: str
    notes: str


@dataclass(slots=True)
class Round1Row:
    """Mapped row object for Influencer Rounds Round 1."""

    influencer_name: str
    handle: str
    deliverable: str
    location: str
    product: str
    notes: str


@dataclass(slots=True)
class RecruitingRow:
    """Mapped row object for Influencer Rounds Recruiting."""

    influencer_name: str
    handle: str
    platform: str
    email: str
    ro: str
    fo: str
    notes: str


@dataclass(slots=True)
class MappingResult:
    """Top-level mapped row bundles and non-blocking mapping warnings."""

    workflow_influencer_details_rows: list[WorkflowInfluencerDetailsRow]
    workflow_draft_stage_rows: list[WorkflowDraftStageRow]
    workflow_live_content_rows: list[WorkflowLiveContentRow]
    workflow_content_check_rows: list[WorkflowContentCheckRow]
    round_1_rows: list[Round1Row]
    recruiting_rows: list[RecruitingRow]
    warnings: list[str]


def map_workflow_sections(
    selected_records: list[InfluencerRecord],
) -> tuple[
    list[WorkflowInfluencerDetailsRow],
    list[WorkflowDraftStageRow],
    list[WorkflowLiveContentRow],
    list[WorkflowContentCheckRow],
    list[str],
]:
    """Map selected records into workflow section rows in input order."""
    details_rows: list[WorkflowInfluencerDetailsRow] = []
    draft_rows: list[WorkflowDraftStageRow] = []
    live_rows: list[WorkflowLiveContentRow] = []
    check_rows: list[WorkflowContentCheckRow] = []
    warnings: list[str] = []

    for record in selected_records:
        details_row = map_workflow_influencer_details_row(record)
        draft_row = map_workflow_draft_stage_row(record)
        live_row = map_workflow_live_content_row(record)
        check_row = map_workflow_content_check_row(record)

        details_rows.append(details_row)
        draft_rows.append(draft_row)
        live_rows.append(live_row)
        check_rows.append(check_row)

        warnings.extend(build_workflow_row_warnings(record, details_row))

    return (
        details_rows,
        draft_rows,
        live_rows,
        check_rows,
        dedupe_preserve_order(warnings),
    )


def map_influencer_rounds(
    selected_records: list[InfluencerRecord],
    recruiting_records: list[InfluencerRecord] | None = None,
) -> tuple[list[Round1Row], list[RecruitingRow], list[str]]:
    """Map selected/recruiting records into round sections in input order."""
    round_1_rows: list[Round1Row] = []
    recruiting_rows: list[RecruitingRow] = []
    warnings: list[str] = []

    for record in selected_records:
        round_1_row = map_round_1_row(record)
        round_1_rows.append(round_1_row)
        warnings.extend(build_round_1_row_warnings(record, round_1_row))

    source_for_recruiting = (
        recruiting_records if recruiting_records is not None else selected_records
    )
    for record in source_for_recruiting:
        recruiting_row = map_recruiting_row(record)
        recruiting_rows.append(recruiting_row)
        warnings.extend(build_recruiting_row_warnings(record, recruiting_row))

    return round_1_rows, recruiting_rows, dedupe_preserve_order(warnings)


def map_campaign_sections(
    selected_records: list[InfluencerRecord],
    recruiting_records: list[InfluencerRecord] | None = None,
) -> MappingResult:
    """Map all phase-1 sections and return a single mapping result."""
    (
        workflow_influencer_details_rows,
        workflow_draft_stage_rows,
        workflow_live_content_rows,
        workflow_content_check_rows,
        workflow_warnings,
    ) = map_workflow_sections(selected_records)

    round_1_rows, recruiting_rows, rounds_warnings = map_influencer_rounds(
        selected_records=selected_records,
        recruiting_records=recruiting_records,
    )

    return MappingResult(
        workflow_influencer_details_rows=workflow_influencer_details_rows,
        workflow_draft_stage_rows=workflow_draft_stage_rows,
        workflow_live_content_rows=workflow_live_content_rows,
        workflow_content_check_rows=workflow_content_check_rows,
        round_1_rows=round_1_rows,
        recruiting_rows=recruiting_rows,
        warnings=dedupe_preserve_order(workflow_warnings + rounds_warnings),
    )


def map_workflow_influencer_details_row(
    record: InfluencerRecord,
) -> WorkflowInfluencerDetailsRow:
    """Map one record into a Workflow Influencer Details row."""
    return WorkflowInfluencerDetailsRow(
        influencer_name=record.canonical_name,
        handle_linked=format_handle_display(record),
        phone_number=format_phone_display(record),
        email=format_email_display(record),
        contract_sent="",
        contract_signed="",
        payment_amount="",
        deliverable="",
        product="",
        invoiced="",
        w9="",
        notes="",
    )


def map_workflow_draft_stage_row(record: InfluencerRecord) -> WorkflowDraftStageRow:
    """Map one record into a Workflow Draft Stages row."""
    return WorkflowDraftStageRow(
        influencer_name=record.canonical_name,
        draft_due_date="",
        draft_status="",
        final_approval="",
        notes="",
    )


def map_workflow_live_content_row(record: InfluencerRecord) -> WorkflowLiveContentRow:
    """Map one record into a Workflow Live Content row."""
    return WorkflowLiveContentRow(
        influencer_name=record.canonical_name,
        deliverable="",
        live_date="",
        live_date_confirmed="",
        link_to_live_content="",
        notes="",
    )


def map_workflow_content_check_row(
    record: InfluencerRecord,
) -> WorkflowContentCheckRow:
    """Map one record into a Workflow Content Checks row."""
    return WorkflowContentCheckRow(
        influencer_name=record.canonical_name,
        likes_unhidden="",
        link_in_caption="",
        link_in_bio="",
        hashtag_lindt_love="",
        hashtag_walmart="",
        mention_lindt_usa="",
        story_count="",
        notes="",
    )


def map_round_1_row(record: InfluencerRecord) -> Round1Row:
    """Map one record into an Influencer Rounds Round 1 row."""
    return Round1Row(
        influencer_name=record.canonical_name,
        handle=format_handle_display(record),
        deliverable="",
        location=format_location_display(record),
        product="",
        notes=select_notes_text(record),
    )


def map_recruiting_row(record: InfluencerRecord) -> RecruitingRow:
    """Map one record into an Influencer Rounds Recruiting row."""
    return RecruitingRow(
        influencer_name=record.canonical_name,
        handle=format_handle_display(record),
        platform=format_platform_display(record),
        email=format_email_display(record),
        ro="",
        fo="",
        notes=select_notes_text(record),
    )


def format_handle_display(record: InfluencerRecord) -> str:
    """Format display handle for workflow/round sections."""
    pairs = platform_handle_pairs(record)
    if not pairs:
        return ""

    if len(pairs) == 1:
        platform, handle = pairs[0]
        if platform == "IG":
            return f"@{handle}"
        return f"{platform}- @{handle}"

    return "\n".join(f"{platform}- @{handle}" for platform, handle in pairs)


def format_platform_display(record: InfluencerRecord) -> str:
    """Format compact platform display for recruiting rows."""
    labels = [platform for platform, _ in platform_handle_pairs(record)]
    return " + ".join(labels) if labels else ""


def format_location_display(record: InfluencerRecord) -> str:
    """Format location display for round 1 rows."""
    if compact_text(record.location_display):
        return compact_text(record.location_display)

    city = compact_text(record.city)
    state = compact_text(record.state)
    if city and state:
        return f"{city}, {state}"
    if city:
        return city
    if state:
        return state
    return ""


def format_phone_display(record: InfluencerRecord) -> str:
    """Format phone display for workflow influencer details rows."""
    if compact_text(record.phone_display):
        return compact_text(record.phone_display)
    if compact_text(record.phone_raw):
        return compact_text(record.phone_raw)
    return ""


def format_email_display(record: InfluencerRecord) -> str:
    """Format email display for workflow/recruiting rows."""
    return compact_text(record.email)


def select_notes_text(record: InfluencerRecord) -> str:
    """Select concise, useful notes text for round rows."""
    raw_candidates: list[str] = []
    raw_candidates.extend(record.notes_candidate_parts)
    if not raw_candidates:
        raw_candidates.extend(record.raw_custom_responses.values())

    candidates = filter_note_fragments(raw_candidates)
    if not candidates:
        return ""

    ranked = sorted(candidates, key=score_note_fragment, reverse=True)
    chosen: list[str] = []
    max_total_chars = 160

    for fragment in ranked:
        projected_length = sum(len(value) for value in chosen) + len(fragment)
        projected_length += 3 * len(chosen)
        if projected_length > max_total_chars:
            continue
        chosen.append(fragment)
        if len(chosen) >= 2:
            break

    return " | ".join(chosen) if chosen else ""


def platform_handle_pairs(record: InfluencerRecord) -> list[tuple[str, str]]:
    """Return platform and handle pairs in IG, TT, YT, FB order."""
    pairs: list[tuple[str, str]] = []

    instagram = clean_handle(record.instagram_handle)
    tiktok = clean_handle(record.tiktok_handle)
    youtube = clean_handle(record.youtube_handle)
    facebook = clean_handle(record.facebook_handle)

    if instagram:
        pairs.append(("IG", instagram))
    if tiktok:
        pairs.append(("TT", tiktok))
    if youtube:
        pairs.append(("YT", youtube))
    if facebook:
        pairs.append(("FB", facebook))

    return pairs


def build_workflow_row_warnings(
    record: InfluencerRecord,
    row: WorkflowInfluencerDetailsRow,
) -> list[str]:
    """Build workflow mapping warnings for a single record."""
    warnings: list[str] = []
    if not row.handle_linked:
        warnings.append(f'missing handle for influencer "{record.canonical_name}"')
    if not row.phone_number:
        warnings.append(
            f'missing phone for workflow details row "{record.canonical_name}"'
        )
    if not row.email:
        warnings.append(
            f'missing email for workflow details row "{record.canonical_name}"'
        )
    return warnings


def build_round_1_row_warnings(
    record: InfluencerRecord,
    row: Round1Row,
) -> list[str]:
    """Build round 1 mapping warnings for a single record."""
    warnings: list[str] = []
    if not row.handle:
        warnings.append(f'missing handle for influencer "{record.canonical_name}"')
    if not row.location:
        warnings.append(f'missing location for round 1 row "{record.canonical_name}"')
    if not row.notes:
        warnings.append(
            f'notes omitted for influencer "{record.canonical_name}" '
            "because no useful concise text was found"
        )
    return warnings


def build_recruiting_row_warnings(
    record: InfluencerRecord,
    row: RecruitingRow,
) -> list[str]:
    """Build recruiting mapping warnings for a single record."""
    warnings: list[str] = []
    if not row.handle:
        warnings.append(f'missing handle for influencer "{record.canonical_name}"')
    if not row.platform:
        warnings.append(
            f'missing platform for recruiting row "{record.canonical_name}"'
        )
    if not row.email:
        warnings.append(f'missing email for recruiting row "{record.canonical_name}"')
    if not row.notes:
        warnings.append(
            f'notes omitted for influencer "{record.canonical_name}" '
            "because no useful concise text was found"
        )
    return warnings


def filter_note_fragments(values: list[str]) -> list[str]:
    """Filter raw note text into concise and useful fragments."""
    fragments: list[str] = []
    seen: set[str] = set()

    for value in values:
        for piece in split_note_fragments(value):
            cleaned = compact_text(piece)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            if is_unhelpful_fragment(cleaned):
                continue
            seen.add(lowered)
            fragments.append(cleaned)

    return fragments


def split_note_fragments(value: str) -> list[str]:
    """Split note text into short candidate fragments."""
    return [piece.strip() for piece in re.split(r"[\r\n;|]+", value) if piece.strip()]


def is_unhelpful_fragment(fragment: str) -> bool:
    """Return True if a note fragment is generic or too long."""
    lowered = fragment.lower()
    if lowered in GENERIC_NOTE_VALUES:
        return True
    if re.fullmatch(r"(yes|no|y|n)", lowered):
        return True
    if len(fragment) > 140:
        return True
    if len(fragment.split()) > 24:
        return True
    if not any(char.isalnum() for char in fragment):
        return True
    return False


def score_note_fragment(fragment: str) -> int:
    """Score note candidates using conservative operational relevance hints."""
    lowered = fragment.lower()
    score = 0

    if re.search(r"\b(store|store#|store number|location #|suite|unit)\b", lowered):
        score += 6
    if re.search(
        r"\b(street|st\.|ave|avenue|blvd|road|rd\.|drive|dr\.|address|zip)\b",
        lowered,
    ):
        score += 5
    if re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        lowered,
    ):
        score += 5
    if re.search(
        r"\b(am|pm|morning|afternoon|evening|delivery|drop off|pickup|window|eta|by)\b",
        lowered,
    ):
        score += 4
    if re.search(
        r"\b(concept|hook|angle|caption|creative|content|shoot|filming|script)\b",
        lowered,
    ):
        score += 3
    if re.search(r"\d", fragment):
        score += 2
    if 8 <= len(fragment) <= 90:
        score += 2

    return score


def clean_handle(value: str | None) -> str:
    """Normalize handle text without leading @."""
    cleaned = compact_text(value)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.lstrip("@")


def compact_text(value: str | None) -> str:
    """Normalize optional text for mapping output fields."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Dedupe list values while preserving first appearance order."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
