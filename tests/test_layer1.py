"""Layer 1 automated tests: rule coverage, override JS contract, and anti-leak invariants."""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402


EXPECTED_RULE_ORDER = [
    "RULE-SET,custom_direct,🎯 全球直连",
    "RULE-SET,custom_direct_ip,🎯 全球直连,no-resolve",
    "RULE-SET,private,🎯 全球直连",
    "RULE-SET,custom_reject,🛑 广告拦截",
    "RULE-SET,custom_ai,🤖 AI 专用",
    "RULE-SET,custom_ai,REJECT",
    "RULE-SET,custom_proxy,🚀 节点选择",
    "RULE-SET,custom_proxy,REJECT",
    "RULE-SET,cn_domain,🎯 全球直连",
    "RULE-SET,cn_ip,🎯 全球直连,no-resolve",
    "MATCH,🚀 节点选择",
    "MATCH,REJECT",
]

REQUIRED_PRIVATE_CIDRS = {
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
}

EXPECTED_LEAK_CHECK_DOMAINS = [
    "ipleak.net",
    "dnsleaktest.com",
    "browserleaks.com",
    "whoer.net",
    "ipinfo.io",
    "ip.sb",
    "ifconfig.me",
    "ipapi.co",
    "ipify.org",
    "whatismyipaddress.com",
    "checkip.amazonaws.com",
]


