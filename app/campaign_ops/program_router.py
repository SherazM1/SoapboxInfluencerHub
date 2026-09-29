"""Single entry point for Program navigation from registry, My Programs and creation."""
from app.campaign_ops.state import clear_selected_program, set_section
from app.campaign_ops.ui.navigation import clear_all_specialized_state, route_to_specialized_workspace
from core.campaign_ops.influencer_timeline import STAGE_LABELS
from core.campaign_ops.program_routing import ProgramRoutingService


def open_program(session_state, actor, service, program_id):
    destination = ProgramRoutingService(service.repository).resolve(actor, program_id)
    clear_selected_program(session_state)
    clear_all_specialized_state(session_state)
    # Discard only editor snapshots when explicitly navigating to a program; saves are unchanged.
    for key in list(session_state):
        if key.startswith("campaign_ops_influencer_draft_"):
            session_state.pop(key, None)
    session_state.pop("campaign_ops_influencer_timeline_navigation", None)
    if destination.section in ("All Programs", "Social Media Management"):
        set_section(session_state, destination.section)
    else:
        route_to_specialized_workspace(session_state, destination.section, program_id, destination.record_id)
    if destination.stage:
        session_state["campaign_ops_influencer_timeline_navigation"] = STAGE_LABELS[destination.stage]
    if destination.message:
        session_state["campaign_ops_program_route_message"] = destination.message
    return destination
