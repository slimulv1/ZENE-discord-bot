# Hướng dẫn đọc code Zene Bot — Tiếng Việt + 日本語

> Ghi chú dễ hiểu cho người mới lấy code đọc. **Mã nguồn, biến, hàm, file path giữ tiếng Anh;**
> chỉ *comment / ghi chú* viết **Tiếng Việt + Tiếng Nhật** (mỗi ý 2 dòng).
> **コード / 識別子 / ファイルパスは英語のまま。コメントだけがベトナム語と日本語。**

---

## Cấu trúc thư mục / ディレクトリ構成

```
zene_core/
├── bot.py           # ZeneBot: boot, load cog, event, safe_send — Bot本体
├── supervisor.py    # Supervisor: restart backoff + health /health /ready /live — プロセス監督
├── config.py        # Config.from_env(): đọc env + validate — 設定を env から読む
├── net.py           # shared aiohttp session + retry + circuit breaker — 共有HTTP層
├── resilience.py    # RetryPolicy, CircuitBreaker, TokenBucket, with_timeout — 堅牢化の道具
├── state.py         # RuntimeState: shutdown/restart flags — 実行時状態
├── assets.py        # AssetRegistry: file assets, max size — アセット管理
├── content.py       # memes.json load + triggers + hot-reload — メモ定義 + ホットリロード
├── triggers.py      # TriggerRegistry — トリガー登録
├── pagination.py    # Discord pagination helper — ページング補助
├── dashboard.py     # DASHBOARD_HTML for /status — ダッシュボードHTML
├── logging_setup.py # logging config — ログ設定
├── avwiki.py        # Vietnamese translation + wiki fetch — 翻訳 + データ取得
├── cogs/            # các cog Discord — Discordコグ群
│   ├── embedfix.py  # tính năng chính: social link → embed — ソーシャルリンク埋め込み
│   ├── conversation.py / ops.py / digest.py / ...
└── embedfix/        # lớp logic embed — 埋め込みのロジック層
    ├── models.py        # LinkContext, ProbeResult — データモデル
    ├── modifiers.py     # modifier 文 trước link (spoiler/translate...) — 修飾語解析
    ├── guards.py        # SSRF, canonical URL, mirror rewrite — URL検証 + 安全ガード
    ├── router.py        # domain → adapter route — ドメイン→アダプタルーティング
    ├── adapters.py      # MetaAdapter, YtDlpAdapter, _MetaParser — 汎用メタアダプタ
    ├── proxy_adapters.py# FxEmbed/Ifx/OgInstagram/Facebed/TikTok... — 公式API代替プロキシ
    └── views.py         # Components V2: MediaGallery, CarouselView, CTA — UI部品
```

---

## Luồng chính embed social / ソーシャル埋め込みの流れ

```
on_message                     # user gửi link — ユーザーがリンクを送信
  → parse_modifiers            # đọc spoiler/translate/hide_quote/言語 — 修飾語を解析
  → canonicalize               # SSRF + sửa link (shortener, tracking, redirect ≤5) — URL正規化
  → queue                      # asyncio.Queue + semaphore worker — キュー + ワーカー
  → _embed_hints               # tái dùng media Discord native — Discordネイティブ埋め込み再利用
  → _probe                     # route_for + adapters (parallel IG/TikTok) + cache — アダプタで探索
  → _process                   # cache hit, NSFW, translate, spoiler, CTA — 整形 + 送信
  → build_view                 # Components V2 MediaGallery / CarouselView + CTA link button — UI構築
  → channel.send               # safe_send — 送信
```

---

## Từ vựng code dễ nhầm / 紛らわしい用語

