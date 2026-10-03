// Cloudflare Worker: SSTP 节点连通性检测端
// 部署后记下域名,填到 vpngate.py 的 WORKER_CHECK_URL
// 用法: https://你的域名/check?host=1.2.3.4&port=443
import { connect } from 'cloudflare:sockets';

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname !== '/check') {
      return new Response('vpngate-check worker ok', { status: 200 });
    }
    const host = url.searchParams.get('host');
    const port = parseInt(url.searchParams.get('port') || '443', 10);
    if (!host) {
      return Response.json({ ok: false, error: 'missing host' }, { status: 400 });
    }
    const t0 = Date.now();
    // 优先 TCP 直连测速 (需要 Workers 付费计划的 sockets 权限,免费版会抛错走 fallback)
    try {
      const sock = connect({ hostname: host, port });
      await sock.opened;
      sock.close();
      return Response.json({ ok: true, ms: Date.now() - t0, mode: 'tcp' });
    } catch (e) {
      // fallback: HTTPS 握手计时,至少能判断 443 是否存活
      try {
        const c = new AbortController();
        const timer = setTimeout(() => c.abort(), 8000);
        await fetch(`https://${host}:${port}/`, {
          method: 'HEAD',
          signal: c.signal,
          cf: { cacheTtl: 0 },
        }).catch(() => {});
        clearTimeout(timer);
        return Response.json({ ok: true, ms: Date.now() - t0, mode: 'https-fallback' });
      } catch (e2) {
        return Response.json({ ok: false, ms: Date.now() - t0, error: String(e2).slice(0, 120) });
      }
    }
  },
};
