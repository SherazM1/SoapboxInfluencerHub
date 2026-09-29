from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts.dev import cleanup_campaign_ops_test_data as cleanup


class MemoryCleanupRepository:
    def __init__(self):
        self.programs = [
            {'id': 'test', 'program_name': 'TEST - Fixture', 'client': 'TEST - Client', 'primary_workstream_type': 'influencer', 'is_active': True},
            {'id': 'real', 'program_name': 'Client Fall Campaign', 'client': 'TEST - Shared Client', 'primary_workstream_type': 'retail_media', 'is_active': True},
        ]
        self.children = [
            {'id': 'fixture', 'program_id': 'test', 'name': 'Legacy name under fixture', 'kind': 'influencer', 'is_active': True},
            {'id': 'real-child', 'program_id': 'real', 'name': 'Real retail campaign', 'kind': 'retail_media', 'is_active': True},
            {'id': 'test-project', 'program_id': 'real', 'name': 'TEST_Project', 'kind': 'insights', 'is_active': True},
        ]
        self.clients = [{'id': 'client', 'name': 'TEST - Shared Client', 'is_active': True}]
        self.calls = []
        self.actor = SimpleNamespace(id='admin', role='administrator', is_active=True)

    def inventory(self):
        return cleanup.build_inventory(deepcopy(self.programs), deepcopy(self.children), deepcopy(self.clients))

    def list_active_users(self): return [self.actor]

    def append_event(self, **kwargs): self.calls.append(('event', kwargs))

    def archive_program(self, program_id, actor_user_id=None):
        self.calls.append(('archive', program_id))
        next(p for p in self.programs if p['id'] == program_id)['is_active'] = False

    def __getattr__(self, name):
        if name in {spec[2] for spec in cleanup.SPECIALIZED.values()}:
            def deactivate(record_id):
                self.calls.append(('deactivate', record_id))
                next(c for c in self.children if c['id'] == record_id)['is_active'] = False
            return deactivate
        raise AttributeError(name)


