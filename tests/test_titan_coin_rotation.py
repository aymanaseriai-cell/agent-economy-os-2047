import time
import unittest
from trading.okx_live_executor import (
    last_fully_closed_swap_symbol, choose_signal, ExecutionBlocked,
)


class FakeHistory:
    def __init__(self,rows):
        self.rows=rows
        self.calls=[]
    def request(self,method,path,*,params=None):
        self.calls.append((method,path,params))
        return list(self.rows)


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_800_000_000_000

    def record(self,symbol,minutes_ago=1,kind="2"):
        return {"instType":"SWAP","instId":symbol,"type":kind,
                "uTime":str(self.now-minutes_ago*60_000)}

    def test_latest_complete_exit_is_rotated(self):
        client=FakeHistory([self.record("BTC-USDT-SWAP",2),
                            self.record("ADA-USDT-SWAP",16)])
        self.assertEqual(last_fully_closed_swap_symbol(client,now_ms=self.now),
                         "BTC-USDT-SWAP")
        self.assertEqual(len(client.calls),1)

    def test_partial_exit_not_rotation(self):
        client=FakeHistory([self.record("BTC-USDT-SWAP",kind="1")])
        self.assertIsNone(last_fully_closed_swap_symbol(client,now_ms=self.now))

    def test_older_last_close_not_excluded(self):
        client=FakeHistory([self.record("BTC-USDT-SWAP",minutes_ago=180)])
        self.assertIsNone(last_fully_closed_swap_symbol(client,now_ms=self.now))

    def test_unknown_identity_fails_closed(self):
        row=self.record("BTC-USDT-SWAP")
        del row["instId"]
        with self.assertRaises(ExecutionBlocked):
            last_fully_closed_swap_symbol(FakeHistory([row]),now_ms=self.now)

    def test_multiple_recent_same_time_fails_closed(self):
        client=FakeHistory([self.record("BTC-USDT-SWAP"),
                            self.record("ETH-USDT-SWAP")])
        with self.assertRaises(ExecutionBlocked):
            last_fully_closed_swap_symbol(client,now_ms=self.now)

    def test_bounded_history_fails_closed(self):
        client=FakeHistory([self.record("BTC-USDT-SWAP")]*100)
        with self.assertRaisesRegex(ExecutionBlocked,"paginated"):
            last_fully_closed_swap_symbol(client,now_ms=self.now)

if __name__=="__main__":
    unittest.main()
