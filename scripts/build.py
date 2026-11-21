#!/usr/bin/env python3
"""Build Mihomo (.txt/.mrs) and Shadowrocket (.list/.conf) artifacts from unified rules."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INFO_SUFFIX_PREFIX = "DOMAIN-SUFFIX,"
INFO_EXACT_PREFIX = "DOMAIN,"


def load_sources(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return _parse_simple_sources_yaml(text)


def _parse_simple_sources_yaml(text: str) -> dict[str, Any]:
    """Minimal pure-stdlib parser for sources.yaml when PyYAML is unavailable."""
    data: dict[str, Any] = {"bundles": []}
    current_bundle: dict[str, Any] | None = None
    in_upstream = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()

        if stripped == "bundles:":
            in_upstream = False
            continue

        if raw_line.startswith("  - ") and current_bundle is not None or (
            raw_line.lstrip().startswith("- name:")
        ):
            in_upstream = False
            current_bundle = {"upstream": []}
            data["bundles"].append(current_bundle)
            kv = stripped[2:].strip()
            if ":" in kv:
                k, v = [p.strip() for p in kv.split(":", 1)]
                current_bundle[k] = _parse_scalar(v)
            continue

        if current_bundle is not None and raw_line.startswith("      - "):
            if in_upstream:
                current_bundle["upstream"].append(_parse_scalar(stripped[2:].strip()))
            continue

        if current_bundle is not None and raw_line.startswith("    "):
            if ":" in stripped:
                k, v = [p.strip() for p in stripped.split(":", 1)]
                if k == "upstream":
                    in_upstream = True
                    if v == "[]":
                        current_bundle["upstream"] = []
                        in_upstream = False
                else:
                    in_upstream = False
                    current_bundle[k] = _parse_scalar(v)
            continue

        if ":" in stripped:
            in_upstream = False
            k, v = [p.strip() for p in stripped.split(":", 1)]
            data[k] = _parse_scalar(v)

    return data


def _parse_scalar(value: str) -> Any:
    if value in ("null", "~", ""):
        return None
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def fetch_url(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "proxy-ruleset-builder/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def normalize_domain_line(raw: str, source_name: str, line_no: int) -> tuple[str, str]:
    """Return (mihomo_text_rule, shadowrocket_rule) for a domain entry."""
    line = raw.strip()
    if line.startswith(("DOMAIN-SUFFIX,", "DOMAIN,", "HOST-SUFFIX,", "HOST,")):
        rule_type, val = [p.strip() for p in line.split(",", 1)]
        val = val.split(",", 1)[0].strip().lower()
        if not val or " " in val or "/" in val:
            raise ValueError(f"{source_name}:{line_no}: invalid domain '{raw}'")
        if rule_type in ("DOMAIN-SUFFIX", "HOST-SUFFIX"):
            return f"+.{val}", f"DOMAIN-SUFFIX,{val}"
        return val, f"DOMAIN,{val}"

    if line.startswith("+."):
        domain = line[2:].strip().lower()
        if not domain or " " in domain:
            raise ValueError(f"{source_name}:{line_no}: invalid domain '{raw}'")
        return f"+.{domain}", f"DOMAIN-SUFFIX,{domain}"

    if line.startswith("."):
        domain = line[1:].strip().lower()
        if not domain or " " in domain:
            raise ValueError(f"{source_name}:{line_no}: invalid domain '{raw}'")
        return f".{domain}", f"DOMAIN-SUFFIX,{domain}"

    if "," in line:
        raise ValueError(
            f"{source_name}:{line_no}: unsupported rule in domain bundle '{raw}' "
            "(only DOMAIN, DOMAIN-SUFFIX, or domain/+.domain entries are allowed for .mrs compilation)"
        )

    domain = line.lower()
    if " " in domain or "/" in domain:
        raise ValueError(f"{source_name}:{line_no}: invalid domain '{raw}'")
    return domain, f"DOMAIN,{domain}"


def normalize_ipcidr_line(raw: str, source_name: str, line_no: int) -> tuple[str, str]:
    """Return (mihomo_text_cidr, shadowrocket_rule) for an IP-CIDR entry."""
    line = raw.strip()
    if line.startswith(("IP-CIDR,", "IP-CIDR6,")):
        parts = [p.strip() for p in line.split(",")]
        cidr_str = parts[1]
    elif "," in line:
        raise ValueError(
            f"{source_name}:{line_no}: unsupported rule in ipcidr bundle '{raw}'"
        )
    else:
        cidr_str = line

    net = ipaddress.ip_network(cidr_str, strict=False)
    prefix = "IP-CIDR6" if net.version == 6 else "IP-CIDR"
    canonical = str(net)
    return canonical, f"{prefix},{canonical},no-resolve"


def parse_lines(content: str, behavior: str, source_name: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for idx, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue
        if behavior == "domain":
            items.append(normalize_domain_line(stripped, source_name, idx))
        elif behavior == "ipcidr":
            items.append(normalize_ipcidr_line(stripped, source_name, idx))
        else:
            raise ValueError(f"Unsupported behavior '{behavior}' for {source_name}")
    return items


def domain_patterns_overlap(
    left: list[str], left_suffix: bool, right: list[str], right_suffix: bool
) -> bool:
    """Compare reversed labels for exact, suffix and single-label wildcard rules."""
    if (len(left) < len(right) and not left_suffix) or (
        len(right) < len(left) and not right_suffix
    ):
        return False
    return all(a == b or a == "*" or b == "*" for a, b in zip(left, right))


def check_conflicts(compiled: dict[str, list[tuple[str, str]]]) -> None:
    proxy_groups = ("custom-proxy", "custom-ai")
    incompatible = {
        "custom-direct": (*proxy_groups, "custom-reject"),
        "private": (*proxy_groups, "custom-reject"),
        "custom-reject": proxy_groups,
    }
    patterns = {}
    for group in (*incompatible, *proxy_groups):
        # Shadowrocket's output maps both "+." and "." to DOMAIN-SUFFIX.
        # Check the apex too, since a conflict on either client matters.
        patterns[group] = []
        for rule, sr_rule in sorted(compiled.get(group, [])):
            kind, domain = sr_rule.split(",", 1)
            patterns[group].append((rule, domain.split(".")[::-1], kind == "DOMAIN-SUFFIX"))

    for first_group, other_groups in incompatible.items():
        for second_group in other_groups:
            for first_rule, first_labels, first_suffix in patterns[first_group]:
                for second_rule, second_labels, second_suffix in patterns[second_group]:
                    if domain_patterns_overlap(
                        first_labels, first_suffix, second_labels, second_suffix
                    ):
                        raise RuntimeError(
                            f"Rule conflict between '{first_group}' ({first_rule}) "
                            f"and '{second_group}' ({second_rule})"
                        )


def find_mihomo_bin(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    return shutil.which("mihomo") or shutil.which("clash-meta")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build proxy rulesets for Mihomo & Shadowrocket.")
    parser.add_argument("--offline", action="store_true", help="Skip fetching upstream rule URLs.")
    parser.add_argument("--require-mrs", action="store_true", help="Fail if mihomo binary is missing.")
    parser.add_argument("--mihomo-bin", default=None, help="Path to mihomo binary for .mrs compilation.")
    args = parser.parse_args()

    sources = load_sources(ROOT / "sources.yaml")
    mihomo_bin = find_mihomo_bin(args.mihomo_bin)
    if args.require_mrs and not mihomo_bin:
        print("ERROR: --require-mrs specified, but mihomo binary was not found.", file=sys.stderr)
        return 1

    dist_dir = ROOT / "dist"
    mihomo_dir = dist_dir / "mihomo"
    sr_dir = dist_dir / "shadowrocket"
    override_dir = dist_dir / "override"
    tpl_dir = dist_dir / "templates"

    compiled: dict[str, list[tuple[str, str]]] = {}

    for bundle in sources.get("bundles", []):
        name = bundle["name"]
        behavior = bundle["behavior"]
        seen: dict[str, str] = {}

        local_rel = bundle.get("local")
        if local_rel:
            local_path = ROOT / local_rel
            for m_rule, sr_rule in parse_lines(
                local_path.read_text(encoding="utf-8"), behavior, str(local_rel)
            ):
                seen.setdefault(m_rule, sr_rule)

        if not args.offline:
            for url in bundle.get("upstream") or []:
                print(f"Fetching upstream for {name}: {url}")
                content = fetch_url(url)
                for m_rule, sr_rule in parse_lines(content, behavior, url):
                    seen.setdefault(m_rule, sr_rule)

        compiled[name] = sorted(seen.items(), key=lambda kv: kv[0])

    check_conflicts(compiled)

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    for d in (mihomo_dir, sr_dir, override_dir, tpl_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {"mrs_compiled": bool(mihomo_bin), "bundles": {}}

    for name, pairs in compiled.items():
        behavior = next(b["behavior"] for b in sources["bundles"] if b["name"] == name)
        txt_path = mihomo_dir / f"{name}.txt"
        list_path = sr_dir / f"{name}.list"

        txt_lines = [m for m, _ in pairs]
        sr_lines = [s for _, s in pairs]

        txt_path.write_text("\n".join(txt_lines) + ("\n" if txt_lines else ""), encoding="utf-8")
        list_path.write_text("\n".join(sr_lines) + ("\n" if sr_lines else ""), encoding="utf-8")

        if mihomo_bin:
            mrs_path = mihomo_dir / f"{name}.mrs"
            cmd = [mihomo_bin, "convert-ruleset", behavior, "text", str(txt_path), str(mrs_path)]
            subprocess.run(cmd, check=True)

        manifest["bundles"][name] = {
            "behavior": behavior,
            "count": len(pairs),
        }
        print(f"Built {name}: {len(pairs)} rules")

    # Copy client entry files to dist
    shutil.copy2(ROOT / "override" / "mihomo-override.js", override_dir / "mihomo-override.js")
    shutil.copy2(ROOT / "templates" / "mihomo-base.yaml", tpl_dir / "mihomo-base.yaml")
    shutil.copy2(ROOT / "templates" / "shadowrocket.conf", sr_dir / "shadowrocket.conf")

    (dist_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Done. Output written to {dist_dir} (mrs_compiled={bool(mihomo_bin)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
