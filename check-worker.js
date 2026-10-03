// Cloudflare Worker: SSTP 节点连通性检测端 (极简版,无任何 import)
// 部署后记下域名,填到 GitHub 仓库 Variables 的 CHECK_WORKER
// 用法: https://你的域名/check?host=1.2.3.4&port=443
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
    try {
      const c = new AbortController();
      const timer = setTimeout(() => c.abort(), 8000);
      await fetch('https://' + host + ':' + port + '/', {
        method: 'HEAD',
        signal: c.signal,
      }).catch(function () {});
      clearTimeout(timer);
      return Response.json({ ok: true, ms: Date.now() - t0, mode: 'https' });
    } catch (e) {
      return Response.json({ ok: false, ms: Date.now() - t0, error: String(e).slice(0, 120) });
    }
  },
};
