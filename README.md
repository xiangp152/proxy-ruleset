# proxy-ruleset

适用于 Mihomo 客户端和 Shadowrocket 的极简代理分流配置。

---

## 用在哪些客户端？

| 客户端 | 适用平台 | 接入方式 |
| :--- | :--- | :--- |
| **Clash Party** | macOS / Windows / Linux | 远程全局覆写脚本 |
| **FlClash** | Android / Windows / macOS / Linux | 远程全局覆写脚本 |
| **Shadowrocket（小火箭）** | iOS | 扫码导入 / 远程配置文件 |

---

## 怎么用？

### 1. Clash Party / FlClash（桌面端 & 安卓端）

1. 正常导入你的机场订阅。
2. 打开客户端 **「覆写（Override / Script）」→「远程导入」**，粘贴以下链接并开启自动更新：
   ```text
   https://cdn.jsdelivr.net/gh/xiangp152/proxy-ruleset@dist/override/mihomo-override.js
   ```
3. Clash Party 将脚本设为 **「全局启用」**。FlClash 在当前订阅上选用该脚本。完成后重载配置。
4. 建议在客户端首页开启 **TUN 模式**。

### 2. Shadowrocket（iOS 小火箭）

1. 正常导入你的机场订阅节点。
2. 导入配置（二选一）：
   - **扫码导入（推荐）**：用 iPhone 相机或小火箭首页左上角「扫一扫」扫描下方二维码，按提示下载并使用配置：

     <img src="assets/shadowrocket-qr.png" width="180" alt="Shadowrocket 配置导入二维码" />

   - **手动导入**：打开底部 **「配置」→ 右上角 `+`**，粘贴链接下载并选择 **「使用配置」**：
     ```text
     https://cdn.jsdelivr.net/gh/xiangp152/proxy-ruleset@dist/shadowrocket/shadowrocket.conf
     ```
3. 回到首页，将 **「全局路由」** 设为 **「配置」** 即可。

---

## 日常怎么选节点？

配置启用后，策略组里只会看到这 4 个常用分组：

- **`🚀 节点选择`**：日常主力出口，在里面选你平时常用的节点即可。
- **`🤖 AI 专用`**：默认自动跟随 `🚀 节点选择`；如果你的主力节点是香港，可以在这里单独为 ChatGPT / Claude / Gemini 等选一个美国、日本或新加坡节点。
- **`🎯 全球直连`**：国内网站与直连流量，无需手动操作。
- **`🛑 广告拦截`**：默认拦截；如果某个网页被误拦打不开，临时点进去切到 `DIRECT` 即可放行。

## 已知限制

- **国内网站或 App 的部分功能可能走代理。** 未命中域名规则时，Mihomo 的国内 IP 规则带有 `no-resolve`，因此不会专门解析域名来判断 IP 归属。若没有可供匹配的国内 IP，流量会交给主力代理。遇到加载慢或地区识别异常时，可查看连接日志中的目标域名与命中规则。[Mihomo 路由规则](https://wiki.metacubex.one/config/rules/#no-resolve)
- **WebRTC 的 UDP 需要被客户端接管。** 仅开系统代理时，UDP 可能绕过 Mihomo。使用 Clash Party 或 FlClash 时，请确认 TUN 接管了相关流量。进入 Mihomo 规则模式的 UDP 若需要代理，但所选节点不支持 UDP，会被拒绝。按规则直连的国内 STUN 仍可能暴露真实出口 IP。测漏网页显示代理 IP，只能说明该网页的请求走了代理。[Mihomo TUN 文档](https://wiki.metacubex.one/config/inbound/tun/)
- **换订阅后可能需要重新启用覆写。** FlClash 按订阅绑定脚本，新导入的订阅需重新选用。Mihomo 覆写会替换订阅原有的策略组、分流规则和 DNS，引用原策略组的链式代理可能失效。若订阅同时包含内嵌节点和远程节点池，新策略组只纳入内嵌节点。[FlClash 脚本绑定源码](https://github.com/chen08209/FlClash/blob/afe7136002271fd64f098b154e7fff40be721eb8/lib/providers/state/profile.dart#L100-L139)
- **公司内网或 NAS 的域名可能无法解析。** Mihomo 的直连 DNS 默认使用公共 DoH。只在公司 DNS 或家里路由器上注册的域名，可能需要为该域名单独指定内网解析服务器。[Mihomo DNS 配置](https://wiki.metacubex.one/config/dns/#direct-nameserver)
- **Shadowrocket 与 Mihomo 的分流可能不同。** 两端使用不同的国内域名库。例如，Apple 的下载域名 `appldnld.apple.com` 可能在 Shadowrocket 上命中域名直连，在 Mihomo 上则由后续规则决定出口。[Shadowrocket 直连表](https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/direct.txt) · [Mihomo 国内域名表](https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/cn.list)
