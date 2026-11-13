import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import patch

from trading.okx_live_executor import ExecutionBlocked
from trading.okx_risk_watchdog import (
    ReadOnlyOKX, assess, main, STATUS_FLAT, STATUS_HEALTHY, STATUS_RISK,
    STATUS_UNKNOWN, STATUS_CONNECTION,
)


class FakeClient:
    def __init__(self, *, positions=None, algos=None, equity="1000", free="800"):
        self.positions = [] if positions is None else positions
        self.algos = [] if algos is None else algos
        self.equity, self.free = equity, free

    def request(self, method, path, *, params=None, body=None, auth=True):
        if method != "GET":
            raise AssertionError("Read-only test submitted a write")
        if path.endswith("/config"):
            return [{"posMode": "net_mode"}]
        if path.endswith("/positions"):
            return self.positions
        if path.endswith("/orders-pending"):
            return []
        if path.endswith("/orders-algo-pending"):
            return self.algos if params["ordType"] == "oco" else []
        if path.endswith("/balance"):
            return [{"totalEq": self.equity,
                     "details": [{"ccy": "USDT", "availEq": self.free}]}]
        raise AssertionError("Unknown endpoint " + path)


def position(*, notional="100", leverage="20"):
    return {"instId": "BTC-USDT-SWAP", "pos": "1", "mgnMode": "isolated",
            "notionalUsd": notional, "lever": leverage, "markPx": "100"}


def protective(*, stop="99"):
    return {"instId": "BTC-USDT-SWAP", "slTriggerPx": stop,
            "tpTriggerPx": "105"}


class ReadOnlyWatchdogTests(unittest.TestCase):
    def test_empty_portfolio_is_success(self):
        self.assertEqual(assess(FakeClient()), (STATUS_FLAT, 0))

    def test_protected_position_is_success(self):
        self.assertEqual(assess(FakeClient(positions=[position()],
                                           algos=[protective()])), (STATUS_HEALTHY, 0))

    def test_over_budget_is_error_not_success(self):
        self.assertEqual(assess(FakeClient(positions=[position(notional="2000")],
                                           algos=[protective(stop="96")])), (STATUS_RISK, 2))

    def test_missing_tp_sl_is_never_healthy(self):
        self.assertEqual(assess(FakeClient(positions=[position()])), (STATUS_UNKNOWN, 3))

    def test_missing_actual_leverage_is_unverifiable(self):
        p = position()
        p.pop("lever")
        self.assertEqual(assess(FakeClient(positions=[p], algos=[protective()])),
                         (STATUS_UNKNOWN, 3))

    def test_transport_denies_post_and_unknown_reads(self):
        calls = []
        def transport(req):
            calls.append(req["method"])
            return {"code": "0", "data": []}
        c = ReadOnlyOKX({"OKX_API_KEY": "unused", "OKX_SECRET_KEY": "unused",
                         "OKX_PASSPHRASE": "unused"}, transport=transport)
        self.assertEqual(c.request("GET", "/api/v5/account/config"), [])
        with self.assertRaises(ExecutionBlocked):
            c.request("POST", "/api/v5/trade/order", body={"sz": "1"})
        with self.assertRaises(ExecutionBlocked):
            c.request("POST", "/api/v5/account/set-leverage", body={"lever": "100"})
        with self.assertRaises(ExecutionBlocked):
            c.request("GET", "/api/v5/trade/order")
        self.assertEqual(calls, ["GET"])

    def test_missing_credentials_exit_cleanly_without_network(self):
        f = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(f):
            code = main()
        self.assertEqual(code, 3)
        self.assertIn(STATUS_CONNECTION, f.getvalue())


if __name__ == "__main__":
    unittest.main()
