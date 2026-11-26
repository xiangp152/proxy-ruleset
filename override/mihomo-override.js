// Mihomo 全局覆写脚本（适用于 Clash Party / FlClash 等基于 Mihomo 内核的客户端）
// 设计原则：
// 1. 零节点命名假设：不写死节点名、不按地区正则猜测，兼容任何机场订阅
// 2. 极简 4 策略组：🚀 节点选择 / 🤖 AI 专用 / 🎯 全球直连 / 🛑 广告拦截
// 3. 防泄露 DNS：fake-ip + respect-rules + 四层隔离 + 关闭默认 IPv6 + Sniffer

// 个人直连配置。在客户端导入的本地副本里填写，去掉需要使用的示例行前的 //。
const LOCAL_DIRECT = {
  // 标准 Mihomo 规则，优先匹配。域名规则沿用现有 DNS 配置。
  rules: [
    // "DOMAIN,git.corp.example.com,DIRECT",                    // 只匹配这个域名
    // "DOMAIN-SUFFIX,corp.example.com,DIRECT",                 // 域名本身和所有下级子域
    // "DOMAIN-WILDCARD,dev-*.corp.example.com,DIRECT",         // 按 * 或 ? 匹配域名
    // "IP-CIDR,10.20.0.15/32,DIRECT,no-resolve",                // 单个 IPv4 地址
    // "IP-CIDR,10.30.0.0/16,DIRECT,no-resolve",                 // IPv4 网段
    // "IP-CIDR6,fd00:1234::/48,DIRECT,no-resolve",              // IPv6 网段
  ],
  // 固定 IP 映射，同时直连。Mihomo 本地应答地址查询，不向上游查询。
  hosts: {
    // "git.corp.example.com": "10.20.0.15",   // 精确域名
    // "*.dev.corp.example.com": "10.20.0.16", // 仅匹配一级子域
    // "+.lab.corp.example.com": "10.20.0.17", // 域名本身和所有下级子域
  },
  // IP 直连的简写，支持单个地址和 CIDR 网段。
  ips: [
    // "10.20.0.15",
    // "10.30.0.0/16",
  ],
};

const CDN_BASE = "https://cdn.jsdelivr.net/gh/xiangp152/proxy-ruleset@dist";
const META_BASE = "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo";

// 仅过滤常见的订阅提示性假节点（避免它们被当成真实出口），但保留订阅卡片的流量/到期信息显示
const INFO_NODE_RE = /剩余流量|套餐到期|到期时间|距离下次重置|官网|发布页|Traffic|Expire|Reset/i;

