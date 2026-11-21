# proxy-ruleset

极简、防泄露、可跨端复用的 Mihomo（Clash Party / FlClash / CMFA）与 Shadowrocket（iOS 小火箭）统一分流规则与 DNS 仓库。

详细工程设计与防泄露原理见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 核心特性

- **换配置零折腾**：导入任何新机场订阅后，无需手动改规则与 DNS；且**零节点命名假设**，不依赖机场节点命名规范。
- **极简 4 策略组**：`🚀 节点选择`、`🤖 AI 专用`（默认跟随主力，可按需单选非港节点）、`🎯 全球直连`、`🛑 广告拦截`。
- **默认防代理/DNS 泄露**：
  - Mihomo 端：`fake-ip` + `respect-rules: true` + 四层隔离 DNS（境外 DoH 强制走代理出口）+ `sniffer` + 默认关闭 IPv6。
  - Shadowrocket 端：禁用系统直连回落、开启 DoH、关闭 IPv6、所有 `IP-CIDR` / `GEOIP` 强制 `,no-resolve`。
- **单一规则源，双端自动编译**：只需维护 `rules/` 下的纯文本规则与 `sources.yaml`，GitHub Actions 每日自动编译为 Mihomo `.mrs` 与 Shadowrocket `.list`。

---

## 快速接入（导入一次，长期复用）

> 首次使用前，请先将 `master` 分支推送到 GitHub，等待 `Build and Publish Rulesets` Action 运行完成（会自动生成 `dist` 分支产物）。

### 1. 桌面端（Clash Party）& 安卓端（FlClash）
1. 正常导入你自己的机场订阅（保留原订阅的剩余流量与到期时间提示）。
2. 打开客户端 **「覆写（Override / Script）」** -> **「远程导入」**，填入脚本链接并开启定期更新：
   ```text
   https://cdn.jsdelivr.net/gh/xiangp152/proxy-ruleset@dist/override/mihomo-override.js
   ```
3. 打开该脚本的 **「全局启用」**（或在对应订阅上勾选应用），重载配置即可生效。

*(注：若使用 CMFA 或纯命令行 Mihomo，可使用 [mihomo-base.yaml](templates/mihomo-base.yaml)，只需替换其中 `proxy-providers.MySub.url` 一行。)*

### 2. iOS 端（Shadowrocket 小火箭）
1. 正常导入你的机场订阅节点。
2. 打开底部 **「配置（Config）」** -> 右上角 `+` -> 粘贴配置链接并下载：
   ```text
   https://cdn.jsdelivr.net/gh/xiangp152/proxy-ruleset@dist/shadowrocket/shadowrocket.conf
   ```
3. 点击该配置选择 **「使用配置」**，并将首页 **「全局路由」** 设为 **「配置」**。
4. 首页选中任意节点即作为主力出口；如需为 AI 单独指定线路，在配置策略组里调整 `🤖 AI 专用` 即可。

---

## 日常修改规则

1. 编辑 `rules/` 下对应文件：
   - `rules/custom-direct.list`：强制直连域名（网银、NAS、国内误杀站）
   - `rules/custom-direct-ip.list`：强制直连 IP / CIDR
   - `rules/custom-proxy.list`：强制走代理域名（测漏站、GitHub、Telegram 等）
   - `rules/custom-ai.list`：AI 补充域名（构建时会自动与上游 `MetaCubeX category-ai-!cn` 合并去重）
   - `rules/custom-reject.list`：自定义屏蔽域名
2. 推送到 `master` 后，GitHub Actions 会自动校验冲突、重新编译并更新 `dist` 分支。

本地校验构建（纯 Python 标准库即可运行，不依赖第三方包）：

```bash
python3 scripts/build.py --offline
```

---

## 代理与 DNS 泄露自检

配置启用后，建议通过以下站点验证：
1. `https://dnsleaktest.com`（运行 Extended Test）：确认仅出现代理节点所在地或上游境外 DNS，无国内运营商 DNS。
2. `https://ipleak.net` / `https://browserleaks.com/webrtc`：确认出口 IP 与 DNS 均属于代理节点，无真实 IPv4/IPv6 泄露。
3. 在客户端日志中确认 `chatgpt.com` 命中 `🤖 AI 专用`，国内站点命中 `🎯 全球直连` / `DIRECT`。
