import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        cases = [
            ("custom-direct", "DOMAIN,example.com", "custom-proxy", "DOMAIN,example.com"),
            ("custom-direct", "DOMAIN-SUFFIX,example.com", "custom-ai", "api.example.com"),
            ("custom-direct", "api.example.com", "custom-ai", "HOST-SUFFIX,example.com"),
            ("custom-reject", "+.example.com", "custom-proxy", "+.api.example.com"),
            ("custom-reject", ".example.com", "custom-ai", "example.com"),
            ("private", "api.*.example.com", "custom-ai", "+.corp.example.com"),
        ]
        for first_group, first_rule, second_group, second_rule in cases:
            with self.subTest(first_rule=first_rule, second_rule=second_rule):
                compiled = {
                    first_group: build.parse_lines(first_rule, "domain", "local"),
                    second_group: build.parse_lines(second_rule, "domain", "upstream"),
                }
                with self.assertRaises(RuntimeError) as error:
                    build.check_conflicts(compiled)
                for group, rules in compiled.items():
                    self.assertIn(f"'{group}' ({rules[0][0]})", str(error.exception))

    def test_conflicts_preserve_label_boundaries_and_ai_priority(self) -> None:
        build.check_conflicts({
            "custom-direct": build.parse_lines(
                "+.example.com\nexact.example.org", "domain", "local"
            ),
            "custom-proxy": build.parse_lines(
                "+.notexample.com\nchild.exact.example.org", "domain", "local"
            ),
            "custom-ai": build.parse_lines("api.notexample.com", "domain", "upstream"),
        })

    def test_online_build_validates_upstream_before_replacing_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "direct.list").write_text("DOMAIN-SUFFIX,example.com\n", encoding="utf-8")
            (root / "dist").mkdir()
            previous_build = root / "dist" / "manifest.json"
            previous_build.write_text("{}", encoding="utf-8")
            url = "https://example.org/ai.list"
            sources = {
                "bundles": [
                    {"name": "custom-direct", "behavior": "domain", "local": "direct.list"},
                    {"name": "custom-ai", "behavior": "domain", "upstream": [url]},
                ]
            }
            with (
                patch.object(build, "ROOT", root),
                patch.object(build, "load_sources", return_value=sources),
                patch.object(build, "fetch_url", return_value="api.example.com") as fetch,
                patch.object(sys, "argv", ["build.py"]),
            ):
                with self.assertRaisesRegex(RuntimeError, r"custom-direct.*custom-ai"):
                    build.main()
                fetch.assert_called_once_with(url)
            self.assertEqual(previous_build.read_text(encoding="utf-8"), "{}")

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
        proxy_sr = (dist / "shadowrocket" / "custom-proxy.list").read_text(encoding="utf-8")
        self.assertIn("DOMAIN,stun.voip.blackberry.com", proxy_sr)


if __name__ == "__main__":
    unittest.main()
