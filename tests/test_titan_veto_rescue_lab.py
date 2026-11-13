import unittest
from datetime import datetime, timedelta, timezone
from trading.shadow_observatory import BAR_MS, sha
from trading.titan_veto_rescue_lab import AGENTS, inspect

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

def example(i=0, *, policy="a", symbol=None, decision="WAIT", core="LONG",
            vetoes=None, hard=False, warnings=None, stop=98.0, target=108.0,
            movement=2.0, hours=4):
    timestamp = BASE + timedelta(hours=hours*i, minutes=1)
    start = int((timestamp-timedelta(minutes=1)).timestamp()*1000) + BAR_MS
    symbol = symbol or f"COIN{i}-USDT-SWAP"
    row = {"symbol":symbol, "decision":decision,"core_before_filters":core,
           "stop":stop,"target":target,
           "advanced_veto_reasons": ["no_independent_quant_confirmation"] if vetoes is None else vetoes,
           "derivatives_data_warnings":[] if warnings is None else warnings,
           "role_votes":[{"agent":"01_liquidity_sentinel","veto":hard}],
           "source_price":100.0}
    snap={"schema":"quant2037-shadow-v1", "mode":"PUBLIC_ONLY_NO_TRADES",
          "timestamp_utc":timestamp.isoformat().replace("+00:00","Z"),
          "decision_policy_sha256":policy, "decisions":[row],"errors":[]}
    snap["snapshot_sha256"]=sha(snap)
    bars=[{"ts":start+j*BAR_MS,"open":100.0,"high":102.8 if movement>0 else 100.5,
           "low":99.0 if movement>0 else 97.0,"close":100.0+movement}
          for j in range(4)]
    return snap, symbol, bars

def bundle(n, **kwargs):
    snaps=[]; histories={}
    for i in range(n):
        snap,sym,bars=example(i,**kwargs)
        snaps.append(snap)
        histories[sym]=bars
    return snaps,histories

class VetoRescueTests(unittest.TestCase):
    def test_no_evidence_is_not_a_license_to_trade(self):
        x=inspect([],{})
        self.assertEqual(set(x["agents"]),set(AGENTS))
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)
        self.assertFalse(x["agents"]["deployment_guardian"]["live_trading_allowed"])
        self.assertFalse(x["agents"]["deployment_guardian"]["force_entry_allowed"])
        self.assertEqual(x["actual_orders_placed"],0)

    def test_directional_wait_is_reconstructed_with_stop_and_cost(self):
        s,sym,b=example()
        x=inspect([s],{sym:b})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],1)
        self.assertEqual(x["agents"]["deployment_guardian"]["status"],"INSUFFICIENT_PROSPECTIVE_EVIDENCE")

    def test_core_wait_not_a_direction(self):
        s,sym,b=example(core="WAIT")
        x=inspect([s],{sym:b})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)
        self.assertEqual(x["agents"]["hard_veto_isolation"]["exclusions"]["core_without_direction_excluded"],1)

    def test_original_nonwait_not_counted_as_missed(self):
        s,sym,b=example(decision="LONG")
        x=inspect([s],{sym:b})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)

    def test_hard_veto_and_derivatives_problem_never_resurrected(self):
        a,sa,ba=example(0,hard=True)
        b,sb,bb=example(1,warnings=["missing_funding"])
        x=inspect([a,b],{sa:ba,sb:bb})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)
        excluded=x["agents"]["hard_veto_isolation"]["exclusions"]
        self.assertEqual(excluded["hard_agent_veto_excluded"],1)
        self.assertEqual(excluded["missing_derivatives_excluded"],1)

    def test_no_protection_no_counterfactual(self):
        s,sym,b=example(stop=None)
        x=inspect([s],{sym:b})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)
        self.assertEqual(x["agents"]["hard_veto_isolation"]["exclusions"]["missing_or_invalid_horizon_excluded"],1)

    def test_missing_future_candles_is_not_win(self):
        s,sym,b=example()
        x=inspect([s],{sym:b[:2]})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],0)

    def test_missing_history_fails_closed(self):
        s,sym,b=example()
        with self.assertRaisesRegex(ValueError,"Missing actual public candle"):
            inspect([s],{})

    def test_correlated_same_asset_in_same_bucket_excluded(self):
        a,sa,ba=example(0,symbol="ONE-USDT-SWAP")
        b,sb,bb=example(0,symbol="ONE-USDT-SWAP")
        b["timestamp_utc"]=(BASE+timedelta(minutes=2)).isoformat().replace("+00:00","Z")
        b["snapshot_sha256"]=sha({k:v for k,v in b.items() if k!="snapshot_sha256"})
        x=inspect([a,b],{sa:ba})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],1)

    def test_policy_version_firewall(self):
        a,sa,ba=example(0,policy="old")
        b,sb,bb=example(1,policy="new")
        x=inspect([a,b],{sa:ba,sb:bb})
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],1)
        self.assertEqual(x["agents"]["hard_veto_isolation"]["exclusions"]["prior_policy_excluded"],1)

    def test_always_positive_history_still_only_human_review(self):
        snapshots,histories=bundle(150,movement=2)
        x=inspect(snapshots,histories)
        self.assertEqual(x["potential_extra_trades_hypothetical_only"],150)
        self.assertEqual(x["agents"]["deployment_guardian"]["status"],
                         "HUMAN_REVIEW_ELIGIBLE_NOT_AUTOMATIC_APPROVAL")
        self.assertFalse(x["agents"]["deployment_guardian"]["live_trading_allowed"])
        self.assertGreater(x["agents"]["uncertainty_tail_judge"]["holdout_stressed_lower5_mean_pct"],0)

    def test_negative_results_do_not_relax_veto(self):
        snapshots,histories=bundle(150,movement=-2)
        x=inspect(snapshots,histories)
        self.assertEqual(x["agents"]["deployment_guardian"]["status"],
                         "NEGATIVE_OR_UNCERTAIN_EDGE_NO_APPROVAL")

    def test_less_than_fourteen_days_insufficient(self):
        snapshots,histories=bundle(120,hours=1)
        x=inspect(snapshots,histories)
        self.assertNotEqual(x["agents"]["deployment_guardian"]["status"],
                            "HUMAN_REVIEW_ELIGIBLE_NOT_AUTOMATIC_APPROVAL")
        self.assertEqual(x["agents"]["deployment_guardian"]["status"],
                         "INSUFFICIENT_PROSPECTIVE_EVIDENCE")

    def test_tampered_snapshot_rejected(self):
        s,sym,b=example()
        s["decisions"][0]["stop"]=96.0
        with self.assertRaises(ValueError):
            inspect([s],{sym:b})

    def test_non_predeclared_horizon_rejected(self):
        with self.assertRaises(ValueError):
            inspect([],{},horizon=1)

    def test_never_load_secrets_or_write_orders(self):
        import inspect as inspection
        import trading.titan_veto_rescue_lab as m
        code=inspection.getsource(m)
        for forbidden in ("OKX_API_KEY","OKX_SECRET_KEY","/api/v5/trade/order",
                          "requests.post(","subprocess.run(","place_order("):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":
    unittest.main()