function main(config) {
  const rawProxies = (config.proxies || []).map((p) => p.name).filter(Boolean);
  const filteredProxies = rawProxies.filter((name) => !INFO_NODE_RE.test(name));
  const proxyNames = filteredProxies.length > 0 ? filteredProxies : rawProxies;

  const providerNames = Object.keys(config["proxy-providers"] || {});
  if (proxyNames.length === 0 && providerNames.length === 0) {
    return config;
  }

  const localDomains = Object.keys(LOCAL_DIRECT.hosts || {});
  const localExactDomains = [];
  const localDomainPatterns = [];
  for (const domain of localDomains) {
    const isPattern = domain.startsWith("+.") || domain.startsWith(".") || domain.includes("*");
    (isPattern ? localDomainPatterns : localExactDomains).push(domain);
  }
  const localCidrs = (LOCAL_DIRECT.ips || []).map((ip) => {
    if (ip.includes("/")) return ip;
    const prefixLength = ip.includes(":") ? 128 : 32;
    return `${ip}/${prefixLength}`;
  });

  // 1. 构建极简 4 策略组（若通过 proxy-providers 导入节点则自动绑定 use）
  const mainGroup = {
    name: "🚀 节点选择",
    type: "select",
  };
  const aiGroup = {
    name: "🤖 AI 专用",
    type: "select",
  };

  if (proxyNames.length > 0) {
    mainGroup.proxies = [...proxyNames];
    // 默认第 1 项跟随「🚀 节点选择」，开箱零心智负担；同时列出全部节点供按需单独锁定
    aiGroup.proxies = ["🚀 节点选择", ...proxyNames];
  } else {
    mainGroup.use = [...providerNames];
    aiGroup.proxies = ["🚀 节点选择"];
    aiGroup.use = [...providerNames];
  }

  config["proxy-groups"] = [
    mainGroup,
    aiGroup,
    {
      name: "🎯 全球直连",
      type: "select",
      proxies: ["DIRECT"],
    },
    {
      name: "🛑 广告拦截",
      type: "select",
      proxies: ["REJECT", "DIRECT"],
    },
  ];

  // 2. 基础防泄露与性能开关
  config["ipv6"] = false;
  config["unified-delay"] = true;
  config["tcp-concurrent"] = true;
  config["profile"] = {
    ...(config["profile"] || {}),
    "store-selected": true,
    "store-fake-ip": true,
  };

  // 3. 域名嗅探（防止直连 IP 请求绕过域名规则与 DNS 分流）
  config["sniffer"] = {
    enable: true,
    "force-dns-mapping": true,
    "parse-pure-ip": true,
    "override-destination": true,
    sniff: {
      HTTP: { ports: [80, "8080-8880"], "override-destination": true },
      TLS: { ports: [443, 8443] },
      QUIC: { ports: [443, 8443] },
    },
    "skip-domain": ["Mijia Cloud", "+.push.apple.com", ...localDomains],
  };
  if (localCidrs.length) {
    config.sniffer["skip-dst-address"] = localCidrs;
  }

  // 4. 规则集定义（全面采用 .mrs 二进制规则集，毫秒级加载）
  config["rule-providers"] = {
    custom_direct: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${CDN_BASE}/mihomo/custom-direct.mrs`,
      path: "./ruleset/custom-direct.mrs",
      interval: 600,
    },
    custom_direct_ip: {
      type: "http",
      behavior: "ipcidr",
      format: "mrs",
      url: `${CDN_BASE}/mihomo/custom-direct-ip.mrs`,
      path: "./ruleset/custom-direct-ip.mrs",
      interval: 600,
    },
    custom_proxy: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${CDN_BASE}/mihomo/custom-proxy.mrs`,
      path: "./ruleset/custom-proxy.mrs",
      interval: 600,
    },
    custom_ai: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${CDN_BASE}/mihomo/custom-ai.mrs`,
      path: "./ruleset/custom-ai.mrs",
      interval: 600,
    },
    custom_reject: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${CDN_BASE}/mihomo/custom-reject.mrs`,
      path: "./ruleset/custom-reject.mrs",
      interval: 600,
    },
    private: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${META_BASE}/geosite/private.mrs`,
      path: "./ruleset/private.mrs",
      interval: 86400,
    },
    cn_domain: {
      type: "http",
      behavior: "domain",
      format: "mrs",
      url: `${META_BASE}/geosite/cn.mrs`,
      path: "./ruleset/cn_domain.mrs",
      interval: 86400,
    },
    cn_ip: {
      type: "http",
      behavior: "ipcidr",
      format: "mrs",
      url: `${META_BASE}/geoip/cn.mrs`,
      path: "./ruleset/cn_ip.mrs",
      interval: 86400,
    },
  };
  if (localDomainPatterns.length) {
    // 使用 Mihomo 的域名集合，让路由和 hosts 使用相同的 Clash 通配符。
    config["rule-providers"].local_direct_hosts = {
      type: "inline",
      behavior: "domain",
      payload: localDomainPatterns,
    };
  }

  // 5. 防泄露 DNS（与上面的 rule-providers 严格联动）
  const domesticDoH = [
    "https://dns.alidns.com/dns-query",
    "https://doh.pub/dns-query",
  ];
  const proxyDoH = [
    "https://cloudflare-dns.com/dns-query#🚀 节点选择",
    "https://dns.google/dns-query#🚀 节点选择",
  ];
  const aiDoH = [
    "https://cloudflare-dns.com/dns-query#🤖 AI 专用",
    "https://dns.google/dns-query#🤖 AI 专用",
  ];

  if (localDomains.length) {
    config.hosts = { ...config.hosts, ...LOCAL_DIRECT.hosts };
  }
  config["dns"] = {
    enable: true,
    listen: "0.0.0.0:1053",
    ipv6: false,
    "respect-rules": true,
    "enhanced-mode": "fake-ip",
    "fake-ip-range": "198.18.0.1/16",
    "fake-ip-filter": [
      ...localDomains,
      "+.lan",
      "+.local",
      "localhost.ptlogin2.qq.com",
      "rule-set:private",
      "rule-set:custom_direct",
    ],
    "default-nameserver": ["223.5.5.5", "119.29.29.29"],
    "proxy-server-nameserver": domesticDoH,
    "direct-nameserver": domesticDoH,
    nameserver: proxyDoH,
    "nameserver-policy": {
      // hosts 回答地址查询，其余查询类型直接返回空结果，避免转发公司域名。
      ...Object.fromEntries(localDomains.map((domain) => [domain, "rcode://success"])),
      "rule-set:private": domesticDoH,
      "rule-set:custom_direct": domesticDoH,
      "rule-set:cn_domain": domesticDoH,
      "rule-set:custom_ai": aiDoH,
      "rule-set:custom_proxy": proxyDoH,
    },
  };

  // 6. 重写路由规则（IP 类规则统一加 no-resolve，避免提前触发本地 DNS 解析）
  config["rules"] = [
    ...(LOCAL_DIRECT.rules || []),
    ...localExactDomains.map((domain) => `DOMAIN,${domain},DIRECT`),
    ...(localDomainPatterns.length ? ["RULE-SET,local_direct_hosts,DIRECT"] : []),
    ...localCidrs.map((cidr) => {
      const type = cidr.includes(":") ? "IP-CIDR6" : "IP-CIDR";
      return `${type},${cidr},DIRECT,no-resolve`;
    }),
    "RULE-SET,custom_direct,🎯 全球直连",
    "RULE-SET,custom_direct_ip,🎯 全球直连,no-resolve",
    "RULE-SET,private,🎯 全球直连",
    "RULE-SET,custom_reject,🛑 广告拦截",
    // 节点不支持 UDP 时，Mihomo 会继续匹配，须在国内直连规则前拒绝。
    "RULE-SET,custom_ai,🤖 AI 专用",
    "RULE-SET,custom_ai,REJECT",
    "RULE-SET,custom_proxy,🚀 节点选择",
    "RULE-SET,custom_proxy,REJECT",
    "RULE-SET,cn_domain,🎯 全球直连",
    "RULE-SET,cn_ip,🎯 全球直连,no-resolve",
    "MATCH,🚀 节点选择",
    "MATCH,REJECT",
  ];

  return config;
}
