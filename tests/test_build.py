import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402


class BuildTests(unittest.TestCase):
    def test_normalize_domain_variants(self) -> None:
        self.assertEqual(
            build.normalize_domain_line("DOMAIN-SUFFIX,OpenAI.com", "test", 1),
            ("+.openai.com", "DOMAIN-SUFFIX,openai.com"),
        )
        self.assertEqual(
            build.normalize_domain_line("DOMAIN,api.openai.com", "test", 2),
            ("api.openai.com", "DOMAIN,api.openai.com"),
        )
        self.assertEqual(
            build.normalize_domain_line("+.claude.ai", "test", 3),
            ("+.claude.ai", "DOMAIN-SUFFIX,claude.ai"),
        )
        self.assertEqual(
            build.normalize_domain_line("gemini.google.com", "test", 4),
            ("gemini.google.com", "DOMAIN,gemini.google.com"),
        )

    def test_rejects_keyword_in_domain_bundle(self) -> None:
        with self.assertRaises(ValueError):
            build.normalize_domain_line("DOMAIN-KEYWORD,google", "test", 1)

    def test_normalize_ipcidr_variants(self) -> None:
        self.assertEqual(
            build.normalize_ipcidr_line("IP-CIDR,192.168.1.5/24", "test", 1),
            ("192.168.1.0/24", "IP-CIDR,192.168.1.0/24,no-resolve"),
        )
        self.assertEqual(
            build.normalize_ipcidr_line("IP-CIDR6,fe80::1/10,no-resolve", "test", 2),
            ("fe80::/10", "IP-CIDR6,fe80::/10,no-resolve"),
        )

    def test_conflict_detection(self) -> None:
        compiled = {
            "custom-direct": [("+.example.com", "DOMAIN-SUFFIX,example.com")],
            "custom-proxy": [("+.example.com", "DOMAIN-SUFFIX,example.com")],
        }
        with self.assertRaises(RuntimeError):
            build.check_conflicts(compiled)

    def test_offline_build_outputs(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build.py"), "--offline"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Done.", proc.stdout)
        dist = ROOT / "dist"
        self.assertTrue((dist / "override" / "mihomo-override.js").is_file())
        self.assertTrue((dist / "shadowrocket" / "shadowrocket.conf").is_file())
        self.assertTrue((dist / "templates" / "mihomo-base.yaml").is_file())
        manifest = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("custom-direct", manifest["bundles"])
        self.assertIn("custom-proxy", manifest["bundles"])
        self.assertIn("custom-ai", manifest["bundles"])


if __name__ == "__main__":
    unittest.main()
