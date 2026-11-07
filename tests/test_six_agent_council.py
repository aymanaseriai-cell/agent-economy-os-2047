import unittest
from trading.six_agent_council import (
    candles, select_markets, volume_profile, auction_cartographer,
    tape_detective, derivatives_intelligence, structure_navigator,
    risk_marshal, liquidity_sentinel, summarize_agents,
)


def make_bars(n=200, price=100.0, increment=0.0):
    result = []
    for k in range(n):
        close = price + k * increment
        result.append({"ts": 900000 * k, "open": close, "high": close * 1.003,
                       "low": close * .997, "close": close, "quote_vol": 50000.0})
    return result


class TestCouncil(unittest.TestCase):
    def setUp(self):
        self.market = {"symbol": "BTC-USDT-SWAP", "last": 100.0, "bid": 99.99,
                       "ask": 100.01, "spread_bp": 2.0,
                       "turnover_usdt_est": 50_000_000}
        self.book = {"bids": [["99.99", "120", "0", "1"] for _ in range(20)],
                     "asks": [["100.01", "100", "0", "1"] for _ in range(20)],
                     "ts": "0"}

    def test_only_crypto_usdt_swaps(self):
        rows = [
            {"instId": "BTC-USDT-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
            {"instId": "SNDK-USDT-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
            {"instId": "BTC-USD-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
        ]
        self.assertEqual([x["symbol"] for x in select_markets(rows, 10)], ["BTC-USDT-SWAP"])

    def test_candles_exclude_unfinished(self):
        rows = [["0", "1", "2", "0.5", "1.5", "1", "1", "100", "1"],
                ["900000", "1", "2", "0.5", "1.5", "1", "1", "100", "0"]]
        self.assertEqual(len(candles(rows)), 1)

    def test_value_area_well_ordered(self):
        profile = volume_profile(make_bars())
        self.assertLessEqual(profile["VAL_approx"], profile["POC_approx"])
        self.assertLessEqual(profile["POC_approx"], profile["VAH_approx"])
        self.assertEqual(profile["profile_lookback_bars"], 192)

    def test_profile_needs_history(self):
        with self.assertRaises(ValueError):
            volume_profile(make_bars(20))

    def test_auction_neutral_on_flat(self):
        x = auction_cartographer(make_bars())
        self.assertEqual(x["vote"], 0)

    def test_tape_agreement(self):
        trades = [{"side": "buy", "sz": "20"} for _ in range(60)] + [{"side": "sell", "sz": "2"} for _ in range(20)]
        x = tape_detective(self.book, trades)
        self.assertEqual(x["vote"], 1)

    def test_funding_crowding(self):
        x = derivatives_intelligence({"fundingRate": ".0009"}, {"oiUsd": "1000000"},
                                     {"markPx": "100.2"}, 100)
        self.assertEqual(x["vote"], -1)

    def test_liquidity_sentinel_stale_veto(self):
        self.assertTrue(liquidity_sentinel(self.market, self.book)["veto"])

    def test_risk_veto_without_consensus(self):
        x = risk_marshal(self.market, make_bars(), 0, {})
        self.assertTrue(x["veto"])

    def test_structure_uptrend(self):
        hour = make_bars(100, 100, 0.4)
        four = make_bars(30, 100, 0.8)
        self.assertEqual(structure_navigator(hour, four)["vote"], 1)

    def test_ensemble_six_agents_and_no_order(self):
        self.book["ts"] = str(int(__import__("time").time() * 1000))
        trades = [{"side": "buy", "sz": "20"} for _ in range(100)]
        report = summarize_agents(self.market, make_bars(200), make_bars(80),
                                  make_bars(50), self.book, trades, {}, {}, {})
        self.assertEqual(len(report["agents"]), 6)
        self.assertEqual(report["order_count"], 0)
        self.assertEqual(report["execution"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