def run_js_override(mock_config: dict[str, Any]) -> dict[str, Any]:
    """Execute override/mihomo-override.js::main(config) inside Node.js vm."""
    node_bin = shutil.which("node")
    if not node_bin:
        raise unittest.SkipTest("node binary is required to run JS override contract tests")

    override_path = ROOT / "override" / "mihomo-override.js"
    runner = (
        "const fs = require('fs');\n"
        "const vm = require('vm');\n"
        "const code = fs.readFileSync(process.argv[1], 'utf8');\n"
        "const input = JSON.parse(process.argv[2]);\n"
        "const ctx = vm.createContext({});\n"
        "vm.runInContext(code, ctx);\n"
        "const out = ctx.main(input);\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        [node_bin, "-e", runner, str(override_path), json.dumps(mock_config)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def parse_shadowrocket_conf(path: Path) -> dict[str, list[str]]:
    """Parse INI-like Shadowrocket configuration sections preserving order."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def _match_mihomo_domain(domain: str, rules: list[str]) -> bool:
    """Evaluate Mihomo domain-behavior rules ('domain', '.domain', '+.domain')."""
    host = domain.lower().rstrip(".")
    for rule in rules:
        if rule.startswith("+."):
            suffix = rule[2:]
            if host == suffix or host.endswith(f".{suffix}"):
                return True
        elif rule.startswith("."):
            suffix = rule[1:]
            if host.endswith(f".{suffix}"):
                return True
        elif host == rule:
            return True
    return False


def _match_ipcidr(target_ip: str, cidrs: list[str]) -> bool:
    """Evaluate IPv4/IPv6 membership against CIDR list."""
    addr = ipaddress.ip_address(target_ip)
    return any(addr in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def _domain_covers(parent_rule: str, child_rule: str) -> bool:
    """Return True if parent_rule matches everything child_rule matches."""
    if parent_rule == child_rule:
        return True
    if parent_rule.startswith("+."):
        base = parent_rule[2:]
        child_host = child_rule[2:] if child_rule.startswith("+.") else child_rule.lstrip(".")
        return child_host == base or child_host.endswith(f".{base}")
    if parent_rule.startswith("."):
        base = parent_rule[1:]
        child_host = child_rule[2:] if child_rule.startswith("+.") else child_rule.lstrip(".")
        return child_host.endswith(f".{base}")
    return False


class OverrideScriptTests(unittest.TestCase):
    """Contract tests for override/mihomo-override.js."""

    def test_empty_config_returns_unchanged(self) -> None:
        raw = {"proxies": [], "rules": ["MATCH,DIRECT"]}
        out = run_js_override(raw)
        self.assertEqual(out, raw)

    def test_info_nodes_filtered_with_fallback(self) -> None:
        cfg = {
            "proxies": [
                {"name": "剩余流量：120 GB"},
                {"name": "套餐到期：2026-12-31"},
                {"name": "官网：example.com"},
                {"name": "Traffic Reset: 10 days"},
                {"name": "HK-01"},
                {"name": "US-02"},
            ]
        }
        out = run_js_override(cfg)
        groups = {g["name"]: g for g in out["proxy-groups"]}
        self.assertEqual(groups["🚀 节点选择"]["proxies"], ["HK-01", "US-02"])
        self.assertEqual(groups["🤖 AI 专用"]["proxies"], ["🚀 节点选择", "HK-01", "US-02"])
        self.assertEqual(groups["🎯 全球直连"]["proxies"], ["DIRECT"])
        self.assertEqual(groups["🛑 广告拦截"]["proxies"], ["REJECT", "DIRECT"])

        only_info = {"proxies": [{"name": "剩余流量：10 GB"}]}
        fallback_out = run_js_override(only_info)
        fb_groups = {g["name"]: g for g in fallback_out["proxy-groups"]}
        self.assertEqual(fb_groups["🚀 节点选择"]["proxies"], ["剩余流量：10 GB"])

    def test_proxy_providers_mode_binds_use(self) -> None:
        cfg = {"proxies": [], "proxy-providers": {"SubA": {"type": "http"}}}
        out = run_js_override(cfg)
        groups = {g["name"]: g for g in out["proxy-groups"]}
        self.assertEqual(groups["🚀 节点选择"]["use"], ["SubA"])
        self.assertEqual(groups["🤖 AI 专用"]["proxies"], ["🚀 节点选择"])
        self.assertEqual(groups["🤖 AI 专用"]["use"], ["SubA"])

    def test_anti_leak_dns_and_sniffer_invariants(self) -> None:
        out = run_js_override({"proxies": [{"name": "Node-1"}]})

        self.assertIs(out["ipv6"], False)
        self.assertIs(out["unified-delay"], True)
        self.assertIs(out["tcp-concurrent"], True)
        self.assertIs(out["profile"]["store-selected"], True)
        self.assertIs(out["profile"]["store-fake-ip"], True)

        dns = out["dns"]
        self.assertIs(dns["enable"], True)
        self.assertIs(dns["ipv6"], False)
        self.assertIs(dns["respect-rules"], True)
        self.assertEqual(dns["enhanced-mode"], "fake-ip")
        self.assertEqual(dns["fake-ip-range"], "198.18.0.1/16")

        for required_filter in ("+.lan", "+.local", "rule-set:private", "rule-set:custom_direct"):
            self.assertIn(required_filter, dns["fake-ip-filter"])

        # default-nameserver must contain pure IPs only to prevent DoH bootstrap deadlocks
        for server in dns["default-nameserver"]:
            ipaddress.ip_address(server)

        for server in dns["proxy-server-nameserver"] + dns["direct-nameserver"]:
            self.assertTrue(server.startswith("https://"), f"Expected DoH URL, got {server}")

        self.assertTrue(dns["nameserver"])
        for server in dns["nameserver"]:
            self.assertTrue(server.startswith("https://"))
            self.assertTrue(
                server.endswith("#🚀 节点选择"),
                f"Default nameserver must pin proxy group to prevent DNS leak: {server}",
            )

        policy = dns["nameserver-policy"]
        for direct_key in ("rule-set:private", "rule-set:custom_direct", "rule-set:cn_domain"):
            self.assertIn(direct_key, policy)
            for s in policy[direct_key]:
                self.assertNotIn("#", s)
        self.assertTrue(all(s.endswith("#🤖 AI 专用") for s in policy["rule-set:custom_ai"]))
        self.assertTrue(all(s.endswith("#🚀 节点选择") for s in policy["rule-set:custom_proxy"]))

        sniffer = out["sniffer"]
        self.assertIs(sniffer["enable"], True)
        self.assertIs(sniffer["force-dns-mapping"], True)
        self.assertIs(sniffer["parse-pure-ip"], True)
        self.assertIs(sniffer["override-destination"], True)
        for proto in ("HTTP", "TLS", "QUIC"):
            self.assertIn(proto, sniffer["sniff"])

    def test_rule_providers_and_rule_order_invariants(self) -> None:
        out = run_js_override({"proxies": [{"name": "Node-1"}]})
        providers = out["rule-providers"]
        expected_providers = {
            "custom_direct",
            "custom_direct_ip",
            "custom_proxy",
            "custom_ai",
            "custom_reject",
            "private",
            "cn_domain",
            "cn_ip",
        }
        self.assertEqual(set(providers.keys()), expected_providers)
        for name, cfg in providers.items():
            self.assertEqual(cfg["format"], "mrs", f"{name} must use .mrs binary ruleset")
            self.assertTrue(cfg["url"].startswith("https://"))

        self.assertEqual(out["rules"], EXPECTED_RULE_ORDER)


class TemplatesConsistencyTests(unittest.TestCase):
    """Anti-leak and parity tests for templates/shadowrocket.conf and templates/mihomo-base.yaml."""

    def test_shadowrocket_conf_anti_leak_invariants(self) -> None:
        conf_path = ROOT / "templates" / "shadowrocket.conf"
        sections = parse_shadowrocket_conf(conf_path)
        self.assertEqual(set(sections.keys()), {"General", "Proxy Group", "Rule"})

        general: dict[str, str] = {}
        for line in sections["General"]:
            k, v = [p.strip() for p in line.split("=", 1)]
            general[k] = v

        self.assertEqual(general.get("ipv6"), "false")
        self.assertEqual(general.get("prefer-ipv6"), "false")
        self.assertEqual(general.get("dns-direct-system"), "false")
        self.assertEqual(general.get("dns-fallback-system"), "false")
        self.assertEqual(general.get("dns-direct-fallback-proxy"), "true")
        self.assertIn("https://", general.get("dns-server", ""))
        self.assertIn("https://", general.get("fallback-dns-server", ""))

        excluded = {item.strip() for item in general.get("tun-excluded-routes", "").split(",")}
        for cidr in ("10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16"):
            self.assertIn(cidr, excluded)

        groups = {
            line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
            for line in sections["Proxy Group"]
        }
        self.assertIn("🤖 AI 专用", groups)
        self.assertIn("PROXY", groups["🤖 AI 专用"])
        self.assertIn("policy-regex-filter=.*", groups["🤖 AI 专用"])
        self.assertIn("🛑 广告拦截", groups)
        self.assertIn("REJECT", groups["🛑 广告拦截"])
        self.assertIn("DIRECT", groups["🛑 广告拦截"])

        rules = sections["Rule"]
        expected_prefixes = [
            "custom-direct.list",
            "custom-direct-ip.list",
            "private.list",
            "custom-reject.list",
            "custom-ai.list",
            "custom-proxy.list",
            "DOMAIN-SET,",
            "GEOIP,CN,DIRECT,no-resolve",
            "FINAL,PROXY",
        ]
        self.assertEqual(len(rules), len(expected_prefixes))
        for rule_line, token in zip(rules, expected_prefixes):
            self.assertIn(token, rule_line)

        # Every IP-based rule in Shadowrocket must carry no-resolve to avoid local DNS leak
        for rule_line in rules:
            if "custom-direct-ip.list" in rule_line or rule_line.startswith("GEOIP,"):
                self.assertIn(",no-resolve", rule_line)

        sources = build.load_sources(ROOT / "sources.yaml")
        bundle_names = {b["name"] for b in sources["bundles"]}
        for rule_line in rules:
            if "proxy-ruleset@dist/shadowrocket/" in rule_line:
                filename = rule_line.split("/shadowrocket/", 1)[1].split(",", 1)[0]
                self.assertIn(filename.removesuffix(".list"), bundle_names)

    def test_mihomo_base_yaml_parity_with_override(self) -> None:
        yaml_path = ROOT / "templates" / "mihomo-base.yaml"
        text = yaml_path.read_text(encoding="utf-8")

        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
        except ModuleNotFoundError:
            data = None

        if data is not None:
            self.assertIs(data["ipv6"], False)
            self.assertIs(data["dns"]["ipv6"], False)
            self.assertIs(data["dns"]["respect-rules"], True)
            self.assertEqual(data["dns"]["enhanced-mode"], "fake-ip")
            self.assertEqual(data["dns"]["fake-ip-range"], "198.18.0.1/16")
            self.assertEqual(data["rules"], EXPECTED_RULE_ORDER)
            self.assertTrue(all(s.endswith("#🚀 节点选择") for s in data["dns"]["nameserver"]))
        else:
            # Pure-stdlib structural check when PyYAML is not installed locally
            for required_snippet in (
                "ipv6: false",
                "respect-rules: true",
                "enhanced-mode: fake-ip",
                "fake-ip-range: 198.18.0.1/16",
                *(f"- {rule}" for rule in EXPECTED_RULE_ORDER),
            ):
                self.assertIn(required_snippet, text)


class RuleAuditAndRoutingSimulatorTests(unittest.TestCase):
    """Static rule quality audit, conflict checks, and offline routing simulation."""

    @classmethod
    def setUpClass(cls) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build.py"), "--offline"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Done." in proc.stdout

    def test_private_cidrs_complete_and_no_public_ip(self) -> None:
        raw = (ROOT / "rules" / "custom-direct-ip.list").read_text(encoding="utf-8")
        entries = build.parse_lines(raw, "ipcidr", "custom-direct-ip.list")
        cidrs = {m for m, _ in entries}
        self.assertTrue(REQUIRED_PRIVATE_CIDRS.issubset(cidrs))

        for cidr in cidrs:
            net = ipaddress.ip_network(cidr, strict=False)
            self.assertFalse(
                net.is_global,
                f"Public routable IP {cidr} must not be in custom-direct-ip.list",
            )

    def test_direct_local_suffixes_present(self) -> None:
        raw = (ROOT / "rules" / "custom-direct.list").read_text(encoding="utf-8")
        mihomo_rules = {m for m, _ in build.parse_lines(raw, "domain", "custom-direct.list")}
        for suffix in ("+.local", "+.lan", "+.home.arpa"):
            self.assertIn(suffix, mihomo_rules)

    def test_no_suffix_shadowing_conflicts_across_groups(self) -> None:
        groups: dict[str, list[str]] = {}
        for name in ("custom-direct", "custom-proxy", "custom-ai", "custom-reject"):
            raw = (ROOT / "rules" / f"{name}.list").read_text(encoding="utf-8")
            groups[name] = [m for m, _ in build.parse_lines(raw, "domain", name)]

        for direct_rule in groups["custom-direct"]:
            for other in ("custom-proxy", "custom-ai", "custom-reject"):
                for other_rule in groups[other]:
                    self.assertFalse(
                        _domain_covers(direct_rule, other_rule)
                        or _domain_covers(other_rule, direct_rule),
                        f"Suffix overlap between custom-direct ({direct_rule}) and {other} ({other_rule})",
                    )

        for reject_rule in groups["custom-reject"]:
            for other in ("custom-proxy", "custom-ai"):
                for other_rule in groups[other]:
                    self.assertFalse(
                        _domain_covers(reject_rule, other_rule)
                        or _domain_covers(other_rule, reject_rule),
                        f"Suffix overlap between custom-reject ({reject_rule}) and {other} ({other_rule})",
                    )

    def test_dist_artifacts_sync_and_shadowrocket_no_resolve(self) -> None:
        dist = ROOT / "dist"
        self.assertEqual(
            (dist / "override" / "mihomo-override.js").read_text(encoding="utf-8"),
            (ROOT / "override" / "mihomo-override.js").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (dist / "shadowrocket" / "shadowrocket.conf").read_text(encoding="utf-8"),
            (ROOT / "templates" / "shadowrocket.conf").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (dist / "templates" / "mihomo-base.yaml").read_text(encoding="utf-8"),
            (ROOT / "templates" / "mihomo-base.yaml").read_text(encoding="utf-8"),
        )

        sr_ip_lines = [
            line.strip()
            for line in (dist / "shadowrocket" / "custom-direct-ip.list").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(sr_ip_lines)
        for line in sr_ip_lines:
            self.assertTrue(line.endswith(",no-resolve"), f"Missing no-resolve: {line}")

    def test_routing_simulation_and_leak_site_coverage(self) -> None:
        dist_mihomo = ROOT / "dist" / "mihomo"
        domain_sets = {
            name: [
                line.strip()
                for line in (dist_mihomo / f"{name}.txt").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for name in ("custom-direct", "custom-reject", "custom-ai", "custom-proxy")
        }
        direct_cidrs = [
            line.strip()
            for line in (dist_mihomo / "custom-direct-ip.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        # All declared leak-check domains in rules/custom-proxy.list must resolve into custom-proxy
        for domain in EXPECTED_LEAK_CHECK_DOMAINS:
            self.assertTrue(
                _match_mihomo_domain(domain, domain_sets["custom-proxy"]),
                f"Expected leak-check domain missing from custom-proxy: {domain}",
            )

        def route(target: str) -> tuple[str, str]:
            is_ip = False
            try:
                ipaddress.ip_address(target)
                is_ip = True
            except ValueError:
                pass

            if not is_ip and _match_mihomo_domain(target, domain_sets["custom-direct"]):
                return "🎯 全球直连", "custom_direct"
            if is_ip and _match_ipcidr(target, direct_cidrs):
                return "🎯 全球直连", "custom_direct_ip"
            if not is_ip and _match_mihomo_domain(target, domain_sets["custom-reject"]):
                return "🛑 广告拦截", "custom_reject"
            if not is_ip and _match_mihomo_domain(target, domain_sets["custom-ai"]):
                return "🤖 AI 专用", "custom_ai"
            if not is_ip and _match_mihomo_domain(target, domain_sets["custom-proxy"]):
                return "🚀 节点选择", "custom_proxy"
            return "🚀 节点选择", "MATCH"

        cases = [
            ("nas.local", ("🎯 全球直连", "custom_direct")),
            ("router.home.arpa", ("🎯 全球直连", "custom_direct")),
            ("192.168.1.50", ("🎯 全球直连", "custom_direct_ip")),
            ("100.64.0.5", ("🎯 全球直连", "custom_direct_ip")),
            ("fe80::1", ("🎯 全球直连", "custom_direct_ip")),
            ("ads.doubleclick.net", ("🛑 广告拦截", "custom_reject")),
            ("api.openai.com", ("🤖 AI 专用", "custom_ai")),
            ("claude.ai", ("🤖 AI 专用", "custom_ai")),
            ("sub.ipleak.net", ("🚀 节点选择", "custom_proxy")),
            ("browserleaks.com", ("🚀 节点选择", "custom_proxy")),
            ("dnsleaktest.com", ("🚀 节点选择", "custom_proxy")),
            ("checkip.amazonaws.com", ("🚀 节点选择", "custom_proxy")),
            ("stun.l.google.com", ("🚀 节点选择", "custom_proxy")),
            ("stun1.l.google.com", ("🚀 节点选择", "custom_proxy")),
            ("stun.voip.blackberry.com", ("🚀 节点选择", "custom_proxy")),
            ("global.stun.twilio.com", ("🚀 节点选择", "custom_proxy")),
            ("stun.cloudflare.com", ("🚀 节点选择", "custom_proxy")),
            ("stun.nextcloud.com", ("🚀 节点选择", "custom_proxy")),
            ("example-unknown.org", ("🚀 节点选择", "MATCH")),
            ("1.1.1.1", ("🚀 节点选择", "MATCH")),
        ]
        for target, expected in cases:
            with self.subTest(target=target):
                self.assertEqual(route(target), expected)


if __name__ == "__main__":
    unittest.main()
