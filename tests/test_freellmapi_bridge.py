import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from trading.freellmapi_bridge import (
    BridgeError, NoRedirect, config_status, evaluate, parse_vote,
    validate_public_snapshot, gateway_endpoint, call_free_gateway,
    evaluate_scan
)

NOW=datetime(2026,11,8,18,0,tzinfo=timezone.utc)

def snapshot():
    return {
        "source":"OKX public market feeds and deterministic calculations",
        "as_of_utc":NOW.isoformat(),
        "symbol":"UNI-USDT-SWAP",
        "quant_hypothesis_not_an_order":"LONG",
        "quote_price":7.0,
        "quantitative_evidence":[{"role":f"role{i}","veto":False,"evidence":{}} for i in range(6)],
        "news":[]
    }

def settings():
    return {
      "FREELLMAPI_BASE_URL":"http://localhost:3001/v1",
      "FREELLMAPI_API_KEY":"test-unified-key-NOT-REAL",
      "FREELLMAPI_MODEL":"auto:smart",
      "FREELLMAPI_ENABLE_REQUESTS":"YES"
    }

def payload(direction="BUY",confidence=.9):
    return {"choices":[{"message":{"content":json.dumps({
        "direction":direction,"confidence":confidence,"evidence":["market"],
        "risks":["spread"]})}}]}

def transport(url,key,model,snap):
    assert url=="http://localhost:3001/v1/chat/completions"
    return payload(),{"routed_via":"nvidia/example","fallback_attempts":2}

