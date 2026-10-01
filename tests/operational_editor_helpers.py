from datetime import date


def button(app, label):
    return next(w for w in app.button if w.label == label)


def field(app, label):
    return next(w for kind in (app.selectbox, app.text_input, app.date_input, app.checkbox)
                for w in kind if w.label == label)


def edit(app, index, **values):
    for name, value in values.items():
        label = f"{'Custom action' if name == 'Custom Action' else name}, row {index + 1}"
        widget = field(app, label)
        if name == 'Date' and isinstance(value, str):
            value = date.fromisoformat(value) if value else None
        widget.set_value(value).run()
        assert not app.exception


def apply_edits(app, delta):
    for index, values in delta.get('edited_rows', {}).items():
        edit(app, int(index), **values)
    for index in sorted(delta.get('deleted_rows', []), reverse=True):
        [w for w in app.button if w.label == '×'][index].click().run()
    for values in delta.get('added_rows', []):
        button(app, 'Add row').click().run()
        edit(app, len(app.date_input) - 1, **values)


def draft_records(app):
    return next(value['editor_records'] for key, value in app.session_state.filtered_state.items()
                if key.startswith(('campaign_ops_influencer_draft_', 'campaign_ops_smm_draft_'))
                and isinstance(value, dict) and 'editor_records' in value)
