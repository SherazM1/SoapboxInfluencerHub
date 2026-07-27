insert into campaign_ops_users (id, display_name, email, role, is_active)
values
    ('11111111-1111-4111-8111-111111111111', 'Bailey', null, 'administrator', true),
    ('22222222-2222-4222-8222-222222222222', 'T', null, 'team_member', true),
    ('33333333-3333-4333-8333-333333333333', 'L', null, 'team_member', true)
on conflict (id) do update set
    display_name = excluded.display_name,
    email = excluded.email,
    role = excluded.role,
    is_active = excluded.is_active;
