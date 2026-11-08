import json
import unittest
from pathlib import Path

from trading.council_forward_audit import (
    BAR_MS,audit_signal,build_audit,validate_bars,utc_ms
)


def bars_at(start=1_800_000_000_000, count=20, price=100.0):
    # Align start to candle open; 20 consecutive confirmed bars.
    start=(start//BAR_MS)*BAR_MS
    return [{"ts":start+i*BAR_MS,"open":price,"high":price+1,
             "low":price-1,"close":price} for i in range(count)]


def sig(bars,side="LONG", stop=98, target=104, interval=1):
    ts=bars[interval]["ts"]-60_000
    from datetime import datetime,timezone
    return {"published_utc":datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),
            "symbol":"TEST-USDT-SWAP","side":side,"stop":stop,"target":target,
            "run_id":12,"source_url":"https://github.com/test"}


class TestOriginalCouncilForward(unittest.TestCase):
    def test_entry_is_after_report_publication(self):
        b=bars_at()
        s=sig(b)
        x=audit_signal(s,b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["status"],"matured")
        self.assertEqual(x["entry_ts"],b[1]["ts"])
        self.assertGreater(x["entry_ts"],utc_ms(s["published_utc"]))

    def test_no_backdating_to_previous_candle(self):
        b=bars_at()
        s=sig(b,interval=2)
        b[1]={"ts":b[1]["ts"],"open":1,"high":500,"low":.1,"close":100}
        x=audit_signal(s,b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["entry_ts"],b[2]["ts"])
        self.assertEqual(x["outcome"],"horizon_close")

    def test_both_stop_and_target_in_one_candle_stop_first(self):
        b=bars_at()
        b[1]={"ts":b[1]["ts"],"open":100,"high":106,"low":97,"close":100}
        x=audit_signal(sig(b),b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["outcome"],"stop")
        self.assertLess(x["net_unlevered_notional_pct"],0)

    def test_stop_gap_worse_than_stop_price(self):
        b=bars_at()
        b[1]={"ts":b[1]["ts"],"open":95,"high":96,"low":94,"close":95}
        x=audit_signal(sig(b),b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["status"],"invalid_entry") # original stop invalid at entry
        # After entry, a gap below stop is filled at the worse gap open.
        b[1]={"ts":b[1]["ts"],"open":100,"high":100.5,"low":99,"close":100}
        b[2]={"ts":b[2]["ts"],"open":90,"high":92,"low":89,"close":90}
        x=audit_signal(sig(b),b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["outcome"],"stop_gap")
        self.assertAlmostEqual(x["modeled_exit"],90)

    def test_short_stop_when_price_up(self):
        b=bars_at()
        b[1]={"ts":b[1]["ts"],"open":100,"high":106,"low":99,"close":100}
        x=audit_signal(sig(b,"SHORT",102,95),b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["outcome"],"stop")

    def test_target_when_long_reaches_price(self):
        b=bars_at()
        b[1]={"ts":b[1]["ts"],"open":100,"high":105,"low":99,"close":104}
        x=audit_signal(sig(b),b,4,fee=0,slip=0,funding=0)
        self.assertEqual(x["outcome"],"target")
        self.assertGreater(x["net_unlevered_notional_pct"],0)

    def test_no_result_until_four_bars_complete(self):
        b=bars_at(count=4)
        x=audit_signal(sig(b,interval=2),b,4)
        self.assertEqual(x["status"],"not_matured")

    def test_fee_and_slip_reduce_returns(self):
        b=bars_at()
        s=sig(b)
        a=audit_signal(s,b,4,fee=0,slip=0,funding=0)
        z=audit_signal(s,b,4)
        self.assertLess(z["net_unlevered_notional_pct"],a["net_unlevered_notional_pct"])

    def test_missing_bar_rejected(self):
        b=bars_at()
        del b[4]
        with self.assertRaisesRegex(ValueError,"Missing candles"):
            validate_bars(b)

    def test_invalid_candle_rejected(self):
        b=bars_at()
        b[2]["high"]=90
        with self.assertRaisesRegex(ValueError,"Invalid candle"):
            validate_bars(b)

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            utc_ms("2026-11-08T00:00:00")

    def test_locked_original_report_replay_is_negative(self):
        root=Path(__file__).resolve().parent.parent/"reports"
        if not (root/"actual_council_signals_20261108.json").exists():
            self.skipTest("Frozen sample not bundled")
        p=json.loads((root/"actual_council_signals_20261108.json").read_text())
        data={x["symbol"]:json.loads((root/(x["symbol"]+".outcome_candles_20261108.json")).read_text())
              for x in p["signals"]}
        result=build_audit(p,data)
        h=result["summary"]["outcomes"]["60"]
        self.assertEqual((h["matured_count"],h["positive_count"],h["negative_count"]),(6,0,6))
        self.assertAlmostEqual(h["average_net_unlevered_pct"],-.62312,places=4)
        self.assertEqual(result["summary"]["unique_instruments"],
                         ["PEPE-USDT-SWAP","UNI-USDT-SWAP","ZEC-USDT-SWAP"])
if __name__=="__main__":
    unittest.main()