class TestDataCleanupTests(unittest.TestCase):
    def test_explicit_prefix_matching_only(self):
        for name in ('TEST - Retail Media Program 1', 'TEST_Fixture', 'VALIDATION', 'VALIDATION Program', 'RECAP VALIDATION PROGRAM', '  test - Prompt 4A'):
            self.assertTrue(cleanup.is_test_name(name), name)
        for name in ('Contest Launch', 'Client test campaign', 'A validation study', 'Testimonials', 'Testing Products', 'Test', 'Client Fall Campaign', ''):
            self.assertFalse(cleanup.is_test_name(name), name)

    def test_guard_blocks_apply_before_connection(self):
        with patch.object(cleanup, 'connect_to_campaign_ops_database') as connect, redirect_stdout(StringIO()):
            self.assertEqual(2, cleanup.main(['--apply'], env={}))
        connect.assert_not_called()

    def test_apply_requires_exact_explicit_dev_target_and_inventory(self):
        with patch.object(cleanup, 'get_campaign_ops_database_url', return_value='postgresql://localhost/dev'), patch.object(cleanup, 'connect_to_campaign_ops_database') as connect, redirect_stdout(StringIO()):
            self.assertEqual(2, cleanup.main(['--apply'], env={cleanup.ALLOW_ENV: '1'}))
        connect.assert_not_called()

    def test_inventory_preserves_normal_parent_siblings_clients_and_history(self):
        repo = MemoryCleanupRepository()
        before = deepcopy((repo.programs, repo.children, repo.clients))
        inventory = repo.inventory()
        self.assertEqual(before, (repo.programs, repo.children, repo.clients))
        self.assertEqual({'fixture', 'test-project'}, {c['id'] for c in inventory['specialized_candidates']})
        self.assertFalse(next(p for p in inventory['programs'] if p['id'] == 'real')['archive_program'])
        result = cleanup.apply_inventory(repo, inventory, repo.actor)
        self.assertEqual([{'id': 'test', 'name': 'TEST - Fixture'}], result['programs_cleaned'])
        self.assertEqual(2, len(result['child_records_affected']))
        self.assertTrue(repo.programs[1]['is_active'])
        self.assertTrue(repo.children[1]['is_active'])
        self.assertEqual(before[2], repo.clients)
        self.assertEqual(3, len(repo.children))
        calls = deepcopy(repo.calls)
        self.assertEqual({'programs_cleaned': [], 'child_records_affected': []}, cleanup.apply_inventory(repo, repo.inventory(), repo.actor))
        self.assertEqual(calls, repo.calls)

    def test_archived_test_parent_can_cleanup_remaining_active_children(self):
        repo = MemoryCleanupRepository()
        repo.programs[0]['is_active'] = False
        result = cleanup.apply_inventory(repo, repo.inventory(), repo.actor)
        self.assertEqual([], result['programs_cleaned'])
        self.assertFalse(repo.children[0]['is_active'])
        self.assertFalse(repo.programs[0]['is_active'])
        self.assertFalse(any(call[0] == 'archive' for call in repo.calls))

    def test_review_matching_allows_noop_repeat_but_rejects_renamed_or_reactivated_rows(self):
        repo = MemoryCleanupRepository()
        reviewed = repo.inventory()
        cleanup.apply_inventory(repo, reviewed, repo.actor)
        current = repo.inventory()
        self.assertTrue(cleanup.inventory_matches(reviewed, current))
        self.assertFalse(cleanup.inventory_matches(current, reviewed))
        altered = deepcopy(reviewed)
        altered['programs'][0]['program_name'] = 'Real campaign'
        self.assertFalse(cleanup.inventory_matches(altered, reviewed))

    def test_main_default_is_read_only_and_guarded_apply_is_idempotent(self):
        repo = MemoryCleanupRepository()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        with TemporaryDirectory() as directory, patch.object(cleanup, 'get_campaign_ops_database_url', return_value='postgresql://localhost/dev'), patch.object(cleanup, 'connect_to_campaign_ops_database', return_value=connection), patch.object(cleanup, 'CampaignOpsRepository', return_value=repo), patch.object(cleanup, 'read_inventory', side_effect=lambda r: r.inventory()), redirect_stdout(StringIO()):
            path = Path(directory) / 'inventory.json'
            self.assertEqual(0, cleanup.main(['--report', str(path)], env={}))
            self.assertEqual([], repo.calls)
            connection.cursor.return_value.__enter__.return_value.execute.assert_called_with('SET TRANSACTION READ ONLY')
            self.assertFalse(json.loads(path.read_text())['applied'])
            args = ['--apply', '--inventory', str(path), '--confirm-dev-target', 'localhost:5432/dev']
            self.assertEqual(0, cleanup.main(args, env={cleanup.ALLOW_ENV: '1'}))
            calls = deepcopy(repo.calls)
            self.assertEqual(0, cleanup.main(args, env={cleanup.ALLOW_ENV: '1'}))
            self.assertEqual(calls, repo.calls)
            connection.cursor.return_value.__enter__.return_value.execute.assert_called_with('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')

    def test_non_admin_apply_is_rejected(self):
        repo = MemoryCleanupRepository()
        with self.assertRaises(ValueError): cleanup.apply_inventory(repo, repo.inventory(), SimpleNamespace(role='team_member'))
        self.assertEqual([], repo.calls)

    def test_console_inventory_contains_only_program_metadata_and_counts(self):
        output = StringIO()
        with redirect_stdout(output):
            cleanup.print_inventory(MemoryCleanupRepository().inventory())
        for line in output.getvalue().splitlines():
            row = json.loads(line)
            self.assertEqual({'program_id', 'program_name', 'workflow', 'related_record_counts',
                              'active_related_record_count'}, set(row))
        self.assertNotIn('Shared Client', output.getvalue())

    def test_changed_inventory_refuses_apply_before_any_writes(self):
        repo = MemoryCleanupRepository()
        reviewed = {'target': 'localhost:5432/dev', 'inventory': repo.inventory()}
        repo.children[0]['name'] = 'Changed after review'
        connection = MagicMock()
        connection.__enter__.return_value = connection
        with TemporaryDirectory() as directory, patch.object(cleanup, 'get_campaign_ops_database_url', return_value='postgresql://localhost/dev'), patch.object(cleanup, 'connect_to_campaign_ops_database', return_value=connection), patch.object(cleanup, 'CampaignOpsRepository', return_value=repo), patch.object(cleanup, 'read_inventory', side_effect=lambda r: r.inventory()), redirect_stdout(StringIO()):
            path = Path(directory) / 'inventory.json'
            path.write_text(json.dumps(reviewed))
            self.assertEqual(1, cleanup.main(['--apply', '--inventory', str(path), '--confirm-dev-target', 'localhost:5432/dev'], env={cleanup.ALLOW_ENV: '1'}))
        self.assertEqual([], repo.calls)
