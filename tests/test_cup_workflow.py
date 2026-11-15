"""All observations and arm commands in these tests are simulated."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import unittest

from optis.arm.fake import FakeArm, STAGES
from optis.coordinator import Coordinator
from optis.perception.simulated_table import table_observation


class CupWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.arm = FakeArm(step_seconds=0)
        self.c = Coordinator(self.arm, clock=lambda: self.now)
        self.addCleanup(self.c.close)
        self.frame = 0

    def feed(self, scenario='valid'):
        for _ in range(2):
            self.frame += 1
            self.c.observe(table_observation(self.frame, scenario, self.now*1000))

    def pending(self, request_id='request-1'):
        count = len(self.arm.commands)
        self.feed()
        self.c.enable()
        result = self.c.submit('retrieve', 'cup', request_id=request_id)
        self.assertEqual(result['state'], 'awaiting_approval', result)
        self.assertEqual(len(self.arm.commands), count)
        return result['task_id']

    def join(self):
        self.c.worker.join(timeout=2)
        self.assertFalse(self.c.worker.is_alive())

    def test_disabled_boot_and_real_adapter_is_rejected(self):
        self.feed()
        self.assertEqual(self.c.submit('retrieve', 'cup')['code'], 'needs_enable')
        self.assertEqual(self.arm.commands, [])
        for mode in ('bench', 'live'):
            with self.assertRaises(ValueError):
                Coordinator(mode=mode)
        with self.assertRaises(ValueError):
            Coordinator(arm=object())

    def test_success_reports_all_stages_and_consumes_approval_once(self):
        task = self.pending()
        self.c.approve(task)
        self.join()
        self.assertEqual(self.c.status()['state'], 'complete')
        self.assertEqual([cmd['stage'] for cmd in self.arm.commands], list(STAGES))
        self.assertTrue(all(cmd['task_id'] == task for cmd in self.arm.commands))
        self.assertEqual([e['stage'] for e in self.c.events if e['state'] == 'executing' and e['stage']], list(STAGES))
        self.assertEqual(self.c.approve(task)['code'], 'wrong_task')
        self.assertEqual(len(self.arm.commands), len(STAGES))
        self.assertEqual(self.c.submit('retrieve', 'cup', request_id='request-1')['code'], 'wrong_task')
        pending = self.c.submit('retrieve', 'cup', request_id='request-2')
        self.c.approve(pending['task_id'])
        self.join()
        self.assertEqual(len(self.arm.commands), 2*len(STAGES))

    def test_all_camera_negatives_prevent_admission(self):
        self.c.enable()
        codes = {'missing': 'no_target', 'off_mark': 'wrong_zone', 'ambiguous': 'ambiguous',
                 'references': 'fixture_invalid', 'wrong_fixture': 'fixture_invalid',
                 'stale': 'stale_frame', 'disconnected': 'stale_frame'}
        for scenario, code in codes.items():
            with self.subTest(scenario=scenario):
                self.feed(scenario)
                self.assertEqual(self.c.submit('retrieve', 'cup')['code'], code)
                self.assertEqual(self.arm.commands, [])

    def test_two_distinct_consecutive_frames_are_required(self):
        self.c.enable()
        first = table_observation(1, now_ms=self.now*1000)
        self.c.observe(first)
        self.c.observe(first)
        self.assertEqual(self.c.submit('retrieve', 'cup')['code'], 'stale_frame')
        self.c.observe(table_observation(2, 'missing', self.now*1000))
        self.c.observe(table_observation(3, now_ms=self.now*1000))
        self.assertEqual(self.c.submit('retrieve', 'cup')['code'], 'stale_frame')
        self.c.observe(table_observation(4, now_ms=self.now*1000))
        self.assertEqual(self.c.submit('retrieve', 'cup')['state'], 'awaiting_approval')

    def test_approval_rechecks_every_camera_failure(self):
        for scenario in ('missing', 'off_mark', 'ambiguous', 'references', 'wrong_fixture', 'stale', 'disconnected'):
            with self.subTest(scenario=scenario):
                task = self.pending(request_id=scenario)
                self.feed(scenario)
                result = self.c.approve(task)
                self.assertEqual(result['state'], 'idle')
                self.assertIsNone(result['task_id'])
                self.assertEqual(self.arm.commands, [])
                self.c.reset()

    def test_expired_wrong_and_concurrent_approvals(self):
        task = self.pending()
        self.assertEqual(self.c.approve('wrong-id')['code'], 'wrong_task')
        self.assertEqual(self.c.status()['task_id'], task)
        self.now += 10  # Exact deadline is expired, even with refreshed frames.
        self.feed()
        self.assertEqual(self.c.approve(task)['code'], 'approval_expired')
        self.assertEqual(self.arm.commands, [])
        self.c.reset()
        task = self.pending('second')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.c.approve(task), range(8)))
        self.join()
        self.assertEqual(len(self.arm.commands), len(STAGES))

    def test_pending_is_single_and_requests_are_deduplicated(self):
        self.feed()
        self.c.enable()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda n: self.c.submit('retrieve', 'cup', request_id=str(n)), range(4)))
        self.assertEqual(sum(r['code'] is None for r in results), 1)
        self.assertEqual(sum(r['code'] == 'busy' for r in results), 3)
        self.assertEqual(self.arm.commands, [])

    def test_stop_cancels_pending_and_latches_until_reset_enable(self):
        task = self.pending()
        self.c.stop()
        self.assertEqual(self.c.approve(task)['code'], 'wrong_task')
        self.assertEqual(self.c.submit('retrieve', 'cup')['code'], 'needs_enable')
        self.assertEqual(self.c.enable()['code'], 'needs_enable')
        self.assertEqual(self.arm.commands, [])
        self.c.reset()
        self.assertEqual(self.c.status()['state'], 'disabled')
        self.assertEqual(self.c.enable()['state'], 'idle')

    def test_stop_and_gate_failures_during_motion_prevent_next_command(self):
        for scenario in ('stop', 'missing', 'off_mark', 'references', 'wrong_fixture', 'stale', 'disconnected'):
            with self.subTest(scenario=scenario):
                self.c.reset()
                task = self.pending(scenario)
                count = len(self.arm.commands)
                original = self.arm.move
                def move(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if scenario == 'stop':
                        self.c.stop()
                    else:
                        self.feed(scenario)
                    return result
                with patch.object(self.arm, 'move', side_effect=move):
                    self.c.approve(task)
                    self.join()
                self.assertEqual(len(self.arm.commands), count+1)
                self.assertIn(self.c.status()['state'], {'stopped', 'faulted'})

    def test_fault_disconnect_exception_and_timeout_prevent_next_command(self):
        for failure in ('fault', 'disconnect', 'exception', 'timeout'):
            with self.subTest(failure=failure):
                self.c.reset()
                self.arm.connected = True
                self.arm.fail_at = None
                task = self.pending(failure)
                count = len(self.arm.commands)
                original = self.arm.move
                def move(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if failure == 'fault':
                        self.arm.fault = True
                    elif failure == 'disconnect':
                        self.arm.connected = False
                    elif failure == 'exception':
                        raise OSError('simulated serial failure')
                    else:
                        result.update(ok=False, code='arm_timeout')
                    return result
                with patch.object(self.arm, 'move', side_effect=move):
                    self.c.approve(task)
                    self.join()
                self.assertEqual(len(self.arm.commands), count+1)
                self.assertEqual(self.c.status()['state'], 'faulted')

    def test_fault_at_grip_stops_before_lift(self):
        task = self.pending()
        self.arm.fail_at = 'close'
        self.c.approve(task)
        self.join()
        self.assertEqual([cmd['stage'] for cmd in self.arm.commands], list(STAGES[:4]))
        self.assertEqual(self.c.status()['code'], 'arm_fault')

    def test_stale_approval_and_malformed_frame_are_rejected(self):
        task = self.pending()
        self.now += .751
        self.assertEqual(self.c.approve(task)['code'], 'stale_frame')
        self.assertEqual(self.arm.commands, [])
        self.c.reset()
        self.c.enable()
        for field, value in [('seen_ms', float('nan')), ('frame_id', True), ('reference_ok', 1),
                             ('mode', 'live'), ('source', 'head'), ('size_px', [0, 480])]:
            obs = table_observation(self.frame+1, now_ms=self.now*1000)
            obs[field] = value
            self.c.observe(obs)
            self.assertIsNotNone(self.c.gate.check(self.now*1000))
        obs = table_observation(self.frame+10, now_ms=self.now*1000)
        obs['detections'][0]['bbox_xyxy_px'] = [0, 0, 9999, 100]
        self.c.observe(obs)
        self.assertEqual(self.c.gate.check(self.now*1000), 'fixture_invalid')

    def test_health_is_rechecked_before_approval(self):
        task = self.pending()
        self.arm.connected = False
        self.assertEqual(self.c.approve(task)['code'], 'arm_fault')
        self.assertEqual(self.arm.commands, [])

    def test_stop_interrupts_an_inflight_step_without_waiting_for_it(self):
        task = self.pending()
        self.arm.step_seconds = 2
        entered = Event()
        original_wait = self.arm.cancel.wait
        def wait(timeout):
            entered.set()
            return original_wait(timeout)
        with patch.object(self.arm.cancel, 'wait', side_effect=wait):
            self.c.approve(task)
            self.assertTrue(entered.wait(timeout=1))
            self.c.stop()
            self.join()
        self.assertEqual(len(self.arm.commands), 1)
        self.assertEqual(self.c.status()['state'], 'stopped')

    def test_task_time_limit_prevents_the_next_command(self):
        task = self.pending()
        original_move = self.arm.move
        def move(*args, **kwargs):
            result = original_move(*args, **kwargs)
            self.now += 30
            return result
        with patch.object(self.arm, 'move', side_effect=move):
            self.c.approve(task)
            self.join()
        self.assertEqual(len(self.arm.commands), 1)
        self.assertEqual(self.c.status()['code'], 'arm_timeout')


if __name__ == '__main__':
    unittest.main()
