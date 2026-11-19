import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
from authenticated_action_gate import (
    DOMAIN, ENVELOPE_SCHEMA, KEYS_ENV, PolicyError,
    authorize_and_execute, canonical_bytes, load_trusted_keys,
    read_strict_json, verify_signed_envelope,
)
from agent_action_policy import POLICY_SCHEMA, REQUEST_SCHEMA

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
SECRET = bytes(range(1, 33))  # test-only public fixture; never use in deployment
OTHER_SECRET = bytes(range(64, 96))


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def policy():
    return {'schema': POLICY_SCHEMA, 'rules': [{
        'id': 'health_and_evidence', 'effect': 'allow',
        'principals': ['audit-agent'],
        'actions': ['health.inspect', 'evidence.inspect'],
        'resources': ['service:work-covenant'],
        'environments': ['staging'],
        'expires_at': '2027-12-31T23:59:59Z',
    }]}


def envelope(action='evidence.inspect', text='verified bytes', *, nonce='a' * 30,
             principal='audit-agent', start=NOW, expires=NOW + timedelta(minutes=2)):
    request = {
        'schema': REQUEST_SCHEMA, 'principal': principal,
        'action': action, 'resource': 'service:work-covenant',
        'environment': 'staging'
    }
    result = {
        'schema': ENVELOPE_SCHEMA, 'request': request,
        'payload': {'text': text} if action == 'evidence.inspect' else {},
        'issued_at': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'expires_at': expires.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'nonce': nonce,
    }
    result['signature'] = b64(hmac.new(SECRET, canonical_bytes(result), hashlib.sha256).digest())
    return result


class AuthenticatedGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'nonces.sqlite'
        self.keys = {'audit-agent': SECRET}

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, payload, **kw):
        return authorize_and_execute(policy(), payload, self.keys, self.db, clock=kw.get('clock', NOW))

    def test_signed_evidence_is_executed_after_policy(self):
        result = self.run_gate(envelope())
        self.assertEqual(result['decision'], 'allow')
        self.assertTrue(result['principal_authenticated_by_shared_key'])
        self.assertFalse(result['real_world_identity_verified'])
        self.assertFalse(result['external_authorization_granted'])
        self.assertTrue(result['action_executed'])
        self.assertEqual(result['result']['sha256'], hashlib.sha256(b'verified bytes').hexdigest())

    def test_signed_health_is_executed(self):
        result = self.run_gate(envelope('health.inspect'))
        self.assertEqual(result['decision'], 'allow')
        self.assertTrue(result['result']['ok'])

    def test_replay_is_rejected(self):
        signed = envelope()
        self.assertEqual(self.run_gate(signed)['decision'], 'allow')
        with self.assertRaises(PolicyError) as caught:
            self.run_gate(signed)
        self.assertEqual(caught.exception.code, 'replayed_nonce')

    def test_replay_persists_across_new_connection(self):
        signed = envelope()
        self.run_gate(signed)
        with self.assertRaises(PolicyError):
            authorize_and_execute(policy(), signed, self.keys, Path(str(self.db)), clock=NOW)

    def test_concurrent_duplicate_only_one_succeeds(self):
        signed = envelope()
        def task(_):
            try:
                return self.run_gate(signed)['decision']
            except PolicyError as ex:
                return ex.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(task, range(8)))
        self.assertEqual(results.count('allow'), 1, results)
        self.assertEqual(results.count('replayed_nonce'), 7, results)

    def test_signed_payload_tampering_rejected(self):
        signed = envelope()
        signed['payload']['text'] = 'tampered'
        with self.assertRaises(PolicyError) as caught:
            self.run_gate(signed)
        self.assertEqual(caught.exception.code, 'invalid_signature')

    def test_signed_principal_tampering_rejected(self):
        signed = envelope()
        signed['request']['principal'] = 'other-agent'
        with self.assertRaises(PolicyError):
            self.run_gate(signed)

    def test_signed_action_resource_environment_tampering_rejected(self):
        for field, value in (
            ('action', 'health.inspect'), ('resource', 'service:other'), ('environment', 'production')
        ):
            with self.subTest(field=field):
                signed = envelope()
                signed['request'][field] = value
                with self.assertRaises(PolicyError):
                    self.run_gate(signed)

    def test_wrong_secret_rejected(self):
        with self.assertRaises(PolicyError) as caught:
            authorize_and_execute(policy(), envelope(), {'audit-agent': OTHER_SECRET}, self.db, clock=NOW)
        self.assertEqual(caught.exception.code, 'invalid_signature')

    def test_missing_key_rejected(self):
        with self.assertRaises(PolicyError):
            authorize_and_execute(policy(), envelope(), {}, self.db, clock=NOW)

    def test_expiry_and_future_skew_rejected(self):
        for sample, instant in (
            (envelope(), NOW + timedelta(minutes=2)),
            (envelope(start=NOW + timedelta(seconds=31), expires=NOW + timedelta(minutes=3)), NOW),
            (envelope(start=NOW, expires=NOW + timedelta(minutes=6)), NOW),
        ):
            with self.subTest(instant=instant), self.assertRaises(PolicyError):
                self.run_gate(sample, clock=instant)

    def test_invalid_nonce_rejected(self):
        signed = envelope(nonce='abc')
        with self.assertRaises(PolicyError) as caught:
            self.run_gate(signed)
        self.assertEqual(caught.exception.code, 'invalid_nonce')

    def test_unknown_extra_field_fails_closed(self):
        signed = envelope()
        signed['skip_auth'] = True
        with self.assertRaises(PolicyError):
            self.run_gate(signed)

    def test_hard_blocked_financial_action_never_executes(self):
        signed = envelope('wallet.transfer')
        result = self.run_gate(signed)
        self.assertEqual(result['decision'], 'deny')
        self.assertEqual(result['reason'], 'hard_blocked_action')
        self.assertFalse(result['action_executed'])

    def test_policy_no_matching_allow_is_denied(self):
        signed = envelope()
        p = {'schema': POLICY_SCHEMA, 'rules': []}
        result = authorize_and_execute(p, signed, self.keys, self.db, clock=NOW)
        self.assertEqual(result['decision'], 'deny')
        self.assertFalse(result['action_executed'])

    def test_policy_allows_unimplemented_action_but_dispatch_refuses(self):
        p = policy()
        p['rules'][0]['actions'].append('repo.inspect')
        signed = envelope('repo.inspect')
        with self.assertRaises(PolicyError) as caught:
            authorize_and_execute(p, signed, self.keys, self.db, clock=NOW)
        self.assertEqual(caught.exception.code, 'unsupported_local_execution')

    def test_oversized_evidence_payload_rejected(self):
        signed = envelope(text='x' * 8193)
        with self.assertRaises(PolicyError):
            self.run_gate(signed)

    def test_wrong_resource_even_if_policy_allows_it_not_executed(self):
        p = policy()
        p['rules'][0]['resources'].append('service:other')
        signed = envelope()
        signed['request']['resource'] = 'service:other'
        unsigned = {k: v for k, v in signed.items() if k != 'signature'}
        signed['signature'] = b64(hmac.new(SECRET, canonical_bytes(unsigned), hashlib.sha256).digest())
        with self.assertRaises(PolicyError):
            authorize_and_execute(p, signed, self.keys, self.db, clock=NOW)

    def test_bad_db_path_fails_closed(self):
        bad = Path(self.tmp.name) / 'missing' / 'nonces.db'
        with self.assertRaises(PolicyError) as caught:
            authorize_and_execute(policy(), envelope(), self.keys, bad, clock=NOW)
        self.assertEqual(caught.exception.code, 'replay_store_unavailable')

    def test_malformed_keyring_is_rejected(self):
        for value in ('{}', '{"audit-agent":"abc"}', '{"audit-agent":"xx","audit-agent":"yy"}', ''):
            with self.subTest(value=value), self.assertRaises(PolicyError):
                load_trusted_keys({KEYS_ENV: value})

    def test_trusted_keys_env_accepts_one_strong_key(self):
        result = load_trusted_keys({KEYS_ENV: json.dumps({'audit-agent': b64(SECRET)})})
        self.assertEqual(result, self.keys)

    def test_cli_without_keys_denies_without_secret_leak(self):
        envfile = Path(self.tmp.name) / 'envelope.json'
        policyfile = Path(self.tmp.name) / 'policy.json'
        envfile.write_text(json.dumps(envelope()), encoding='utf-8')
        policyfile.write_text(json.dumps(policy()), encoding='utf-8')
        env = dict(os.environ)
        env.pop(KEYS_ENV, None)
        run = subprocess.run([
            sys.executable, str(ROOT / 'automation' / 'authenticated_action_gate.py'),
            '--policy', str(policyfile), '--envelope', str(envfile),
            '--replay-db', str(self.db)], text=True, capture_output=True, env=env)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)['decision'], 'deny')
        self.assertNotIn('audit-agent', run.stdout)

    def test_distinct_nonce_permits_new_request(self):
        self.assertEqual(self.run_gate(envelope(nonce='a' * 30))['decision'], 'allow')
        self.assertEqual(self.run_gate(envelope(nonce='b' * 30))['decision'], 'allow')

if __name__ == '__main__':
    unittest.main()
