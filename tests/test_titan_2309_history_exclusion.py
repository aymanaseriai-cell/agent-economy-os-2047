"""Read-only regression tests for TITAN 23:09 short-history market exclusions."""
import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from trading import six_agent_council as council
from trading.okx_live_executor import ExecutionBlocked, read_report


class HistoryExclusionTests(unittest.TestCase):
    READY = {"symbol": "BTC-USDT-SWAP", "signal": "WAIT",
             "ordinal_buy_points": 0, "ordinal_sell_points": 0,
             "agents": [], "advanced_veto_reasons": [], "omega_veto_reasons": [],
             "core_signal_before_advanced": "WAIT", "execution": "DISABLED"}

    def generate(self, *, results=None, errors=None):
        results = [dict(self.READY)] if results is None else results
        errors = ([{"symbol": "JCT-USDT-SWAP",
                    "reason": council.INCOMPLETE_HISTORY_REASON}]
                  if errors is None else errors)
        symbols = list(dict.fromkeys(
            ["BTC-USDT-SWAP", "JCT-USDT-SWAP"] + [e["symbol"] for e in errors]))
        pool = [{"symbol": x} for x in symbols]
        tickers = [{"instId": x} for x in symbols]
        def public_get(path, _params):
            return tickers if path == "/api/v5/market/tickers" else []
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "signals.json"
            with (patch.object(council, "okx_get", side_effect=public_get),
                  patch.object(council, "eligible_20x_instruments",
                               return_value=set(symbols)),
                  patch.object(council, "select_markets", return_value=pool),
                  patch.object(council, "analyze_market_batch",
                               return_value=(results, errors)),
                  patch("sys.argv", ["council", "--all-eligible", "--out", str(path)]),
                  redirect_stdout(io.StringIO()) as capture):
                code = council.main()
            report = json.loads(path.read_text())
            output = capture.getvalue()
        return code, report, output

    def test_incomplete_history_excludes_only_unready_symbol(self):
        code, report, log = self.generate()
        self.assertEqual(code, 0)
        self.assertTrue(report["market_scan_complete"])
        self.assertEqual(report["markets_preselected_for_deep_analysis"], 2)
        self.assertEqual(report["markets_selected"], 1)
        self.assertEqual(report["markets_analyzed"], 1)
        self.assertEqual(report["orders_placed"], 0)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["markets_skipped_insufficient_history"],
                         [{"symbol": "JCT-USDT-SWAP",
                           "reason": council.INCOMPLETE_HISTORY_REASON}])
        self.assertIn("DATA SKIP JCT-USDT-SWAP", log)
        self.assertNotIn("DATA ERROR JCT-USDT-SWAP", log)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text(json.dumps(report))
            checked = read_report(path, now_ms=int(time.time()*1000))
        self.assertTrue(checked["market_scan_complete"])

    def test_unrelated_data_error_remains_fatal(self):
        code, report, _ = self.generate(errors=[
            {"symbol": "JCT-USDT-SWAP", "reason": "Orderbook unavailable"}])
        self.assertEqual(code, 2)
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["markets_skipped_insufficient_history"], [])

    def test_transient_error_with_history_skip_is_no_order_retry(self):
        code, report, output = self.generate(errors=[
            {"symbol": "JCT-USDT-SWAP", "reason": council.INCOMPLETE_HISTORY_REASON},
            {"symbol": "XPL-USDT-SWAP",
             "reason": "OKX TRANSIENT 50026: public GET retry budget exhausted; no order"}])
        self.assertEqual(code, council.RECOVERABLE_SCAN_EXIT)
        self.assertIn("TITAN PUBLIC GET TRANSIENT_NO_ORDERS", output)
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["orders_placed"], 0)

    def test_all_unready_symbols_never_create_tradeable_scan(self):
        code, report, _ = self.generate(
            results=[], errors=[
                {"symbol": "BTC-USDT-SWAP", "reason": council.INCOMPLETE_HISTORY_REASON},
                {"symbol": "JCT-USDT-SWAP", "reason": council.INCOMPLETE_HISTORY_REASON}])
        self.assertEqual(code, 2)
        self.assertEqual(report["markets_selected"], 0)
        self.assertEqual(len(report["markets_skipped_insufficient_history"]), 2)

    def test_actual_short_candles_raise_exact_reason(self):
        with patch.object(council, "grab", return_value=[]):
            with self.assertRaisesRegex(ValueError, council.INCOMPLETE_HISTORY_REASON):
                council.analyze_market({"symbol": "JCT-USDT-SWAP"})

    def test_executor_rejects_forged_skips_and_mismatched_counts(self):
        _, good, _ = self.generate()
        variants = []
        for mutate in ("bad_count", "wrong_reason", "overlap", "duplicate", "bad_list"):
            v = copy.deepcopy(good)
            skips = v["markets_skipped_insufficient_history"]
            if mutate == "bad_count":
                v["markets_preselected_for_deep_analysis"] = 1
            elif mutate == "wrong_reason":
                skips[0]["reason"] = "Orderbook unavailable"
            elif mutate == "overlap":
                skips[0]["symbol"] = "BTC-USDT-SWAP"
            elif mutate == "duplicate":
                skips.append(dict(skips[0]))
                v["markets_preselected_for_deep_analysis"] = 3
            else:
                v["markets_skipped_insufficient_history"] = "not a list"
            variants.append(v)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            for bad in variants:
                path.write_text(json.dumps(bad))
                with self.subTest(bad=bad):
                    with self.assertRaises(ExecutionBlocked):
                        read_report(path, now_ms=int(time.time()*1000))


if __name__ == "__main__":
    unittest.main()