| Từ (code) | Nghĩa Tiếng Việt | 日本語の意味 |
|---|---|---|
| `ProbeResult` | kết quả dò 1 link (kind, title, media...) | リンク調査結果 |
| `kind` | loại: image/video/gallery/link/none | 種類 |
| `media_urls` | URL ảnh/video trực tiếp hiển thị được | 直メディアURL |
| `media_hints` | media Discord native đã lấy sẵn | Discordの既存メディア |
| `spoiler` | ẩn ảnh đến khi user bấm | ネタバレ隠し |
| `nsfw` | nội dung nhạy cảm (None=không biết, strict coi như NSFW) | 年齢制限コンテンツ |
| `hide_quote` | không hiện caption/text gốc | 引用を隠す |
| `rewrite_social_link` | đổi sang mirror embed (fxTikTok/oginstagram...) | ミラーURLへ書き換え |
| `CircuitBreaker` | ngắt mạch khi API lỗi liên tiếp | サーキットブレーカー |
| `OPEN/HALF_OPEN/CLOSED` | trạng thái breaker | ブレーカー状態 |
| `RetryPolicy` | thử lại có backoff + jitter | 指数バックオフ + ジッター付き再試行 |
| `backoff` | chờ lâu dần rồi thử lại | バックオフ |
| `media_timeout` | timeout tải 1 link (25s) | メディア取得タイムアウト |
| `_NEG_CACHE_TTL` | TTL cache lỗi (`ZENE_MEDIA_NEG_CACHE_TTL`, 300s) | 失敗キャッシュTTL |
| `media_cta` | nút link "Xem bài gốc" dưới media | 「Xem bài gốc」リンクボタン |
| `send_cta` | bật/tắt nút CTA khi dựng view | CTAボタンの表示切替 |
| `media_spoiler_default_channels` | kênh spoiler mặc định | 既定でネタバレのチャンネル |
| `safe_send` | gửi tin không bao giờ ném lỗi ra event | 例外を外に出さない送信 |
| `CarouselView` | ảnh 1 + ◀/▶, đếm `-# n/N` | 1枚 + 前/次ボタン |
| `MAX_ITEMS = 9` | tối đa 9 ảnh, lưới 3x3 đều (không crop) | 最大9枚, 3x3格子, 切り抜きなし |
| `cmd` / `mods` | modifier `spoiler`,`~`,`文`,`^`,`lang:` | 修飾語 |
| `LayoutView` | Discord Components V2 container | Components V2 コンテナ |
| `supervised restart` | restart backoff jitter + max_restarts | 監視下再起動 |
| `stable_seconds` | sau bao nhiêu ổn định thì reset failure | 安定後リセット |

---

## Cấu hình quan trọng (env) / 重要な環境変数

- `ZENE_MEDIA_TIMEOUT` (25s) timeout 1 link — メディア取得タイムアウト
- `ZENE_MEDIA_CACHE_TTL` (3600) cache kết quả — 結果キャッシュTTL
- `ZENE_MEDIA_DIRECT_VIDEO_TTL` (300) cache video — 動画キャッシュTTL
- `ZENE_MEDIA_NEG_CACHE_TTL` (300, min 60) cache lỗi — 失敗キャッシュTTL
- `ZENE_MEDIA_CTA` (true) nút "Xem bài gốc" — CTAボタン
- `ZENE_MEDIA_SPOILER_DEFAULT_CHANNELS` (rỗng) kênh spoiler — ネタバレチャンネルID
- `ZENE_MEDIA_MAX_LINKS`, `ZENE_MEDIA_WORKERS`, `ZENE_MEDIA_STRICT_NSFW`, `ZENE_MEDIA_MODE`

Xem `docs/SOCIAL_MEDIA.md` (embed) và `config.example.txt`.
Xem `docs/SOCIAL_MEDIA.md`（埋め込み）と `config.example.txt`。

---

## Cách chạy / 実行方法

```bash
# chạy bot (.venv cần đã có deps; token trong .env, KHÔNG hiện token)
.venv\Scripts\python.exe run.py
# chạy tests (unittest, không cần pytest)
.venv\Scripts\python.exe -m unittest tests.test_embedfix
# quét secret trước commit
powershell -NoProfile -ExecutionPolicy Bypass -File scan-staged-secrets.ps1 -Scope Staged
```

**Không sửa code mà không chạy tests. コードを変えたらテストを通す。**
**Không commit secret/`.env*`. シークレット・`.env*`はコミット禁止。**
