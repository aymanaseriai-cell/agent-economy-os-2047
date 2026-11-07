import unittest
from trading.okx_signal_lab import ema, rsi, atr, parse_candles, pick_liquid, analyze


class SignalLabTests(unittest.TestCase):
    def test_constant_ema(self):
        self.assertEqual(ema([100.0] * 30, 21), 100.0)

    def test_flat_rsi(self):
        self.assertEqual(rsi([42.0] * 20), 50.0)

    def test_rsi_uptrend(self):
        self.assertEqual(rsi([float(i) for i in range(40)]), 100.0)

    def test_pick_liquid(self):
        rows = [
            {"instId": "BTC-USDT-SWAP", "last": "100", "volCcy24h": "500000",
             "bidPx": "100", "askPx": "100.1"},
            {"instId": "BTC-USD-SWAP", "last": "100", "volCcy24h": "8000000",
             "bidPx": "100", "askPx": "100.1"},
            {"instId": "BAD-USDT-SWAP", "last": "1", "volCcy24h": "1000000",
             "bidPx": "1", "askPx": "1.01"}
        ]
        self.assertEqual([x["symbol"] for x in pick_liquid(rows, 10)], ["BTC-USDT-SWAP"])

    def test_ignore_unclosed_candle(self):
        rows = [
            ["2", "2", "3", "1", "2", "1", "1", "1", "0"],
            ["1", "1", "2", "0.9", "1.5", "1", "1", "1", "1"]
        ]
        result = parse_candles(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ts"], 1)

    def test_wait_on_flat_series(self):
        bars = [{"ts": i, "open": 100, "high": 101, "low": 99, "close": 100}
                for i in range(40)]
        result = analyze({"symbol": "BTC-USDT-SWAP"}, bars)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(atr(bars), 2.0)


if __name__ == "__main__":
    unittest.main()
