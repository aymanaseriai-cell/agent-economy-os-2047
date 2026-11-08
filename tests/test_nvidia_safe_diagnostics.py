import unittest
from trading.nvidia_execution_gate import (
    GateRejected, safe_nvidia_error_summary, _nvidia_failure_category,
    require_nvidia_veto_pass,
)
from tests.test_nvidia_execution_gate import fixture

class NvidiaSafeDiagnosticTests(unittest.TestCase):
    def test_http_code_is_exposed_but_raw_error_omitted(self):
        self.assertEqual(_nvidia_failure_category("NVIDIA inference HTTP 429"), "HTTP_429")
        resp={"agents_responded":1, "errors":[{"agent":"risk_critic","error":"NVIDIA inference HTTP 429 TOP_SECRET_TOKEN"}]}
        result=safe_nvidia_error_summary(resp)
        self.assertIn("roles=1/6",result)
        self.assertIn("HTTP_429",result)
        self.assertNotIn("TOP_SECRET_TOKEN",result)
        self.assertNotIn("risk_critic",result)

    def test_invalid_output_and_unusable_model_are_categorized(self):
        self.assertEqual(_nvidia_failure_category("Model returned invalid JSON"),"INVALID_MODEL_OUTPUT")
        self.assertEqual(_nvidia_failure_category("No usable inference model responded"),"NO_USABLE_MODEL")

    def test_incomplete_council_blocks_without_trading(self):
        report,signal=fixture()
        def incomplete(*args,**kwargs):
            return {"mode":"ADVISORY_ONLY","execution_authorized":False,
                    "agents_expected":6,"agents_responded":0,
                    "model":"private-model","votes":[],
                    "errors":[{"agent":"trend","error":"NVIDIA inference HTTP 401 HiddenSecret"}],
                    "advisory":"WAIT"}
        with self.assertRaisesRegex(GateRejected,"HTTP_401") as caught:
            require_nvidia_veto_pass(report,signal,"fake",council_fn=incomplete)
        self.assertNotIn("HiddenSecret",str(caught.exception))
        self.assertNotIn("private-model",str(caught.exception))

    def test_unknown_errors_are_not_replayed_in_logs(self):
        bad={"agents_responded":"not_a_number","errors":[{"error":"PASSWORD abc-123"}]}
        self.assertEqual(safe_nvidia_error_summary(bad),
                         "roles=unknown/6; errors=1; categories=UNKNOWN")

    def test_malformed_response_still_rejected(self):
        self.assertEqual(safe_nvidia_error_summary(None),"response_type_invalid")
        report,signal=fixture()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report,signal,"fake",council_fn=lambda *a,**k: None)
