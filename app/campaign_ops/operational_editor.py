"""Small native row controls shared by operational timeline fragments."""
from uuid import uuid4

import streamlit as st

COLUMNS = ("Date", "Action", "Done", "Program Notes")
WIDTHS = [15, 40, 7, 32, 6]


def editor_styles():
    from app.campaign_ops.ui.styles import apply_editor_styles
    apply_editor_styles()


def row_key(prefix, record, field):
    return f"{prefix}_{record['_draft_id']}_{field}"


def collect_rows(snapshot, prefix):
    """Read current widget state, including pending values delivered with Save."""
    for row in snapshot["editor_records"]:
        for field in (*COLUMNS, "Custom Action"):
            key = row_key(prefix, row, field)
            if key in st.session_state:
                row[field] = st.session_state[key]
        if row.get("Action") != "Custom":
            row["Custom Action"] = ""
    return snapshot["editor_records"]


def _add(snapshot, prefix):
    collect_rows(snapshot, prefix)
    snapshot["editor_records"].append({"_row_id": None, "_draft_id": str(uuid4()),
        "Date": None, "Action": "", "Custom Action": "", "Done": False, "Program Notes": ""})


def _remove(snapshot, prefix, token):
    collect_rows(snapshot, prefix)
    snapshot["editor_records"] = [r for r in snapshot["editor_records"] if r["_draft_id"] != token]


def render_rows(snapshot, prefix, *, actions=None):
    with st.container(key="ops_table"):
        _render_table(snapshot, prefix, actions=actions)


def _render_table(snapshot, prefix, *, actions):
    columns = st.columns(WIDTHS, gap="small")
    for column, label in zip(columns, (*COLUMNS, "Remove")):
        column.markdown(f"**{label}**")
    for index, row in enumerate(snapshot["editor_records"], 1):
        with st.container(key=f"ops_row_{row['_draft_id']}"):
            columns = st.columns(WIDTHS, gap="small")
            with columns[0]:
                row["Date"] = st.date_input(f"Date, row {index}", value=row.get("Date"),
                    format="MM/DD/YYYY", key=row_key(prefix, row, "Date"), label_visibility="collapsed")
            with columns[1]:
                if actions is None:
                    row["Action"] = st.text_input(f"Action, row {index}", value=row.get("Action") or "",
                        key=row_key(prefix, row, "Action"), label_visibility="collapsed")
                else:
                    options = ["", *actions]
                    row["Action"] = st.selectbox(f"Action, row {index}", options,
                        index=options.index(row.get("Action") or ""),
                        format_func=lambda value: value or "Choose an action",
                        key=row_key(prefix, row, "Action"), label_visibility="collapsed")
                    if row["Action"] == "Custom":
                        row["Custom Action"] = st.text_input(f"Custom action, row {index}",
                            value=row.get("Custom Action") or "", placeholder="Enter custom action",
                            key=row_key(prefix, row, "Custom Action"), label_visibility="collapsed")
                    else:
                        row["Custom Action"] = ""
                        st.session_state.pop(row_key(prefix, row, "Custom Action"), None)
            with columns[2]:
                row["Done"] = st.checkbox(f"Done, row {index}", value=bool(row.get("Done")),
                    key=row_key(prefix, row, "Done"), label_visibility="collapsed")
            with columns[3]:
                row["Program Notes"] = st.text_input(f"Program Notes, row {index}", value=row.get("Program Notes") or "",
                    key=row_key(prefix, row, "Program Notes"), label_visibility="collapsed")
            columns[4].button("×", key=row_key(prefix, row, "remove"), help=f"Remove row {index}",
                on_click=_remove, args=(snapshot, prefix, row["_draft_id"]))


def render_add_row(snapshot, prefix):
    st.button("Add row", key=f"{prefix}_add", on_click=_add, args=(snapshot, prefix))
