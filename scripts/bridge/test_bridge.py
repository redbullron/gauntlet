import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import bridge
import core
from processes import run


def verdict(status='approve'):
    return {'verdict': status, 'summary': 'Checked the source.', 'findings': [] if status == 'approve' else [
        {'severity': 'P1', 'file': 'app.txt', 'evidence': 'Expected new, found old', 'requested_change': 'Use new'}]}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gauntlet-bridge-test-')
        self.root = Path(self.temp.name)
        self.old = core.STATE
        core.STATE = self.root / 'state'
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'app.txt').write_text('old\n')
        core.register_project('demo', str(self.source), checks=[{'name': 'unit', 'command': [sys.executable, '-c', 'pass']}])

    def tearDown(self):
        core.STATE = self.old
        self.temp.cleanup()

    def job(self, **kwargs):
        with patch('core.subprocess.Popen'):
            result = core.start('demo', 'Change old to new.', **kwargs)
        return result['id']

    def passes(self, j, label):
        return [{'name': 'unit', 'passed': True, 'exit_code': 0, 'output': ''}]

    def test_status_preserves_live_worker_after_stale_timestamp(self):
        job_id = self.job()
        j = core.get(job_id)
        j['state'] = 'running'
        core.save(j)
        held = core.worker_lock(job_id)
        self.assertIsNotNone(held)
        try:
            with patch('core.time.time', return_value=j['updated'] + 60):
                status = bridge.call('gauntlet_status', {'job_id': job_id})
            self.assertEqual(status['state'], 'running')
        finally:
            held.close()

    def test_fix_then_independent_dual_approval(self):
        job_id = self.job()
        calls = []
        def agent(j, name, prompt, review, label):
            calls.append((name, review))
            if not review:
                (Path(j['workspace']) / 'app.txt').write_text('new\n')
                return 'Fixed'
            return verdict('changes_requested' if j['round'] == 1 else 'approve')
        core.worker(job_id, agent, self.passes)
        j = core.get(job_id)
        self.assertEqual(j['state'], 'approved')
        self.assertEqual(calls, [('codex', True), ('claude', True), ('codex', False), ('codex', True), ('claude', True)])
        self.assertEqual((self.source / 'app.txt').read_text(), 'old\n')
        self.assertIn('+new', Path(j['patch']).read_text())
        self.assertNotEqual(j['history'][0]['revision'], j['history'][1]['revision'])

    def test_export_excludes_generated_and_secret_files(self):
        job_id = self.job()
        def checks(j, label):
            work = Path(j['workspace'])
            (work / '__pycache__').mkdir(exist_ok=True)
            (work / '__pycache__' / 'test.pyc').write_bytes(b'generated')
            (work / '.env').write_text('TEST_SECRET=not-real')
            return self.passes(j, label)
        core.worker(job_id, lambda *args: verdict(), checks)
        self.assertEqual(Path(core.get(job_id)['patch']).read_bytes(), b'')

    def test_checks_block_false_consensus(self):
        job_id = self.job(max_rounds=1)
        core.worker(job_id, lambda *args: verdict(), lambda *args: [{'name': 'test', 'passed': False}])
        self.assertEqual(core.get(job_id)['state'], 'limit_reached')

    def test_code_requires_validation(self):
        core.register_project('demo', str(self.source), checks=[])
        job_id = self.job()
        core.worker(job_id, lambda *args: verdict(), lambda *args: [])
        self.assertEqual(core.get(job_id)['state'], 'needs_validation')

    def test_profile_update_preserves_unspecified_checks(self):
        core.register_project('demo', str(self.source), context='New handoff')
        profile = core.projects()[0]
        self.assertEqual(len(profile['checks']), 1)
        self.assertEqual(profile['context'], 'New handoff')

    def test_post_approval_edit_stops_export(self):
        job_id = self.job()
        original = core.export
        def altered(j):
            (Path(j['workspace']) / 'app.txt').write_text('unreviewed edit\n')
            return original(j)
        with patch('core.export', altered):
            core.worker(job_id, lambda *args: verdict(), self.passes)
        self.assertEqual(core.get(job_id)['state'], 'failed')
        self.assertIn('changed after approval', core.get(job_id)['export_error'])

    def test_document_can_finish_without_code_tests(self):
        core.register_project('demo', str(self.source), kind='document')
        job_id = self.job()
        core.worker(job_id, lambda *args: verdict(), lambda *args: [])
        self.assertEqual(core.get(job_id)['state'], 'approved')

    def test_edits_during_review_invalidate_approval(self):
        job_id = self.job()
        def agent(j, *args):
            (Path(j['workspace']) / 'app.txt').write_text('unexpected\n')
            return verdict()
        core.worker(job_id, agent, self.passes)
        self.assertEqual(core.get(job_id)['state'], 'failed')
        self.assertIn('changed during review', core.get(job_id)['message'])

    def test_two_no_change_rounds_stall(self):
        job_id = self.job()
        core.worker(job_id, lambda j, a, p, review, label: verdict('changes_requested') if review else 'Disagree', self.passes)
        self.assertEqual(core.get(job_id)['state'], 'stalled')

    def test_one_job_global_even_across_projects(self):
        self.job()
        core.register_project('other', str(self.source))
        with self.assertRaisesRegex(ValueError, 'Another Gauntlet'):
            core.start('other', 'Review')

    def test_cancellation_before_start(self):
        job_id = self.job()
        core.cancel(job_id)
        core.worker(job_id, lambda *args: self.fail('Agent should not start'), self.passes)
        self.assertEqual(core.get(job_id)['state'], 'cancelled')

    def test_process_cancel(self):
        begin = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
            run([sys.executable, '-c', 'import time; time.sleep(60)'], self.source, self.root / 'cancel.log',
                cancelled=lambda: time.monotonic() - begin > .6)
        self.assertLess(time.monotonic() - begin, 10)

    def test_crash_recovery(self):
        job_id = self.job()
        j = core.get(job_id)
        j['updated'] = time.time() - 90
        with core.db() as c:
            c.execute('UPDATE jobs SET data=?,updated=? WHERE id=?', (json.dumps(j), j['updated'], job_id))
        core.recover()
        self.assertEqual(core.get(job_id)['state'], 'interrupted')

    def test_paths_and_secret_exclusion(self):
        (self.source / '.env').write_text('SECRET=example')
        (self.source / 'node_modules').mkdir()
        (self.source / 'node_modules' / 'x').write_text('excluded')
        self.assertEqual(core.source_files(self.source), ['app.txt'])
        with self.assertRaises(ValueError):
            core.inside(self.source, '../outside')
        with self.assertRaises(ValueError):
            core.register_project('escape', str(self.source), [{'name': 'x', 'command': ['python'], 'cwd': '..'}])
        with self.assertRaises(ValueError):
            core.job_path('../source')

    def test_malformed_verdict_not_approved(self):
        bad = verdict(); bad['findings'] = verdict('changes_requested')['findings']
        with self.assertRaises(ValueError):
            core.validate_review(bad)
        with self.assertRaises(ValueError):
            core.validate_review({'verdict': 'approve'})

    def test_worker_error_and_denial_not_approved(self):
        out = self.root / 'claude.log'
        out.write_text(json.dumps({'type': 'result', 'subtype': 'success', 'permission_denials': ['Read'], 'structured_output': verdict()}))
        with self.assertRaises(RuntimeError):
            core.parse_output('claude', out, out, True)
        out.write_text(json.dumps({'type': 'result', 'subtype': 'error_max_budget_usd', 'is_error': True}))
        with self.assertRaises(RuntimeError):
            core.parse_output('claude', out, out, True)

    def test_mcp_subprocess_transport(self):
        env = dict(os.environ, GAUNTLET_STATE_DIR=str(core.STATE))
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'gauntlet_projects', 'arguments': {}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'gauntlet_start', 'arguments': {'project': 'demo', 'task': 'x', 'max_rounds': False}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'ping'},
        ]
        p = subprocess.run([sys.executable, str(core.HOME / 'bridge.py'), 'mcp'],
                           input='\n'.join(json.dumps(m) for m in messages) + '\n', text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual(len(replies), 5)
        self.assertEqual(len(replies[1]['result']['tools']), 6)
        self.assertFalse(replies[2]['result']['isError'])
        self.assertTrue(replies[3]['result']['isError'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
