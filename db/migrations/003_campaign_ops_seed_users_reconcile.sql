with seed_users (id, display_name, email, role) as (
    values
        ('11111111-1111-4111-8111-111111111111'::uuid, 'Bailey', null::text, 'administrator'),
        ('22222222-2222-4222-8222-222222222222'::uuid, 'T', null::text, 'team_member'),
        ('33333333-3333-4333-8333-333333333333'::uuid, 'L', null::text, 'team_member')
),
updated_users as (
    update campaign_ops_users existing
    set
        display_name = seed_users.display_name,
        email = seed_users.email,
        role = seed_users.role,
        is_active = true
    from seed_users
    where existing.id = seed_users.id
       or lower(existing.display_name) = lower(seed_users.display_name)
    returning seed_users.display_name
)
insert into campaign_ops_users (id, display_name, email, role, is_active)
select id, display_name, email, role, true
from seed_users
where not exists (
    select 1
    from updated_users
    where updated_users.display_name = seed_users.display_name
);
