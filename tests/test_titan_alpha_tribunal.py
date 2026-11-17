"""Exact counterfactual no-order tests for adversarial goal-vs-loss tribunal."""
import copy
import math
import unittest

from trading.edge_lab import BAR_MS
from trading.titan_alpha_tribunal import (
    STRATEGIES, INITIAL_EQUITY, TARGET_EQUITY, SEVERE_LOSS_EQUITY,
    single_position_episodes, daily_blocks, run_path, block_bootstrap,
    train_only_choice,
)


class TitanAdversarialTribunalTests(unittest.TestCase):
    def test_absorbing_goal_before_ruin(self):
        out=run_path([[0.3, -0.7]], notional_to_equity=4)
        self.assertEqual(out["state"],"GOAL_FIRST")
        self.assertEqual(out["trades"],1)

    def test_absorbing_severe_loss_before_goal(self):
        out=run_path([[-0.3,0.8]],notional_to_equity=4)
        self.assertEqual(out["state"],"SEVERE_LOSS_FIRST")
        self.assertEqual(out["trades"],1)

    def test_do_not_invent_double_at_zero_returns(self):
        out=run_path([[0.0,0.0],[0.0]],notional_to_equity=4)
        self.assertEqual(out["state"],"NEITHER")
        self.assertEqual(out["equity"],INITIAL_EQUITY)

    def test_cost_adversary_cannot_raise_ending_equity(self):
        days=[[.02,.01],[-.003],[.005]]
        a=run_path(days,notional_to_equity=4,cost_overlay_per_notional=0)
        b=run_path(days,notional_to_equity=4,cost_overlay_per_notional=.005)
        self.assertLessEqual(b["equity"],a["equity"])

    def test_single_slot_prevents_overlap_and_is_order_independent(self):
        trades={"BTC-USDT-SWAP":[
                    {"entry_ts":1000,"exit_ts":3000,"notional":100,"net_usd":5},
                    {"entry_ts":5000,"exit_ts":7000,"notional":100,"net_usd":-2}],
                "ETH-USDT-SWAP":[
                    {"entry_ts":2000,"exit_ts":4000,"notional":100,"net_usd":20}]}
        first=single_position_episodes(trades)
        second=single_position_episodes(dict(reversed(list(trades.items()))))
        self.assertEqual(first,second)
        self.assertEqual(len(first),2)
        self.assertEqual([x["symbol"] for x in first],["BTC-USDT-SWAP"]*2)

    def test_daily_block_keeps_same_day_returns_together(self):
        events=[{"entry_ts":10, "net_per_notional":.01},
                {"entry_ts":BAR_MS, "net_per_notional":-.03},
                {"entry_ts":2*86_400_000, "net_per_notional":.02}]
        self.assertEqual(daily_blocks(events),[[.01,-.03],[],[.02]])

    def test_bootstrap_is_deterministic_with_fixed_seed(self):
        a=block_bootstrap([[.01],[-.02],[.05]],notional_to_equity=4,samples=100,seed=9)
        b=block_bootstrap([[.01],[-.02],[.05]],notional_to_equity=4,samples=100,seed=9)
        self.assertEqual(a,b)
        self.assertEqual(sum(round(v*100) for v in
            a["bootstrap_frequencies_not_probabilities"].values()),100)
        self.assertTrue(a["no_validated_prediction"])
        self.assertTrue(a["liquidation_not_modelled"])

    def test_training_veto_all_losses(self):
        data={"BTC":{name:{"train":{"trades":70,"return_pct":-2},
                           "train_stress":{"trades":70,"return_pct":-8}}
                     for name in STRATEGIES},
              "ETH":{name:{"train":{"trades":70,"return_pct":-2},
                           "train_stress":{"trades":70,"return_pct":-8}}
                     for name in STRATEGIES}}
        self.assertEqual(train_only_choice(data),"NO_TRADE")

    def test_six_market_positive_train_can_select_candidate(self):
        data={symbol:{name:{"train":{"trades":11,"return_pct":1.3 if name=="regime_breakout" else -3},
                            "train_stress":{"trades":11,"return_pct":0.8 if name=="regime_breakout" else -6}}
                   for name in STRATEGIES} for symbol in ("A","B","C","D","E","F")}
        self.assertEqual(train_only_choice(data),"regime_breakout")

    def test_reject_nonfinite_return_or_oversized_exposure(self):
        with self.assertRaises(ValueError):
            run_path([[float("nan")]],notional_to_equity=4)
        with self.assertRaises(ValueError):
            run_path([[0.5]],notional_to_equity=101)

    def test_target_and_severe_levels_fixed_and_distinct(self):
        self.assertEqual((INITIAL_EQUITY,TARGET_EQUITY,SEVERE_LOSS_EQUITY),
                         (4.15,8.30,0.83))


if __name__=="__main__":
    unittest.main()
