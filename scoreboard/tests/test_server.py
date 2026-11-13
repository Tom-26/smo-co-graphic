import concurrent.futures
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scoreboard_server', Path(__file__).resolve().parents[1] / 'server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScoreboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'state.json'
        self.store = module.Store(self.path)
        self.index = 0

    def tearDown(self):
        self.tmp.cleanup()

    def cmd(self, action, value=None, ident=None):
        self.index += 1
        return self.store.command(dict(id=ident or f'command-{self.index}', action=action, value=value))

    def test_clock_pause_restart_and_zero(self):
        self.cmd('set_time', 1)
        self.cmd('start')
        time.sleep(.06)
        self.assertLess(self.store.remaining(), 1000)
        self.cmd('pause')
        frozen = self.store.remaining()
        time.sleep(.02)
        self.assertEqual(self.store.remaining(), frozen)
        recovered = module.Store(self.path)
        self.assertEqual(recovered.remaining(), frozen)
        self.cmd('start')
        # Simulate elapsed game time without waiting for a full period.
        with self.store.lock:
            self.store.deadline = time.monotonic() - 1
        self.store.expire()
        state = self.store.snapshot()
        self.assertEqual(state['remainingMs'], 0)
        self.assertFalse(state['running'])
        self.cmd('start')
        self.assertFalse(self.store.snapshot()['running'])

    def test_restart_running_counts_downtime(self):
        self.cmd('set_time', 10)
        self.cmd('start')
        disk = json.loads(self.path.read_text())
        disk['deadlineUnixMs'] -= 3000
        self.path.write_text(json.dumps(disk))
        recovered = module.Store(self.path).snapshot()
        self.assertTrue(recovered['running'])
        self.assertLessEqual(recovered['remainingMs'], 7000)
        self.assertGreater(recovered['remainingMs'], 6000)

    def test_system_clock_change_does_not_shift_active_timer(self):
        self.cmd('start')
        before = self.store.remaining()
        with patch.object(module.time, 'time', return_value=time.time()+100000):
            after = self.store.remaining()
        self.assertLessEqual(abs(after-before), 10)

    def test_adjust_and_period_do_not_reset_score_or_clock(self):
        self.cmd('score', dict(side='home', delta=1))
        self.cmd('set_time', 500)
        self.cmd('period', '2')
        self.assertEqual(self.store.remaining(), 500000)
        self.cmd('start')
        self.cmd('adjust', 10)
        self.assertTrue(self.store.snapshot()['running'])
        self.assertGreater(self.store.remaining(), 509000)
        self.cmd('adjust', -600)
        self.assertEqual(self.store.remaining(), 0)
        self.assertFalse(self.store.snapshot()['running'])
        self.cmd('reset_clock')
        s = self.store.snapshot()
        self.assertEqual((s['home']['score'], s['period'], s['remainingMs']), (1, '2', 1200000))

    def test_idempotency_and_concurrent_scoring(self):
        value = dict(side='home', delta=1)
        self.cmd('score', value, 'same-command')
        self.cmd('score', value, 'same-command')
        self.assertEqual(self.store.snapshot()['home']['score'], 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: self.store.command(dict(id=f'parallel-{n}', action='score', value=value)), range(30)))
        self.assertEqual(self.store.snapshot()['home']['score'], 31)
        self.assertEqual(module.Store(self.path).snapshot()['home']['score'], 31)

    def test_atomic_rollback_on_failed_save(self):
        before = self.store.snapshot()
        with patch.object(self.store, 'persist', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.cmd('score', dict(side='home', delta=1))
        after = self.store.snapshot()
        self.assertEqual(after['home']['score'], before['home']['score'])
        self.assertEqual(after['revision'], before['revision'])

    def test_settings_transaction_validation_and_import_paused(self):
        self.cmd('score', dict(side='home', delta=1))
        self.cmd('start')
        value = self.store.snapshot()
        value['home']['name'] = 'Команда <script> & А'
        value['durationSec'] = 900
        self.cmd('settings', value)
        self.assertEqual(self.store.snapshot()['home']['score'], 1)
        self.assertTrue(self.store.snapshot()['running'])
        self.assertEqual(self.store.snapshot()['durationSec'], 900)
        broken = self.store.snapshot()
        broken['home']['name'] = 'Не должно сохраниться'
        broken['away']['color'] = 'bad'
        with self.assertRaises(ValueError):
            self.cmd('settings', broken)
        self.assertEqual(self.store.snapshot()['home']['name'], value['home']['name'])
        self.cmd('import', self.store.snapshot())
        self.assertFalse(self.store.snapshot()['running'])
        self.cmd('new_match')
        s = self.store.snapshot()
        self.assertEqual((s['home']['score'], s['period'], s['remainingMs']), (0, '1', 900000))
        self.assertEqual(s['home']['name'], value['home']['name'])

    def test_invalid_commands_do_not_mutate(self):
        before = self.store.snapshot()
        cases = [('set_time',-1), ('set_time',6000), ('set_time',True), ('set_time',float('nan')),
                 ('period','4'), ('score',dict(side='other',delta=1)), ('score',dict(side='home',delta=100)),
                 ('import',{}), ('visible','false'), ('unknown',None)]
        for action,value in cases:
            with self.assertRaises((ValueError, TypeError, KeyError)):
                self.cmd(action,value)
            self.assertEqual(self.store.snapshot()['revision'], before['revision'])

    def test_corrupt_state_is_preserved(self):
        raw = '{bad'
        self.path.write_text(raw)
        with self.assertRaises(ValueError):
            module.Store(self.path)
        self.assertEqual(self.path.read_text(), raw)

    def test_http_auth_files_and_live_event_stream(self):
        server = module.Server(('127.0.0.1',0), module.Handler)
        server.store, server.token = self.store, 'test-secret'
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, data=None, headers=None):
            return urllib.request.urlopen(urllib.request.Request(base+path, data=data, headers=headers or {}), timeout=3)
        try:
            with request('/control.html') as r:
                self.assertIn('пульт', r.read().decode())
                self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
            with request('/api/events') as r:
                self.assertEqual(r.readline().strip(), b'event: state')
                self.assertIn(b'"home"',r.readline())
            raw=json.dumps(dict(id='http-command',action='score',value=dict(side='away',delta=1))).encode()
            for headers in ({}, {'X-Scoreboard-Token':server.token,'Origin':'https://foreign.test'}, {'Host':'foreign.test'}):
                with self.assertRaises(urllib.error.HTTPError) as exc:
                    request('/api/command',raw,headers)
                self.assertEqual(exc.exception.code,403)
            with request('/api/command',raw,{'X-Scoreboard-Token':server.token}) as r:
                self.assertEqual(json.load(r)['away']['score'],1)
            with self.assertRaises(urllib.error.HTTPError):
                request('/server.py')
            with self.assertRaises(urllib.error.HTTPError):
                request('/data/state.json')
        finally:
            server.shutdown()
            server.server_close()
            t.join()


if __name__ == '__main__':
    unittest.main()
