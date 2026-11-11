import unittest
from trading.six_agent_council import (
    candles, select_markets, eligible_20x_instruments, volume_profile, auction_cartographer,
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

    @staticmethod
    def instruments_for(rows, *, lever="20"):
        return [{"instId":r["instId"],"state":"live",
                 "ctType":"linear","settleCcy":"USDT","instCategory":"1",
                 "ctValCcy":r["instId"].split("-")[0],
                 "ruleType":"normal","lever":lever} for r in rows]

    def test_only_verified_live_twenty_x_usdt_swaps(self):
        rows = [
            {"instId": "BTC-USDT-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
            {"instId": "SNDK-USDT-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
            {"instId": "BTC-USD-SWAP", "last": "100", "bidPx": "99.99", "askPx": "100.01", "volCcy24h": "500000"},
        ]
        instruments=self.instruments_for(rows)
        instruments[1]["lever"]="10"
        eligible=eligible_20x_instruments(instruments)
        self.assertEqual([x["symbol"] for x in select_markets(rows, 10, eligible=eligible)],
                         ["BTC-USDT-SWAP"])
        self.assertEqual(select_markets(rows,10),[])  # Missing metadata never falls back.

    def test_new_20x_coin_enters_without_any_fixed_allowlist(self):
        rows = [{"instId":"NEW2026-USDT-SWAP","last":"2","bidPx":"1.999",
                 "askPx":"2.001","volCcy24h":"15000000"}]
        eligible=eligible_20x_instruments(self.instruments_for(rows))
        self.assertEqual([x["symbol"] for x in select_markets(rows,12,eligible=eligible)],
                         ["NEW2026-USDT-SWAP"])

    def test_20x_universe_rejects_suspended_premarket_cross_and_underlevered(self):
        rows=[{"instId":s+"-USDT-SWAP","last":"100","bidPx":"99.99",
               "askPx":"100.01","volCcy24h":"500000"}
              for s in ("BTC","ETH","SOL","XRP","ADA")]
        inst=self.instruments_for(rows)
        inst[0]["state"]="suspend"
        inst[1]["lever"]="19"
        inst[2]["ruleType"]="pre_market"
        inst[3]["ctType"]="inverse"
        good=eligible_20x_instruments(inst)
        self.assertEqual(good,frozenset({"ADA-USDT-SWAP"}))
        self.assertEqual(select_markets(rows,12,eligible=good)[0]["symbol"],"ADA-USDT-SWAP")


    def test_equity_forex_metals_bonds_and_unknown_category_never_enter_crypto_scan(self):
        rows=[{"instId":asset+"-USDT-SWAP","last":"100",
               "bidPx":"99.99","askPx":"100.01","volCcy24h":"500000"}
              for asset in ("BTC","NVDA","SOXL","XAU","EURUSDT","US30Y","NEWUNKNOWN")]
        instruments=self.instruments_for(rows)
        for inst,category in zip(instruments,("1","3","3","4","5","6","")):
            inst["instCategory"]=category
            inst["lever"]="50"  # high leverage does NOT override asset class
        eligible=eligible_20x_instruments(instruments)
        self.assertEqual(eligible,frozenset({"BTC-USDT-SWAP"}))
        self.assertEqual([x["symbol"] for x in select_markets(rows,12,eligible=eligible)],
                         ["BTC-USDT-SWAP"])


    def test_twenty_symbol_public_batch_has_no_duplicate_and_no_weak_liquidity(self):
        names=("BTC","ETH","SOL","XRP","DOGE","ADA","LINK","AVAX",
               "DOT","LTC","TRX","BCH","ETC","ATOM","UNI","SUI",
               "NEAR","TAO","FIL","AAVE","ZEC")
        rows=[{"instId":n+"-USDT-SWAP","last":"100",
               "bidPx":"99.99","askPx":"100.01",
               "volCcy24h":str(500000-i*5000)} for i,n in enumerate(names)]
        eligibility=eligible_20x_instruments(self.instruments_for(rows))
        selected=select_markets(rows,20,eligible=eligibility,rotation_epoch=1)
        self.assertEqual(len(selected),20)
        self.assertEqual(len({x["symbol"] for x in selected}),20)
        self.assertTrue(all(x["turnover_usdt_est"]>=15000000 for x in selected))

    def test_rotation_diversifies_liquid_universe_without_relaxing_filters(self):
        symbols = ["BTC","ETH","SOL","XRP","DOGE","ADA","LINK","AVAX",
                   "DOT","LTC","TRX","BCH","ETC","ATOM","UNI","SUI"]
        rows = [{"instId":f"{symbol}-USDT-SWAP",
                 "last":"100","bidPx":"99.99","askPx":"100.01",
                 "volCcy24h":str(500000-i*10000)}
                for i,symbol in enumerate(symbols)]
        eligible=eligible_20x_instruments(self.instruments_for(rows))
        top = select_markets(rows,12,eligible=eligible)
        next_page = select_markets(rows,12,rotation_epoch=1,eligible=eligible)
        self.assertEqual(len(top),12)
        self.assertEqual(len(next_page),12)
        self.assertNotEqual([x["symbol"] for x in top],
                            [x["symbol"] for x in next_page])
        self.assertIn("UNI-USDT-SWAP",[x["symbol"] for x in next_page])
        self.assertEqual({x["symbol"] for x in next_page},
                         {x["symbol"] for x in select_markets(rows,12,rotation_epoch=1,eligible=eligible)})
        for market in next_page:
            self.assertGreaterEqual(market["turnover_usdt_est"],15_000_000)
            self.assertLessEqual(market["spread_bp"],25)

    def test_rotation_cannot_promote_illiquid_coin(self):
        data = [{"instId":f"{x}-USDT-SWAP","last":"100",
                 "bidPx":"99.99","askPx":"100.01","volCcy24h":"500000"}
                for x in ["BTC","ETH","SOL","XRP"]]
        data.append({"instId":"ADA-USDT-SWAP","last":"100",
                     "bidPx":"99.99","askPx":"100.01","volCcy24h":"1000"})
        eligible=eligible_20x_instruments(self.instruments_for(data))
        self.assertNotIn("ADA-USDT-SWAP",
                         [x["symbol"] for x in select_markets(data,3,rotation_epoch=200,eligible=eligible)])

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
