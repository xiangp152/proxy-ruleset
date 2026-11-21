# proxy-ruleset

开箱即用的极简代理分流配置：导入一次即可，之后更换任何机场订阅都不需要重新折腾规则。

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
3. 将该脚本设为 **「全局启用」**（或在当前订阅上勾选使用），重载配置即可。
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