class FreeLLMBridgeTests(unittest.TestCase):
    def test_configuration_requires_unified_key(self):
        x=config_status({})
        self.assertFalse(x["ready"])
        self.assertEqual(x["requests_sent"],0)

    def test_configuration_ready_does_not_call_network(self):
        x=config_status(settings())
        self.assertTrue(x["ready"])
        self.assertFalse(x["execution_authorized"])

    def test_local_router_path_is_fixed(self):
        self.assertEqual(gateway_endpoint("http://localhost:3001/v1",settings()),
                         "http://localhost:3001/v1/chat/completions")
        self.assertEqual(gateway_endpoint("http://127.0.0.1:3001",settings()),
                         "http://127.0.0.1:3001/v1/chat/completions")

    def test_remote_requires_strict_https_allowlist(self):
        url="https://my-private-gateway.example.com:443/v1"
        with self.assertRaises(BridgeError):
            gateway_endpoint(url,settings())
        e=settings()
        e["FREELLMAPI_ALLOWED_HTTPS_HOST"]="my-private-gateway.example.com"
        self.assertEqual(gateway_endpoint(url,e),
                         "https://my-private-gateway.example.com:443/v1/chat/completions")

    def test_disallow_unauthorized_remote_or_credentials(self):
        for url in ("http://10.0.0.2:3001","https://192.168.1.3:3001",
                    "file:///tmp/x","http://hacker.example.com:3001",
                    "http://user:password@localhost:3001",
                    "http://localhost:3001/v1?key=secret",
                    "http://localhost:3001/v1#fragment"):
            with self.assertRaises(BridgeError, msg=url):
                gateway_endpoint(url,settings())

    def test_manual_network_latch_fail_closed(self):
        e=settings()
        e.pop("FREELLMAPI_ENABLE_REQUESTS")
        x=evaluate(snapshot(),env=e,now=NOW,network_enabled=True,
                   transport=lambda *a:self.fail("no request allowed"))
        self.assertEqual(x["requests_sent"],0)
        self.assertEqual(x["advisory"],"WAIT")

    def test_default_no_network_even_when_key_configured(self):
        x=evaluate(snapshot(),env=settings(),now=NOW,
                   transport=lambda *a:self.fail("no request allowed"))
        self.assertEqual(x["requests_sent"],0)

    def test_valid_free_router_approval_is_not_trade_authority(self):
        x=evaluate(snapshot(),env=settings(),now=NOW,
                   transport=transport,network_enabled=True)
        self.assertEqual(x["advisory"],"BUY")
        self.assertEqual(x["requests_sent"],1)
        self.assertFalse(x["execution_authorized"])
        self.assertEqual(x["orders_placed"],0)
        self.assertEqual(x["provider_count_independently_verified"],0)

    def test_fusion_is_a_single_unverified_advisory(self):
        e=settings()
        e["FREELLMAPI_MODEL"]="fusion"
        x=evaluate(snapshot(),env=e,now=NOW,
                   transport=transport,network_enabled=True)
        self.assertEqual(x["model_requested"],"fusion")
        self.assertTrue(x["gateway_fusion_not_independent_consensus"])
        self.assertEqual(x["provider_count_independently_verified"],0)

    def test_wait_or_opposing_vote_vetoes(self):
        for direction in ("WAIT","SELL"):
            x=evaluate(snapshot(),env=settings(),now=NOW,network_enabled=True,
                       transport=lambda *a:(payload(direction),{}))
            self.assertEqual(x["advisory"],"WAIT")

    def test_json_injection_does_not_promote_trade(self):
        bad={"choices":[{"message":{"content":"BUY\n"+json.dumps({
            "direction":"BUY","confidence":1,"evidence":[],"risks":[]})}}]}
        x=evaluate(snapshot(),env=settings(),now=NOW,network_enabled=True,
                   transport=lambda *a:(bad,{}))
        self.assertEqual(x["advisory"],"WAIT")

    def test_untrusted_exception_never_logs_unified_key(self):
        e=settings()
        def broken(*a):raise RuntimeError("secret:"+e["FREELLMAPI_API_KEY"])
        x=evaluate(snapshot(),env=e,now=NOW,network_enabled=True,
                   transport=broken)
        self.assertEqual(x["advisory"],"WAIT")
        self.assertNotIn(e["FREELLMAPI_API_KEY"],json.dumps(x))

    def test_aged_and_future_snapshot_fails_before_request(self):
        for offset in (-180,5):
            s=snapshot()
            s["as_of_utc"]=(NOW+timedelta(seconds=offset)).isoformat()
            x=evaluate(s,env=settings(),now=NOW,network_enabled=True,
                transport=lambda *a:self.fail("network"))
            self.assertEqual(x["requests_sent"],0)

    def test_no_private_account_evidence(self):
        x=snapshot()
        x["api_key"]="any"
        with self.assertRaises(BridgeError):
            validate_public_snapshot(x,now=NOW)

    def test_wait_cannot_become_candidate(self):
        x=snapshot()
        x["quant_hypothesis_not_an_order"]="WAIT"
        out=evaluate(x,env=settings(),now=NOW,network_enabled=True,
                     transport=lambda *a:self.fail("network"))
        self.assertEqual(out["advisory"],"WAIT")
        self.assertEqual(out["requests_sent"],0)

    def test_invalid_model_not_accepted(self):
        e=settings()
        e["FREELLMAPI_MODEL"]="arbitrary/free-untrusted"
        out=evaluate(snapshot(),env=e,now=NOW,network_enabled=True,
                     transport=lambda *a:self.fail("network"))
        self.assertEqual(out["requests_sent"],0)

    def test_redirects_do_not_forward_bearer(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,"Found",{},
                        "https://attacker.invalid/leak"))

    def test_boolean_and_nonfinite_confidence_rejected(self):
        for n in (True,float("nan"),1.1):
            with self.assertRaises(BridgeError):
                parse_vote(payload(confidence=n))

    def test_report_origin_not_quant_rejected(self):
        x=evaluate_scan({"mode":"other","results":[]},env=settings(),now=NOW,
                        network_enabled=True,
                        transport=lambda *a:self.fail("network"))
        self.assertEqual(x["advisory"],"WAIT")
        self.assertEqual(x["orders_placed"],0)

    def test_http_transport_sends_no_tool_calls(self):
        class Response:
            headers={"X-Routed-Via":"groq/llama","X-Fallback-Attempts":"1"}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return json.dumps(payload()).encode()
        class Opener:
            request=None
            def open(self,request,timeout):
                self.request=request
                return Response()
        obj=Opener()
        with patch("trading.freellmapi_bridge.urllib.request.build_opener",return_value=obj):
            data,meta=call_free_gateway("http://localhost:3001/v1/chat/completions",
                "fake-key","auto:smart",snapshot())
        self.assertEqual(meta["routed_via"],"groq/llama")
        self.assertEqual(meta["fallback_attempts"],1)
        body=json.loads(obj.request.data)
        self.assertNotIn("tools",body)
        self.assertEqual(body["stream"],False)
        self.assertEqual(data["choices"][0]["message"]["content"],payload()["choices"][0]["message"]["content"])

if __name__=="__main__":
    unittest.main()
