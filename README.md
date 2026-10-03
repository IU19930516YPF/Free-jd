# Free-jd

VPN Gate SSTP 免费节点自动抓取 + Cloudflare Worker 测速 + GitHub Pages 订阅页。

## 文件

- `vpngate.py` — 抓取 VPN Gate API,经 Worker 测速,生成 `public/` 静态页
- `check-worker.js` — Cloudflare Worker 检测端代码
- `.github/workflows/check.yml` — 每 30 分钟自动运行 + 部署 Pages

## 配置 (Settings → Secrets and variables → Actions → Variables)

| 变量 | 说明 |
|---|---|
| `CHECK_WORKER` | 检测 Worker 地址,如 `https://xxx.workers.dev/check` |
| `EDGE_HOSTS` | edgetunnel 优选入口,逗号分隔,如 `a.com:443,b.com:443` |
| `EDT_UUID` | edgetunnel 的 UUID |
| `EDT_DOMAIN` | edgetunnel 绑定的节点域名 |

## 输出

- `index.html` — 节点列表页
- `hosts.txt` / `sstp.txt` — 节点清单
- `sub.txt` — edgetunnel 订阅 (base64)
