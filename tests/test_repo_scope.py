from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RepositoryScopeTests(unittest.TestCase):
    def test_unrelated_execution_directories_are_absent(self):
        for name in ("trading", "reports", "research_tests"):
            self.assertFalse((ROOT/name).exists(), name)

    def test_no_exchange_automation_workflows(self):
        workflows=ROOT/".github"/"workflows"
        banned=("okx","titan","nvidia","microspot","freellmapi","nexus7","quantum")
        for path in workflows.glob("*.yml"):
            self.assertFalse(any(x in path.name.lower() for x in banned), path.name)

    def test_public_readmes_are_agent_only(self):
        for filename in ("README.md","README-AR.md"):
            content=(ROOT/filename).read_text(encoding="utf-8").lower()
            for token in ("okx", "titan", "usdt-swap"):
                self.assertNotIn(token, content, filename)

if __name__=="__main__":
    unittest.main()
