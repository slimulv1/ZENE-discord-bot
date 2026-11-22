"""Dependency-free status page served at ``/`` by the health server.

Design inspiration: Uptime Kuma's status page (big single status indicator),
Grafana/EUI guidance (visual hierarchy, cards, calm palette), and Netdata's
grid layout. Everything is inline so it works offline on a Raspberry Pi.
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZENE Bot · Trạng thái</title>
<style>
  :root {
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-2: #263449;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --ok: #22c55e;
    --warn: #f59e0b;
    --bad: #ef4444;
    --border: #334155;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 20px 48px;
    background: var(--bg); color: var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }
  .wrap { max-width: 920px; margin: 0 auto; }
  header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
  h1 { font-size: 1.55rem; margin: 0; letter-spacing: .3px; }
  .subtitle { color: var(--muted); font-size: .9rem; }
  .banner {
    display: flex; align-items: center; gap: 16px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 22px 24px; margin-bottom: 20px;
  }
  .dot { width: 18px; height: 18px; border-radius: 50%; background: var(--warn); flex: none; box-shadow: 0 0 0 6px rgba(245,158,11,.12); }
  .dot.ok { background: var(--ok); box-shadow: 0 0 0 6px rgba(34,197,94,.12); }
  .dot.bad { background: var(--bad); box-shadow: 0 0 0 6px rgba(239,68,68,.12); }
  .banner strong { font-size: 1.2rem; display: block; }
  .banner span { color: var(--muted); font-size: .9rem; }
  h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: 1.2px; color: var(--muted); margin: 26px 0 10px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 16px 18px;
  }
  .card .label { color: var(--muted); font-size: .82rem; }
  .card .value { font-size: 1.7rem; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .card .hint { color: var(--muted); font-size: .75rem; margin-top: 2px; }
  .card.alert .value { color: var(--warn); }
  .chip {
    display: inline-block; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 12px; font-size: .82rem; margin: 2px 4px 2px 0;
  }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  td { padding: 7px 4px; border-bottom: 1px solid var(--border); }
  td:last-child { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
  footer { color: var(--muted); font-size: .8rem; margin-top: 30px; }
  a { color: #7dd3fc; }
  @media (max-width: 560px) { body { padding: 20px 14px 36px; } .card .value { font-size: 1.45rem; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🤖 ZENE Bot</h1>
    <span class="subtitle">Trạng thái hoạt động · tự cập nhật 5 giây</span>
  </header>

  <div class="banner">
    <div class="dot" id="dot"></div>
    <div>
      <strong id="headline">Đang kiểm tra…</strong>
      <span id="detail">Đang lấy dữ liệu từ /health</span>
    </div>
  </div>

  <h2>Số liệu chính</h2>
  <div class="grid">
    <div class="card"><div class="label">Thời gian chạy</div><div class="value" id="uptime">—</div><div class="hint">từ lúc khởi động</div></div>
    <div class="card"><div class="label">Số lần khởi động lại</div><div class="value" id="restarts">—</div><div class="hint">cả crash lẫn restart tay</div></div>
    <div class="card"><div class="label">Meme đã phản hồi</div><div class="value" id="triggers">—</div><div class="hint">trigger tự động</div></div>
    <div class="card"><div class="label">Lệnh asset</div><div class="value" id="assets">—</div><div class="hint">cụm từ gửi ảnh/video</div></div>
  </div>

  <h2>Chi tiết</h2>
  <div class="grid">
    <div class="card">
      <div class="label">Extension lỗi</div>
      <div id="extensions"><span class="chip">đang tải…</span></div>
    </div>
    <div class="card">
      <div class="label">Bộ đếm sự kiện</div>
      <table id="stats"><tr><td>đang tải…</td><td></td></tr></table>
    </div>
  </div>

  <footer>
    Xem dữ liệu thô tại <a href="/health">/health</a> ·
    cập nhật lần cuối <span id="updated">—</span>
  </footer>
</div>

<script>
function fmtUptime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (d) return d + "n " + h + "g";
  if (h) return h + "g " + m + "p";
  if (m) return m + "p " + s + "s";
  return s + "s";
}

async function refresh() {
  try {
    const res = await fetch("/health", { cache: "no-store" });
    const data = await res.json();
    const ok = data.status === "ok";
    const ready = !!data.ready;

    document.getElementById("dot").className = "dot " + (ok ? "ok" : (ready ? "" : "bad"));
    document.getElementById("headline").textContent =
      ok ? "Bot đang chạy tốt" : (ready ? "Bot chạy nhưng cần kiểm tra" : "Bot chưa sẵn sàng");
    document.getElementById("detail").textContent =
      ok ? "Sẵn sàng nhận lệnh" : "Xem chi tiết bên dưới hoặc logs/zene.log";

    document.getElementById("uptime").textContent = fmtUptime(data.uptime_seconds);
    document.getElementById("restarts").textContent = data.restarts ?? 0;
    document.getElementById("triggers").textContent = (data.stats && data.stats.trigger_hits) || 0;
    document.getElementById("assets").textContent = data.asset_commands ?? 0;

    const failed = data.failed_extensions || [];
    document.getElementById("extensions").innerHTML = failed.length
      ? failed.map(x => '<span class="chip">' + x + '</span>').join("")
      : '<span class="chip">Không có lỗi nào 🎉</span>';

    const stats = data.stats || {};
    const rows = Object.entries(stats).sort((a, b) => b[1] - a[1]);
    document.getElementById("stats").innerHTML = rows.length
      ? rows.map(([k, v]) => "<tr><td>" + k + "</td><td>" + v + "</td></tr>").join("")
      : '<tr><td>(chưa có sự kiện)</td><td>0</td></tr>';

    document.getElementById("updated").textContent = new Date().toLocaleTimeString("vi-VN");
  } catch (err) {
    document.getElementById("headline").textContent = "Không đọc được /health";
    document.getElementById("detail").textContent = String(err);
  }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""
