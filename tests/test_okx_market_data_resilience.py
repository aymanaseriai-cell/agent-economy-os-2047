"""Public market-data resilience: retry only GET, never trade on partial scans."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from trading.six_agent_council import (
    okx_get, transient_market_errors, RECOVERABLE_SCAN_EXIT,
)


def reply(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class PublicGetRecoveryTests(unittest.TestCase):
    def test_50026_then_success_retries_only_public_get(self):
        responses = [reply({"code":"50026", "msg":"System error. Try again later."}),
                     reply({"code":"0", "data":[{"k":"safe"}]})]
        with patch("trading.six_agent_council.urlopen", side_effect=responses) as get, \
             patch("trading.six_agent_council.time.sleep") as sleep:
            data = okx_get("/api/v5/market/candles", {"instId":"XPL-USDT-SWAP"})
        self.assertEqual(data,[{"k":"safe"}])
        self.assertEqual(get.call_count,2)
        sleep.assert_called_once_with(1)

    def test_persistent_50026_exhausts_budget_without_marking_scan_valid(self):
        responses = [reply({"code":"50026","msg":"System error"}) for _ in range(4)]
        with patch("trading.six_agent_council.urlopen", side_effect=responses) as get, \
             patch("trading.six_agent_council.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "OKX TRANSIENT 50026"):
                okx_get("/api/v5/market/candles", {"instId":"XPL-USDT-SWAP"})
        self.assertEqual(get.call_count,4)
        self.assertEqual([x.args[0] for x in sleep.call_args_list],[1,2,4])

    def test_rate_limit_is_backed_off(self):
        with patch("trading.six_agent_council.urlopen",
                   side_effect=[reply({"code":"50011"}),
                                reply({"code":"0","data":[]})]) as get, \
             patch("trading.six_agent_council.time.sleep"):
            self.assertEqual(okx_get("/api/v5/market/tickers",{"instType":"SWAP"}),[])
        self.assertEqual(get.call_count,2)

    def test_http_503_retries_public_get(self):
        exc=HTTPError("https://www.okx.com",503,"unavailable",{},None)
        with patch("trading.six_agent_council.urlopen",
                   side_effect=[exc,reply({"code":"0","data":[]})]) as get, \
             patch("trading.six_agent_council.time.sleep"):
            self.assertEqual(okx_get("/api/v5/public/instruments",{"instType":"SWAP"}),[])
        self.assertEqual(get.call_count,2)

    def test_bad_parameter_and_malformed_response_do_not_retry(self):
        for payload in ({"code":"51000","msg":"Bad parameter"},
                        {"code":"0","data":{}}, []):
            with self.subTest(payload=payload):
                with patch("trading.six_agent_council.urlopen",
                           return_value=reply(payload)) as get, \
                     patch("trading.six_agent_council.time.sleep") as sleep:
                    with self.assertRaises(ValueError):
                        okx_get("/api/v5/market/candles",{"instId":"BTC-USDT-SWAP"})
                get.assert_called_once()
                sleep.assert_not_called()

    def test_only_explicit_transient_symbol_faults_are_recoverable(self):
        self.assertTrue(transient_market_errors([
            {"symbol":"XPL-USDT-SWAP","reason":"OKX TRANSIENT 50026: public GET retry budget exhausted; no order"}]))
        for errors in ([],[{"symbol":"XPL-USDT-SWAP","reason":"Insufficient candle history"}],
                       [{"symbol":"XPL-USDT-SWAP","reason":"OKX TRANSIENT 50026"},
                        {"symbol":"BTC-USDT-SWAP","reason":"corrupt"}],
                       [{"symbol":"BTC-USDT-SWAP","reason":"OKX 51000: bad args"}]):
            with self.subTest(errors=errors):
                self.assertFalse(transient_market_errors(errors))


if __name__ == "__main__":
    unittest.main()
