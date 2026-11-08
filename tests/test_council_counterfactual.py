import json
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from trading.council_counterfactual import (
    BAR_MS, HORIZON, geometric_flip, placebo_outcomes, evaluate, summarize_groups
)
from trading.council_forward_audit import utc_ms, audit_signal


def data():
    root=Path(__file__).resolve().parent.parent/"reports"
    provenance=json.loads((root/"actual_council_signals_20261108.json").read_text())
    histories={s:json.loads((root/(s+".outcome_candles_20261108.json")).read_text())
               for s in sorted({x["symbol"] for x in provenance["signals"]})}
    return provenance,histories


class CouncilAdversarialTests(unittest.TestCase):
    def test_actual_event_vs_symmetric_opposite_geometry(self):
        provenance,histories=data()
        signal=provenance["signals"][0]
        bars=histories[signal["symbol"]]
        flipped=geometric_flip(signal,bars)
        self.assertEqual(flipped["side"],"LONG")
        start=((utc_ms(signal["published_utc"])+BAR_MS-1)//BAR_MS)*BAR_MS
        price=next(b["open"] for b in bars if b["ts"]==start)
        self.assertAlmostEqual(abs(flipped["stop"]-price)/price,
                               abs(signal["stop"]-price)/price,places=12)
        self.assertAlmostEqual(abs(flipped["target"]-price)/price,
                               abs(signal["target"]-price)/price,places=12)

    def test_opposite_trade_does_not_use_original_short_stops(self):
        provenance,histories=data()
        s=next(x for x in provenance["signals"] if x["side"]=="SHORT")
        f=geometric_flip(s,histories[s["symbol"]])
        self.assertLess(f["stop"],f["target"])
        self.assertLess(f["stop"],s["stop"])

    def test_each_placebo_1h_window_completed_before_publication(self):
        provenance,histories=data()
        source=provenance["signals"][0]
        seen=[]
        original=audit_signal
        def capture(s,bars,horizon,**kwargs):
            x=original(s,bars,horizon,**kwargs)
            seen.append(x)
            return x
        with patch("trading.council_counterfactual.audit_signal",side_effect=capture):
            values=placebo_outcomes(source,histories[source["symbol"]])
        self.assertEqual(len(values),68)
        posted=utc_ms(source["published_utc"])
        self.assertEqual(len(seen),len(values))
        self.assertTrue(all(x["exit_end_ts"]<=posted for x in seen))

    def test_all_placebos_are_prior_to_and_exclude_signal_event(self):
        provenance,histories=data()
        for source in provenance["signals"]:
            values=placebo_outcomes(source,histories[source["symbol"]])
            self.assertGreaterEqual(len(values),10)
            self.assertTrue(all(isinstance(x,float) for x in values))

    def test_fee_stress_makes_all_six_worse(self):
        provenance,histories=data()
        report=evaluate(provenance,histories)
        self.assertEqual(len(report["rows"]),6)
        self.assertTrue(all(x["net_stress_pct"]<x["net_base_pct"] for x in report["rows"]))

    def test_frictionless_better_than_normal_on_all_six(self):
        provenance,histories=data()
        result=evaluate(provenance,histories)
        self.assertTrue(all(x["frictionless_pct"]>x["net_base_pct"] for x in result["rows"]))

    def test_exact_frozen_aggregate(self):
        provenance,histories=data()
        result=evaluate(provenance,histories)
        s=result["summary"]
        self.assertEqual((s["signals"],s["underlying_instruments"]), (6,3))
        self.assertEqual((s["positive_baseline_count"],s["negative_baseline_count"]), (0,6))
        self.assertAlmostEqual(s["baseline_mean_pct"],-.62312,places=5)
        self.assertAlmostEqual(s["frictionless_mean_pct"],-.46161,places=5)
        self.assertAlmostEqual(s["stressed_mean_pct"],-.82503,places=5)
        self.assertAlmostEqual(s["reverse_direction_mean_pct"],.33618,places=5)

    def test_independent_assets_not_six_trades(self):
        provenance,histories=data()
        groups=evaluate(provenance,histories)["summary"]["asset_cluster_results"]
        self.assertEqual({k:v["candidate_count"] for k,v in groups.items()},
                         {"PEPE-USDT-SWAP":3,"UNI-USDT-SWAP":1,"ZEC-USDT-SWAP":2})
        self.assertTrue(all(v["all_negative"] for v in groups.values()))

    def test_not_a_claim_of_nvidia_approved_trades(self):
        provenance,histories=data()
        result=evaluate(provenance,histories)
        self.assertTrue(result["summary"]["no_verified_nvidia_approvals"])
        self.assertNotIn("orders",result["summary"])
        self.assertEqual(result["assumptions"]["outcome_minutes"],60)

    def test_rejects_missing_history(self):
        provenance,histories=data()
        missing={key:val for key,val in histories.items() if key!="PEPE-USDT-SWAP"}
        with self.assertRaises(KeyError):
            evaluate(provenance,missing)

    def test_counterfactual_does_not_look_ahead(self):
        provenance,histories=data()
        row=provenance["signals"][0]
        original=histories[row["symbol"]]
        flip_before=geometric_flip(row,original)
        copy=[dict(x) for x in original]
        copy[-1]["high"]*=1.1
        # Last observation is long after original signal; cannot alter entry
        flip_after=geometric_flip(row,copy)
        self.assertEqual(flip_before,flip_after)

if __name__=="__main__":
    unittest.main()
