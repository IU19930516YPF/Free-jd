#!/usr/bin/env python3
"""VPN Gate SSTP 节点抓取 + Cloudflare Worker 测速 + 生成 Pages 站点.

环境变量:
  CHECK_WORKER   检测 Worker 地址,例: https://xxx.workers.dev/check
  EDGE_HOSTS     edgetunnel 优选入口,逗号分隔,例: a.com:443,b.com:443
  EDT_UUID       edgetunnel 的 UUID
  EDT_DOMAIN     edgetunnel 绑定的节点域名
  EDT_FINGERPRINT  指纹,默认 chrome
  CHECK_CONCURRENCY 并发数,默认 32
  CHECK_TIMEOUT    单节点超时秒,默认 90 (Worker 侧约 8s,此处为整体兜底)
"""
import base64
import csv
import html
import io
import os
import sys
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

VPNGATE_API = "http://www.vpngate.net/api/iphone/"

WORKER_CHECK_URL = os.environ.get("CHECK_WORKER") or "https://你的Worker域名/check"
CHECK_CONCURRENCY = int(os.environ.get("CHECK_CONCURRENCY", "32"))

EDGE_HOSTS = [h.strip() for h in os.environ.get(
    "EDGE_HOSTS", "").split(",") if h.strip()]
EDT_UUID = os.environ.get("EDT_UUID", "")
EDT_DOMAIN = os.environ.get("EDT_DOMAIN", "")
EDT_FINGERPRINT = os.environ.get("EDT_FINGERPRINT", "chrome")


def fetch_vpngate():
    req = urllib.request.Request(VPNGATE_API, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(3)
    print(f"抓取 VPN Gate 失败: {last}", file=sys.stderr)
    return None


def parse_nodes(text):
    nodes = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("*"):
            continue
        parts = line.split(",", 14)
        if len(parts) < 14:
            continue
        try:
            nodes.append({
                "hostname": parts[0],
                "ip": parts[1],
                "score": int(parts[2] or 0),
                "ping": int(parts[3] or 9999),
                "speed": int(parts[4] or 0),  # bps
                "country": parts[5] or parts[6],
                "sessions": int(parts[7] or 0),
                "uptime": int(parts[8] or 0),
                "operator": parts[12],
            })
        except ValueError:
            continue
    return nodes


def check_one(node):
    """经由 Worker 检测单个节点 443 连通性,返回延迟 ms / None."""
    if not WORKER_CHECK_URL or "你的Worker域名" in WORKER_CHECK_URL:
        return None  # 未配置 Worker,跳过实测
    q = urllib.parse.urlencode({"host": node["ip"], "port": "443"})
    req = urllib.request.Request(f"{WORKER_CHECK_URL}?{q}", headers={
        "User-Agent": "vpngate-check/1.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            import json
            data = json.loads(r.read().decode())
            if data.get("ok"):
                return data.get("ms", int((time.time() - t0) * 1000))
    except Exception:
        pass
    return None


def build_vless_sub():
    if not (EDT_UUID and EDT_DOMAIN):
        return ""
    links = []
    hosts = EDGE_HOSTS or [f"{EDT_DOMAIN}:443"]
    for i, h in enumerate(hosts):
        addr, _, port = h.partition(":")
        port = port or "443"
        params = urllib.parse.urlencode({
            "encryption": "none", "security": "tls", "sni": EDT_DOMAIN,
            "fp": EDT_FINGERPRINT, "type": "ws", "host": EDT_DOMAIN,
            "path": "/?ed=2048",
        })
        name = urllib.parse.quote(f"edgetunnel-{i+1}")
        links.append(
            f"vless://{EDT_UUID}@{addr}:{port}?{params}#{name}")
    raw = "\n".join(links)
    return base64.b64encode(raw.encode()).decode()


def fmt_speed(bps):
    mb = bps / 1e6
    return f"{mb:.1f} Mbps" if mb >= 1 else f"{bps/1e3:.0f} Kbps"


def build_page(nodes, updated):
    rows = []
    for n in nodes:
        ms = n.get("check_ms")
        ms_txt = f"{ms} ms" if ms is not None else "-"
        rows.append(
            f"<tr><td>{html.escape(n['country'])}</td>"
            f"<td><code>{html.escape(n['ip'])}</code></td>"
            f"<td>{html.escape(n['hostname'][:28])}</td>"
            f"<td>{n['ping']} ms</td><td>{fmt_speed(n['speed'])}</td>"
            f"<td>{ms_txt}</td><td>{n['sessions']}</td></tr>")
    body = "\n".join(rows) if rows else \
        '<tr><td colspan="7">暂无数据,稍后重试</td></tr>'
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VPN Gate SSTP 节点</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:0 auto;padding:16px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:6px 8px;font-size:13px}}
th{{background:#f5f5f5}}code{{font-size:12px}}</style></head>
<body><h2>VPN Gate SSTP 节点 (自动测速)</h2>
<p>更新时间: {updated} · 共 {len(nodes)} 个节点 · SSTP 端口 443,用户名/密码 vpn</p>
<p><a href="hosts.txt">hosts.txt</a> · <a href="sub.txt">订阅 sub.txt</a></p>
<table><tr><th>国家/地区</th><th>IP</th><th>主机名</th><th>官方Ping</th>
<th>带宽</th><th>实测延迟</th><th>会话数</th></tr>
{body}</table></body></html>
"""


def main():
    os.makedirs("public", exist_ok=True)
    text = fetch_vpngate()
    nodes = parse_nodes(text) if text else []
    print(f"抓到 {len(nodes)} 个节点,开始测速…")
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=CHECK_CONCURRENCY) as ex:
        futs = {ex.submit(check_one, n): n for n in nodes}
        for f in as_completed(futs):
            futs[f]["check_ms"] = f.result()
    # 排序:实测通的优先,按延迟;没实测的按官方 ping
    nodes.sort(key=lambda n: (n.get("check_ms") is None,
                              n.get("check_ms") or n["ping"]))
    nodes = nodes[:100]
    print(f"测速完成,用时 {time.time()-t_start:.0f}s,可用 {sum(1 for n in nodes if n.get('check_ms'))} 个")
    bj = timezone(timedelta(hours=8))
    updated = datetime.now(bj).strftime("%Y-%m-%d %H:%M CST")
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(build_page(nodes, updated))
    with open("public/hosts.txt", "w", encoding="utf-8") as f:
        for n in nodes:
            f.write(f"{n['ip']} {n['hostname']}\n")
    with open("public/sub.txt", "w", encoding="utf-8") as f:
        f.write(build_vless_sub())
    # sstp 明文节点清单,方便手动拨号
    with open("public/sstp.txt", "w", encoding="utf-8") as f:
        for n in nodes:
            f.write(f"{n['ip']}:443 vpn/vpn #{n['country']} {n['ping']}ms\n")
    print("已生成 public/index.html, hosts.txt, sub.txt, sstp.txt")


if __name__ == "__main__":
    main()
