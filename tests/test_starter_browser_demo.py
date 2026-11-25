import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class StarterBrowserDemoTests(unittest.TestCase):
    def test_discoverability_and_network_boundary(self):
        page = (ROOT / "docs/starter-demo.html").read_text(encoding="utf-8")
        index = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        scope = (ROOT / "docs/PILOT_49.md").read_text(encoding="utf-8")
        self.assertIn('href="./starter-demo.html"', index)
        self.assertIn("starter-demo.html", scope)
        self.assertIn("connect-src 'none'", page)
        self.assertIn("form-action 'none'", page)
        self.assertIn('src="./starter-demo.js"', page)
        self.assertIn("No check run yet.", page)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_js_synthetic_scenarios(self):
        subprocess.run(["node", "--test", str(ROOT / "tests/starter-browser.test.cjs")],
                       cwd=ROOT, check=True, timeout=30, capture_output=True, text=True)
