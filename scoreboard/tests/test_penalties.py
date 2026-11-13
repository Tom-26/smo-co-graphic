import unittest
import test_server
module = test_server.module
from unittest.mock import patch
import json
import time


class PenaltyTests(unittest.TestCase):
    setUp = test_server.ScoreboardTests.setUp
    tearDown = test_server.ScoreboardTests.tearDown
    cmd = test_server.ScoreboardTests.cmd
    def add(self, side='home', seconds=120, player='27'):
        return self.cmd('penalty_add', dict(side=side, durationSec=seconds, player=player))

    def test_pause_projection_and_remove(self):
        with patch.object(module.time, 'monotonic', return_value=1000) as clock:
            self.add()
            self.cmd('start')
            clock.return_value = 1030
            self.assertEqual(self.store.snapshot()['penalties']['home'][0]['remainingMs'], 90000)
            self.cmd('pause')
            clock.return_value = 1100
            self.assertEqual(self.store.snapshot()['penalties']['home'][0]['remainingMs'], 90000)
            ident = self.store.snapshot()['penalties']['home'][0]['id']
            self.cmd('penalty_remove', dict(side='home', id=ident))
            self.assertEqual(self.store.snapshot()['penalties']['home'], [])

    def test_new_penalty_starts_at_addition_and_idempotent(self):
        with patch.object(module.time, 'monotonic', return_value=1000) as clock:
            self.add()
            self.cmd('start')
            clock.return_value = 1030
            self.cmd('penalty_add', dict(side='away', durationSec=300, player='9'), ident='same-penalty-command')
            self.cmd('penalty_add', dict(side='away', durationSec=300, player='9'), ident='same-penalty-command')
            state=self.store.snapshot()
            self.assertEqual(state['penalties']['home'][0]['remainingMs'], 90000)
            self.assertEqual(state['penalties']['away'][0]['remainingMs'], 300000)
            self.assertEqual(len(state['penalties']['away']),1)

    def test_clock_corrections_and_period_reset_preserve_penalties(self):
        with patch.object(module.time, 'monotonic', return_value=1000) as clock:
            self.add()
            self.cmd('start')
            clock.return_value = 1030
            self.cmd('adjust', -10)
            self.assertEqual(self.store.snapshot()['penalties']['home'][0]['remainingMs'], 90000)
            self.cmd('set_time', 100)
            self.cmd('period', '2')
            self.cmd('reset_clock')
            self.assertEqual(self.store.snapshot()['penalties']['home'][0]['remainingMs'], 90000)
            self.assertFalse(self.store.snapshot()['running'])

    def test_penalty_and_period_expiration(self):
        with patch.object(module.time, 'monotonic', return_value=1000) as clock:
            self.add(seconds=2)
            self.add(side='away', seconds=120)
            self.cmd('set_time', 5)
            self.cmd('start')
            clock.return_value = 1002
            self.store.expire()
            self.assertEqual(self.store.snapshot()['penalties']['home'], [])
            self.assertTrue(self.store.snapshot()['running'])
            clock.return_value = 1100
            self.store.expire()
            self.assertEqual(self.store.snapshot()['penalties']['away'][0]['remainingMs'], 115000)
            self.assertFalse(self.store.snapshot()['running'])

    def test_restart_downtime_capped_at_period_end(self):
        self.add(seconds=120)
        self.cmd('set_time',5)
        self.cmd('start')
        disk=json.loads(self.path.read_text())
        disk['deadlineUnixMs']=time.time()*1000-30000
        self.path.write_text(json.dumps(disk))
        recovered=module.Store(self.path).snapshot()
        self.assertEqual(recovered['penalties']['home'][0]['remainingMs'],115000)
        self.assertFalse(recovered['running'])

    def test_restart_running_penalty_keeps_elapsed_time(self):
        self.add(seconds=120)
        self.cmd('start')
        disk=json.loads(self.path.read_text())
        disk['deadlineUnixMs']-=30000
        self.path.write_text(json.dumps(disk))
        recovered=module.Store(self.path).snapshot()
        self.assertTrue(recovered['running'])
        self.assertAlmostEqual(recovered['penalties']['home'][0]['remainingMs'],90000,delta=50)

    def test_old_match_import_and_new_match(self):
        old=self.store.snapshot()
        del old['penalties']
        self.cmd('import',old)
        self.assertEqual(self.store.snapshot()['penalties'],dict(home=[],away=[]))
        self.add()
        self.cmd('import',self.store.snapshot())
        self.assertEqual(self.store.snapshot()['penalties']['home'][0]['player'],'27')
        self.assertFalse(self.store.snapshot()['running'])
        self.cmd('new_match')
        self.assertEqual(self.store.snapshot()['penalties'],dict(home=[],away=[]))

    def test_limits_validation_and_failed_write(self):
        self.add()
        self.add(player='99')
        with self.assertRaises(ValueError): self.add(player='1')
        with self.assertRaises(ValueError): self.add(side='other')
        with self.assertRaises(ValueError): self.add(side='away', player='<b>')
        with self.assertRaises(ValueError): self.add(side='away', seconds=-1)
        with patch.object(self.store, 'persist', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.add(side='away')
        self.assertEqual(len(self.store.snapshot()['penalties']['home']),2)
        self.assertEqual(self.store.snapshot()['penalties']['away'],[])
