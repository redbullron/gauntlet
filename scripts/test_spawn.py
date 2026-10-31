"""Local controller tests. Never launches Claude or paid inference."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import spawn
from process_runner import run, Stopped


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gauntlet-spawn-test-')
        self.root = Path(self.temp.name)
        self.oldroot = spawn.ROOT
        spawn.ROOT = self.root / 'state'
        self.source = self.root / 'project'
        self.source.mkdir()
        (self.source / 'one.txt').write_text('original\n')
        (self.source / 'two.txt').write_text('second\n')

    def tearDown(self):
        spawn.ROOT = self.oldroot
        # Windows can briefly retain a file lock after the owned process exits.
        # Bound cleanup retries and still fail if the file remains locked.
        deadline = time.monotonic() + 2
        while True:
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    def manifest(self, mode='edit', checks=None):
        return spawn.validate({'name': 'local test', 'claude_executable': 'NOT_EXECUTED', 'concurrency': 2,
            'tasks': [{'id': 'one', 'source': str(self.source), 'mode': mode, 'task': 'local test',
                       'write_paths': ['one.txt'] if mode == 'edit' else [], 'checks': checks or []}]})

    def fake(self, edit=True, path='one.txt', malformed=False):
        def invoke(command, cwd, output, **kwargs):
            if edit:
                (cwd / path).write_text('changed\n')
            Path(output).write_text('not JSON' if malformed else json.dumps({'type': 'result', 'subtype': 'success',
                'is_error': False, 'result': 'Local fake report', 'modelUsage': {'fake-model': {}}, 'permission_denials': []}))
            return 0
        return invoke

    def execute(self, manifest, invoke):
        batch = spawn.create_batch(manifest)
        spawn.coordinate(batch, invoke)
        return batch, spawn.read(batch / 'one/result.json')

    def test_patch_isolation_and_no_validation_claim(self):
        batch, result = self.execute(self.manifest(), self.fake())
        self.assertEqual(result['state'], 'needs_validation')
        self.assertTrue(result['source_unchanged'])
        self.assertEqual((self.source / 'one.txt').read_text(), 'original\n')
        patch = (batch / 'one/changes.patch').read_text()
        self.assertIn('+changed', patch)
        self.assertEqual(result['models_returned'], ['fake-model'])

    def test_real_check_and_mutation_detection(self):
        checks = [{'command': [sys.executable, '-c', 'from pathlib import Path; assert Path("one.txt").read_text()=="changed\\n"'], 'timeout_seconds': 10}]
        _, result = self.execute(self.manifest(checks=checks), self.fake())
        self.assertEqual(result['state'], 'needs_review', result)
        checks[0]['command'] = [sys.executable, '-c', 'from pathlib import Path; Path("two.txt").write_text("oops")']
        _, result = self.execute(self.manifest(checks=checks), self.fake())
        self.assertEqual(result['state'], 'failed')
        self.assertIn('validation modified', result['error'])

    def test_scope_read_only_and_malformed(self):
        for manifest, fake in [(self.manifest(), self.fake(path='two.txt')),
                               (self.manifest('read'), self.fake()),
                               (self.manifest(), self.fake(malformed=True))]:
            _, result = self.execute(manifest, fake)
            self.assertEqual(result['state'], 'failed')
        _, result = self.execute(self.manifest('read'), self.fake(edit=False))
        self.assertEqual(result['state'], 'needs_review')

    def test_parallel_cap_and_queue(self):
        manifest = self.manifest('read')
        manifest['tasks'] = [dict(manifest['tasks'][0], id=f'job{i}') for i in range(4)]
        lock = threading.Lock()
        active = peak = count = 0
        def fake(*args, **kwargs):
            nonlocal active, peak, count
            with lock:
                active += 1
                peak = max(peak, active)
                count += 1
            time.sleep(0.3)
            self.fake(edit=False)(*args, **kwargs)
            with lock:
                active -= 1
            return 0
        batch = spawn.create_batch(manifest)
        spawn.coordinate(batch, fake)
        self.assertEqual(peak, 2)
        self.assertEqual(count, 4)
        self.assertTrue(all(s == 'needs_review' for s in spawn.read(batch / 'status.json')['tasks'].values()))

    def test_limits_and_cancel_prevent_invocation(self):
        for cancel in (False, True):
            batch = spawn.create_batch(self.manifest())
            if cancel:
                (batch / 'CANCEL').touch()
            else:
                state = spawn.read(batch / 'status.json')
                state['deadline'] = time.time() - 1
                spawn.save(batch / 'status.json', state)
            spawn.coordinate(batch, lambda *a, **k: self.fail('worker should not run'))
            self.assertEqual(spawn.read(batch / 'one/result.json')['state'], 'cancelled' if cancel else 'limit_reached')

    def test_manifest_rejects_overlap_traversal_and_bad_limits(self):
        data = self.manifest()
        for path in ('../bad', 'C:/bad', '/bad', '.git/config', 'src/../../bad'):
            value = copy.deepcopy(data)
            value['tasks'][0]['write_paths'] = [path]
            with self.assertRaises(ValueError):
                spawn.validate(value)
        data['tasks'].append(dict(data['tasks'][0], id='other'))
        with self.assertRaises(ValueError):
            spawn.validate(data)
        data = self.manifest()
        data['max_minutes'] = float('nan')
        with self.assertRaises(ValueError):
            spawn.validate(data)

    def test_inventory_excludes_credentials_and_builds(self):
        (self.source / '.env').write_text('FAKE_TEST_FIXTURE')
        (self.source / 'node_modules').mkdir()
        (self.source / 'node_modules/ignore.txt').write_text('ignored')
        inv = spawn.inventory(self.source)
        self.assertNotIn('.env', inv['files'])
        self.assertIn('.env', inv['excluded'])
        self.assertIn('node_modules/', inv['excluded'])

    def test_new_and_deleted_files(self):
        manifest = self.manifest()
        manifest['tasks'][0]['write_paths'].append('new.txt')
        def fake(command, cwd, output, **kw):
            (cwd / 'one.txt').unlink()
            return self.fake(path='new.txt')(command, cwd, output, **kw)
        batch, result = self.execute(manifest, fake)
        self.assertEqual(result['changed_files'], ['new.txt', 'one.txt'])
        self.assertIn('deleted file mode', (batch / 'one/changes.patch').read_text())
        self.assertIn('new file mode', (batch / 'one/changes.patch').read_text())

    def test_source_drift_and_permission_denials_fail(self):
        def fake(*a, **kw):
            (self.source / 'two.txt').write_text('external edit')
            return self.fake()(*a, **kw)
        _, result = self.execute(self.manifest(), fake)
        self.assertFalse(result['source_unchanged'])
        self.assertEqual(result['state'], 'failed')
        path = self.root / 'report.json'
        spawn.save(path, {'type': 'result', 'subtype': 'success', 'permission_denials': [{}]})
        with self.assertRaises(ValueError):
            spawn.parse_report(path)

    def test_lock_and_interrupted_state(self):
        batch = spawn.create_batch(self.manifest())
        status = spawn.read(batch / 'status.json')
        status['state'] = 'running'
        spawn.save(batch / 'status.json', status)
        with spawn.Lock(batch / 'controller.lock'):
            self.assertEqual(spawn.status_of(batch)['state'], 'running')
            with self.assertRaises(RuntimeError):
                spawn.Lock(batch / 'controller.lock')
            with self.assertRaises(ValueError):
                spawn.start(self.manifest())
        self.assertEqual(spawn.status_of(batch)['state'], 'interrupted')

    def test_owned_process_timeout_and_cancellation(self):
        log = self.root / 'command.log'
        self.assertEqual(run([sys.executable, '-c', 'print("native ok")'], self.root, log, timeout=5), 0)
        self.assertIn('native ok', log.read_text())
        with self.assertRaisesRegex(Stopped, 'limit_reached'):
            run([sys.executable, '-c', 'import time; time.sleep(20)'], self.root, log, timeout=0.3)
        cancel = threading.Event()
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        try:
            with self.assertRaisesRegex(Stopped, 'cancelled'):
                run([sys.executable, '-c', 'import time; time.sleep(20)'], self.root, log, cancelled=cancel.is_set)
        finally:
            timer.join()

    def test_owned_descendant_stops(self):
        marker = self.root / 'child-ticks'
        child = 'import pathlib,time\np=pathlib.Path(' + repr(str(marker)) + ')\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.05)'
        parent = 'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",' + repr(child) + '])\ntime.sleep(20)'
        with self.assertRaises(Stopped):
            run([sys.executable, '-c', parent], self.root, self.root / 'tree.log', timeout=0.8)
        self.assertTrue(marker.exists())
        first = marker.read_text()
        time.sleep(0.3)
        self.assertEqual(marker.read_text(), first)

    def test_no_restart_and_detached_dispatch(self):
        manifest = self.manifest()
        # Python rejects Claude's arguments; exercises real detached dispatch with no inference.
        manifest['claude_executable'] = sys.executable
        previous = os.environ.get('GAUNTLET_SPAWN_HOME')
        os.environ['GAUNTLET_SPAWN_HOME'] = str(spawn.ROOT)
        try:
            launched = spawn.start(manifest)
            batch = Path(launched['directory'])
            until = time.time() + 15
            while time.time() < until:
                status = spawn.status_of(batch)
                if status['state'] not in spawn.ACTIVE:
                    break
                time.sleep(0.1)
            self.assertEqual(status['state'], 'completed')
            self.assertEqual(spawn.read(batch / 'one/result.json')['state'], 'failed')
            with self.assertRaises(ValueError):
                spawn.coordinate(batch, self.fake())
        finally:
            if previous is None:
                os.environ.pop('GAUNTLET_SPAWN_HOME', None)
            else:
                os.environ['GAUNTLET_SPAWN_HOME'] = previous

    def test_new_excluded_files_are_not_patched(self):
        def fake(command, cwd, output, **kwargs):
            (cwd / '.env').write_text('FAKE_TEST_FIXTURE')
            return self.fake()(command, cwd, output, **kwargs)
        batch, result = self.execute(self.manifest(), fake)
        self.assertNotIn('FAKE_TEST_FIXTURE', (batch / 'one/changes.patch').read_text())
        self.assertEqual(result['changed_files'], ['one.txt'])

    @unittest.skipUnless(os.name == 'nt', 'Windows kill-on-close job contract')
    def test_controller_loss_closes_native_worker_job(self):
        marker = self.root / 'worker-ticks'
        child = 'import pathlib,time\np=pathlib.Path(' + repr(str(marker)) + ')\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.05)'
        controller = ('import sys\nfrom pathlib import Path\nsys.path.insert(0,' + repr(str(Path(__file__).parent)) + ')\n'
                      'from process_runner import run\nrun([sys.executable,"-c",' + repr(child) + '],Path(' + repr(str(self.root)) + '),Path(' + repr(str(self.root / 'loss.log')) + '),timeout=20)')
        process = subprocess.Popen([sys.executable, '-c', controller], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            until = time.time() + 5
            while not marker.exists() and time.time() < until:
                time.sleep(.05)
            self.assertTrue(marker.exists())
            process.kill()  # Retained test process handle, never PID discovery/adoption.
            process.wait(timeout=5)
            time.sleep(.2)
            first = marker.read_text()
            time.sleep(.3)
            self.assertEqual(marker.read_text(), first)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
