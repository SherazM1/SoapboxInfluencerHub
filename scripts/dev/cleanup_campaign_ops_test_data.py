"""Guarded, one-time soft cleanup. Default mode is a read-only inventory."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.campaign_ops.db import connect_to_campaign_ops_database, get_campaign_ops_database_url
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.repository import CampaignOpsRepository

ALLOW_ENV = "ALLOW_CAMPAIGN_OPS_TEST_DATA_CLEANUP"
TEST_PREFIX = re.compile(r"^(?:TEST\s*-\s+|TEST_|VALIDATION(?:[\s_-]|$)|RECAP VALIDATION(?:[\s_-]|$))", re.IGNORECASE)
# SQL identifiers are fixed constants, never supplied by the operator.
SPECIALIZED = {
    "influencer": ("campaign_ops_influencer_campaigns", "campaign_title", "deactivate_influencer_campaign"),
    "retail_media": ("campaign_ops_retail_media_campaigns", "campaign_title", "deactivate_retail_media_campaign"),
    "content": ("campaign_ops_content_programs", "content_program_title", "deactivate_content_program"),
    "insights": ("campaign_ops_insights_projects", "project_title", "deactivate_insights_project"),
    "request": ("campaign_ops_reporting_requests", "request_type", "deactivate_reporting_request"),
}


def is_test_name(name):
    return bool(TEST_PREFIX.match((name or "").strip()))


def target_identity(url):
    parsed = urlsplit(url or "")
    return f"{parsed.hostname or ''}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"


def read_inventory(repository):
    programs = repository._fetch_raw_all(
        "select p.id, p.program_name, p.primary_workstream_type, p.is_active, c.name as client "
        "from campaign_ops_programs p left join campaign_ops_clients c on c.id = p.client_id order by p.id", ())
    children = []
    for kind, (table, title, _) in SPECIALIZED.items():
        for row in repository._fetch_raw_all(f"select id, program_id, {title} as name, is_active from {table} order by id", ()):
            children.append({**row, "kind": kind})
    clients = repository._fetch_raw_all("select id, name, is_active from campaign_ops_clients order by id", ())
    return build_inventory(programs, children, clients)


def build_inventory(programs, children, clients=()):
    # Client-only matches are reported but never cascade into normal-looking programs.
    program_map = {str(p["id"]): {**p, "id": str(p["id"])} for p in programs}
    matched = {key for key, program in program_map.items() if is_test_name(program["program_name"])}
    selected, skipped_children = [], 0
    related = {key: [] for key in program_map}
    for child in children:
        child = {**child, "id": str(child["id"]), "program_id": str(child["program_id"])}
        related.setdefault(child["program_id"], []).append(child)
        # A request type is not a project name: select requests only by a test parent.
        own_match = child["kind"] != "request" and is_test_name(child["name"])
        if child["program_id"] in matched or own_match:
            selected.append({**child, "reason": "test program" if child["program_id"] in matched else "explicit project prefix"})
        else:
            skipped_children += 1
    relevant_programs = matched | {row["program_id"] for row in selected}
    inventory = []
    for program_id in sorted(relevant_programs):
        program = program_map.get(program_id)
        if program is None:
            raise ValueError("Specialized record has no program; cleanup refused.")
        inventory.append({**program, "archive_program": program_id in matched,
            "related_specialized_records": sorted(related.get(program_id, []), key=lambda r: (r["kind"], r["id"]))})
    return {
        "programs": inventory,
        "specialized_candidates": sorted(selected, key=lambda r: (r["kind"], r["id"])),
        "skipped_programs": len(program_map) - len(matched),
        "skipped_specialized_records": skipped_children,
        "client_matches_preserved": [{"id": str(c["id"]), "name": c["name"], "is_active": c["is_active"]} for c in clients if is_test_name(c["name"])],
    }


def inventory_matches(reviewed, current):
    """Allow only already-cleaned active flags to differ on a repeat apply."""
    if isinstance(reviewed, dict) and isinstance(current, dict):
        if reviewed.keys() != current.keys():
            return False
        return all((key == "is_active" and reviewed[key] is True and current[key] is False)
                   or inventory_matches(reviewed[key], current[key]) for key in reviewed)
    if isinstance(reviewed, list) and isinstance(current, list):
        return len(reviewed) == len(current) and all(inventory_matches(a, b) for a, b in zip(reviewed, current))
    return reviewed == current


def print_inventory(inventory):
    """Console output deliberately contains only reviewable program metadata."""
    for program in inventory["programs"]:
        children = program["related_specialized_records"]
        print(json.dumps({"program_id": program["id"], "program_name": program["program_name"],
            "workflow": program["primary_workstream_type"],
            "related_record_counts": {kind: sum(child["kind"] == kind for child in children)
                                      for kind in SPECIALIZED},
            "active_related_record_count": sum(bool(child["is_active"]) for child in children)},
            default=str), flush=True)


def apply_inventory(repository, inventory, actor):
    if not can_access_admin(actor):
        raise ValueError("An active Campaign Ops administrator is required.")
    affected = {"programs_cleaned": [], "child_records_affected": []}
    # Existing repository soft-deactivation methods work even if a test parent was
    # previously archived; no temporary reactivation or hard deletion is necessary.
    for child in inventory["specialized_candidates"]:
        if not child["is_active"]:
            continue
        method = SPECIALIZED[child["kind"]][2]
        getattr(repository, method)(child["id"])
        repository.append_event(event_type="test_data_soft_cleanup", entity_type=child["kind"],
            entity_id=child["id"], program_id=child["program_id"], actor_user_id=actor.id,
            message=f"Guarded test-data cleanup deactivated {child['name']}.")
        affected["child_records_affected"].append({"kind": child["kind"], "id": child["id"], "name": child["name"]})
    for program in inventory["programs"]:
        if not program["archive_program"] or not program["is_active"]:
            continue
        repository.archive_program(program["id"], actor_user_id=actor.id)
        repository.append_event(event_type="program_archived", entity_type="program",
            entity_id=program["id"], program_id=program["id"], actor_user_id=actor.id,
            message=f"Guarded test-data cleanup archived {program['program_name']}.")
        affected["programs_cleaned"].append({"id": program["id"], "name": program["program_name"]})
    return affected


def main(argv=None, env=None):
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--inventory", type=Path, help="Previously reviewed dry-run JSON, required for apply")
    parser.add_argument("--confirm-dev-target", help="Explicit intended local/dev host:port/database, required for apply")
    args = parser.parse_args(argv)
    if args.apply and env.get(ALLOW_ENV) != "1":
        print(f"{ALLOW_ENV}=1 is required. No database changes were made.")
        return 2
    url = get_campaign_ops_database_url()
    target = target_identity(url)
    if args.apply and (args.confirm_dev_target != target or args.inventory is None):
        print("Apply requires the reviewed inventory and exact intended local/dev target. No changes made.")
        return 2
    report = {"mode": "apply" if args.apply else "dry-run", "target": target,
              "programs_cleaned": [], "child_records_affected": []}
    try:
        reviewed = json.loads(args.inventory.read_text(encoding="utf-8")) if args.apply else None
        with connect_to_campaign_ops_database() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if args.apply else "SET TRANSACTION READ ONLY")
                repository = CampaignOpsRepository(connection)
                inventory = read_inventory(repository)
                report["inventory"] = inventory
                print_inventory(inventory)
                if args.apply:
                    if reviewed.get("target") != target or not inventory_matches(reviewed.get("inventory"), inventory):
                        raise ValueError("Candidates or target changed since dry-run. Produce and review a fresh inventory.")
                    actor = next((user for user in repository.list_active_users() if can_access_admin(user)), None)
                    result = apply_inventory(repository, inventory, actor)
            # Only report writes as applied after the transaction has committed.
        if args.apply:
            report.update(result)
            report["applied"] = True
        else:
            report["applied"] = False
    except (CampaignOpsError, ValueError, OSError) as exc:
        report["error"] = str(exc)
        report["applied"] = False
        print("Cleanup did not complete. Review the safe error in the report.")
        if args.report:
            args.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        return 1
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
