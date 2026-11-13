import json
import tempfile
import unittest
from pathlib import Path
from trading.titan2037_flight_recorder import parse_log, summarize, load_directory

def sample():
    return "\n".join([
        "2026-11-13T20:30:00Z TITAN cycle 1 start; full public council scan",
        "2026-11-13T20:30:10Z SIX AGENTS + QUANT2037: selected= 36 analyzed= 36 signals= 0 errors= 0",
        "2026-11-13T20:30:10Z TITAN SAME-BATCH UNIVERSE: all_eligible= True screened= 226 qualified_for_deep_analysis= 36 completed= 36",
        '2026-11-13T20:30:11Z TITAN VETO BREAKDOWN: advanced= {"no_independent_quant_confirmation": 1} omega= {"multiverse_no_positive_net_edge": 2}',
        "2026-11-13T20:30:11Z TITAN SIGNAL DIAGNOSTICS: core_candidates= 3 omega_vetoes= 2 advanced_vetoes= 1 consensus_entries= 0",
        "2026-11-13T20:30:12Z OKX PORTFOLIO SLOTS: open=1 limit=10 remaining=9",
        "2026-11-13T20:30:13Z OKX EXECUTION RESULT: NO_CONSENSUS",
        "2026-11-13T20:30:19Z TITAN cycle 2 start; full public council scan",
        "2026-11-13T20:30:29Z SIX AGENTS + QUANT2037: selected= 35 analyzed= 35 signals= 1 errors= 0",
        "2026-11-13T20:30:30Z TITAN SIGNAL DIAGNOSTICS: core_candidates= 1 omega_vetoes= 0 advanced_vetoes= 0 consensus_entries= 1",
        "2026-11-13T20:30:31Z OKX EXECUTION RESULT: FILLED_PROTECTED",
    ])

class FlightRecorderTests(unittest.TestCase):
    def test_counts_reflect_real_log_pattern(self):
        a=parse_log(1234,sample())
        self.assertEqual(a["cycles"],2)
        self.assertEqual(a["scan_count"],2)
        self.assertEqual(a["market_analyses_including_repeats"],71)
        self.assertEqual(a["max_screened"],226)
        self.assertEqual(a["logged_outcomes"]["FILLED_PROTECTED"],1)
        self.assertEqual(a["logged_outcomes"]["NO_CONSENSUS"],1)
        self.assertEqual(a["veto_counts"]["multiverse_no_positive_net_edge"],2)
        self.assertEqual(a["median_result_interval_seconds"],18)
        self.assertEqual(a["last_logged_open_positions"],1)

    def test_true_sources_not_overclaimed(self):
        a=summarize([parse_log(1234,sample())])
        self.assertEqual(len(a["agents"]),7)
        self.assertEqual(a["orders_submitted"],0)
        self.assertEqual(a["live_settings_changes"],0)
        self.assertFalse(a["agents"]["stop_governor"]["auto_enable_live"])
        self.assertIn("NOT_INDEPENDENT",a["agents"]["execution_truth"]["status"])

    def test_empty_logs_no_fabricated_data(self):
        a=summarize([parse_log(1234,"")])
        self.assertEqual(a["runs_with_evidence"],0)
        self.assertEqual(a["outcomes"],{})
        self.assertIsNone(a["runs"][0]["last_logged_open_positions"])

    def test_duplicate_runs_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            summarize([parse_log(1,sample()),parse_log(1,sample())])

    def test_position_inconsistency_rejected(self):
        with self.assertRaisesRegex(ValueError,"contradict"):
            parse_log(1,"OKX PORTFOLIO SLOTS: open=9 limit=10 remaining=4")

    def test_bad_veto_counts_rejected(self):
        with self.assertRaisesRegex(ValueError,"Invalid veto counter"):
            parse_log(1,'TITAN VETO BREAKDOWN: advanced= {"x": -1} omega= {}')

    def test_no_adverse_data_in_aggregate(self):
        a=summarize([parse_log(1,sample()+"\nsecret=abc123456")])
        self.assertNotIn("abc123456",json.dumps(a))

    def test_filename_filter_and_total(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,"123.log").write_text(sample())
            Path(root,"not-a-run.log").write_text("ignore")
            a=load_directory(Path(root))
            self.assertEqual(a["runs_parsed"],1)
            self.assertEqual(a["agents"]["coverage_accountant"]["deep_scans"],2)

    def test_invalid_run_and_oversize(self):
        with self.assertRaises(ValueError):
            parse_log(True,sample())
        with self.assertRaises(ValueError):
            parse_log(1,"x"*6000001)

    def test_no_private_order_route(self):
        import inspect
        import trading.titan2037_flight_recorder as module
        code=inspect.getsource(module)
        for forbidden in ("OKX_API_KEY","OKX_SECRET_KEY","requests.post(",
                          "subprocess.run(", "place_order(", "urlopen("):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":
    unittest.main()
