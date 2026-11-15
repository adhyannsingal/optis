from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from optis.api import create_app
from optis.arm.fake import FakeArm, STAGES
from optis.coordinator import Coordinator
from optis.cup_bridge import CupDemo
from optis.interaction.voice import command
from optis.perception.simulated_table import table_observation


class Voice:
    text = 'Put the cup in the tray'
    def transcribe(self, *args):
        return self.text
    def speak(self, text):
        return b'simulated-audio', 'audio/mpeg'


class CupApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 100.0
        self.arm = FakeArm(step_seconds=0)
        self.c = Coordinator(self.arm, clock=lambda: self.now)
        self.demo = CupDemo(coordinator=self.c)
        self.demo.start = lambda: None  # Tests control every synthetic frame.
        self.voice = Voice()
        app = create_app(database=Path(self.temp.name)/'db', token='user-token',
                         spotter_token='spotter-token', cup_demo=self.demo, voice=self.voice)
        self.app = app
        self.client = TestClient(app, client=('127.0.0.1', 1000))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.user = {'Authorization': 'Bearer user-token'}
        self.spotter = {'Authorization': 'Bearer spotter-token'}
        self.frame = 0

    def feed(self):
        for _ in range(2):
            self.frame += 1
            self.c.observe(table_observation(self.frame, now_ms=self.now*1000))

    def action(self, action, task_id=None):
        body = dict(action=action)
        if task_id:
            body['task_id'] = task_id
        return self.client.post('/v1/cup-demo/spotter', json=body, headers=self.spotter)

    def test_typed_bench_flow_needs_separate_exact_spotter_approval(self):
        self.assertEqual(self.client.get('/camera').status_code, 200)
        self.assertIn('cup-simulation', self.client.get('/camera').text)
        self.assertEqual(self.client.get('/v1/cup-demo/ui.js').status_code, 200)
        self.assertEqual(self.client.get('/v1/health').json()['arm'], 'disabled')
        self.assertEqual(self.client.get('/v1/cup-demo').status_code, 401)
        self.feed()
        self.action('enable')
        pending = self.client.post('/v1/cup-demo/request', headers=self.user,
                                  json=dict(text='Put the cup in the tray', request_id='typed-1')).json()
        self.assertEqual(pending['status'], 'awaiting_approval')
        task = pending['data']['task_id']
        self.assertEqual(self.arm.commands, [])
        self.assertEqual(self.client.post('/v1/cup-demo/spotter', headers=self.user,
                         json=dict(action='approve', task_id=task)).status_code, 401)
        self.assertEqual(self.action('approve', 'wrong').json()['status'], 'wrong_task')
        self.assertEqual(self.action('approve', task).status_code, 200)
        self.c.worker.join(timeout=2)
        result = self.client.get('/v1/cup-demo', headers=self.user).json()
        self.assertEqual(result['status']['state'], 'complete')
        self.assertFalse(result['real_execution'])
        self.assertEqual(len(result['commands']), len(STAGES))
        self.assertEqual(self.action('approve', task).json()['status'], 'wrong_task')
        self.c.observe(table_observation(10, 'missing', self.now*1000))
        refused = self.client.post('/v1/cup-demo/request', headers=self.user,
                                  json=dict(text='Put the cup in the tray', request_id='missing-2')).json()
        self.assertEqual(refused['status'], 'no_target')
        self.assertEqual(refused['data']['state'], 'idle')
        self.assertIsNone(refused['data']['task_id'])
        self.assertEqual(len(self.arm.commands), len(STAGES))

    def test_remote_spotter_and_spoofed_loopback_are_denied(self):
        remote = TestClient(self.app, client=('192.0.2.4', 1000))
        try:
            result = remote.post('/v1/cup-demo/spotter', json={'action': 'enable'},
                                 headers={**self.spotter, 'X-Forwarded-For': '127.0.0.1'})
            self.assertEqual(result.status_code, 403)
        finally:
            remote.close()
        self.assertEqual(self.arm.commands, [])

    def test_user_cannot_inject_observations_or_approve_through_intent(self):
        self.assertEqual(self.client.post('/v1/cup-demo/scenario', headers=self.user,
                         json={'scenario': 'valid'}).status_code, 401)
        self.assertEqual(self.client.post('/v1/intent', headers=self.user,
                         json=dict(request_id='bad', kind='approve', item='cup')).status_code, 422)
        self.assertEqual(self.client.post('/v1/cup-demo/request', headers=self.user,
                         json=dict(request_id='bad', text='approve cup')).status_code, 422)
        self.assertEqual(self.client.post('/v1/cup-demo/spotter', headers=self.spotter,
                         json=dict(action='approve')).status_code, 422)

    def test_voice_creates_pending_but_cannot_approve_enable_or_reset(self):
        self.feed()
        self.action('enable')
        result = self.client.post('/v1/voice', headers={**self.user, 'Content-Type': 'audio/wav'},
                                  content=b'fake recording').json()
        self.assertEqual(result['status'], 'awaiting_approval')
        self.assertEqual(self.arm.commands, [])
        for phrase in ('approve', 'enable', 'reset', 'approve the cup', 'move joint 1'):
            self.assertIsNone(command(phrase))
        self.voice.text = 'Stop the arm'
        result = self.client.post('/v1/voice', headers={**self.user, 'Content-Type': 'audio/wav'},
                                  content=b'fake recording').json()
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(self.c.status()['state'], 'stopped')
        self.assertEqual(self.arm.commands, [])

    def test_default_backend_remains_disabled(self):
        app = create_app(database=Path(self.temp.name)/'default-db', token='test')
        with TestClient(app) as client:
            result = client.post('/v1/intent', headers={'Authorization': 'Bearer test'},
                                 json=dict(request_id='default', kind='retrieve', item='cup'))
            self.assertEqual(result.json()['status'], 'arm_disabled')
            self.assertEqual(client.get('/v1/cup-demo').status_code, 404)

    def test_distinct_spotter_secret_is_required(self):
        for value in (None, 'user-token'):
            with self.assertRaises(ValueError):
                create_app(token='user-token', spotter_token=value, cup_demo=self.demo)


if __name__ == '__main__':
    unittest.main()
