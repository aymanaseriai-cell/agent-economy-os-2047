import math
import unittest

from trading.titan_cosmos import SYSTEMS, evaluate_cosmos


def bars(n, slope=0.0, wave=0.0):
    out=[]
    for i in range(n):
        price=100*math.exp(slope*i+wave*math.sin(i/4))
        out.append({"ts":i*900000, "open":price, "high":price*1.001,
                    "low":price*0.999, "close":price, "quote_vol":25000})
    return out


class CosmosResearchTests(unittest.TestCase):
    def test_exactly_ten_deterministic_read_only_metrics(self):
        book={"bids":[["100","200"] for _ in range(20)],
              "asks":[["100","100"] for _ in range(20)]}
        args=(bars(200,0.0005,0.001),bars(80,0.001),bars(50,0.002),book)
        one=evaluate_cosmos(*args)
        two=evaluate_cosmos(*args)
        self.assertEqual(one,two)
        self.assertTrue(one["cosmos_data_valid"])
        self.assertTrue(one["cosmos_research_only"])
        self.assertEqual(one["cosmos_system_count"],10)
        self.assertEqual(len(one["cosmos_systems"]),len(SYSTEMS))
        self.assertEqual(one["orders_placed"],0)
        self.assertTrue(all(x["status"]=="DIAGNOSTIC_ONLY" for x in one["cosmos_systems"]))
        for x in one["cosmos_systems"]:
            for metric in x["metrics"].values():
                if metric is not None:
                    self.assertTrue(math.isfinite(metric))

    def test_neutral_flat_candles_are_finite(self):
        result=evaluate_cosmos(bars(200),bars(80),bars(50),{})
        self.assertTrue(result["cosmos_data_valid"])
        by_name={x["name"]: x for x in result["cosmos_systems"]}
        self.assertEqual(by_name[SYSTEMS[0]]["metrics"]["normalized_amplitude_proxy"],0)
        self.assertIsNone(by_name[SYSTEMS[8]]["metrics"]["top20_depth_imbalance"])

    def test_bad_data_does_not_fabricate_signals(self):
        result=evaluate_cosmos([{"close":0}]*100,bars(80),bars(50),{})
        self.assertFalse(result["cosmos_data_valid"])
        self.assertEqual(result["cosmos_systems"],[])
        self.assertEqual(result["orders_placed"],0)

    def test_incomplete_candles_are_not_interpreted(self):
        result=evaluate_cosmos(bars(20),bars(80),bars(50),{})
        self.assertFalse(result["cosmos_data_valid"])
        self.assertTrue(result["cosmos_research_only"])


if __name__ == "__main__":
    unittest.main()
