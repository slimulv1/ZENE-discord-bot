# Thiết kế ZENE Social Embed Strategy — X, Instagram, Facebook, TikTok

> Mục tiêu: Chọn nguồn media (trực tiếp nguồn gốc → upload file → rewrite link), sau đó hiển thị
> trên Discord Components V2 với tối ưu UX. Nội dung dựa trên claim/evidence thực tế trong phiên này
> (`memory` + probe HTTP trực tiếp 2026-11-24). Chỉ là thiết kế — code viết theo khi đồng thuận.

---

## 1. Xếp hạngước nhu cầu (≈90 điểm)

| Hạng | Phương án | Điểm |
|---|---|---:|
| P0 | Media trực tiếp có thể trust nguồn bên ngoài, có fallback đầy đủ | 30 |
| P0 | UX: Gallery sinh động (≤9 items), bot *reply* không phải *edit* user message (không có Manage Messages) | 15 |
| P0 | Hướng dẫn từng nền tảng đã học (claims từ ledger) cho phần user hành động (thông báo Permissions) | 15 |
| P2 | Rate limiting, cache, breaker | 10 |
| P2 | Config khả dụng (env, config.example, docs) | 10 |
| P2 | Test/probe khách quan (ảnh xác nhận + code test) | 10 |
| P2 | Hướng dẫn theo team/Project Docs + Operation toàn cầu | 10 |

---

## 2. Nội dung mục 0: Nhận biết "thiết kế thất bại"

Phản biện mạnh nhất được trong phiên này: **trên Discord, embeds ảnh/video mới được tạo rất ít
(các ảnh/video cũ thường đã thay thế = ngắn hạn, không tái tạo ra câu chuyện), URL hết hạn nhanh
(signed URL), và video nằm trong gallery nhưng có khi không hover được.**

---

## 3. Thiết kế chi tiết UX (Components V2 — sử dụng MediaGallery + ActionRow)

### 3.1 Component decision tree (ultra-pragmatic)

```text
media_kind == "video":
    if CANUPLOAD and filesize <= 8MB and not use_ytdlp:
        upload as discord.File (để native preview, không upload server-side)
    else:
        MediaGallery(url) + link button (Xem bài gốc) bên dưới
media_kind == "image"|"carousel":
    MediaGallery(urls) + link button
media_kind == "none":
    Plain text (title + link tnktok hoặc gốc)
```

### 3.2 Carousel (multi-image Instagram) — đã implement
- `CarouselView`: 1 ảnh MediaGallery + `◀/▶` ActionRow, chỉ số `-# 1/3`.
- Tại sao: media_hints từ native embed, nên kết quả cho IG carousel đẹp như native.

### 3.3 Nếu bot có video trực tiếp — dùng làm thumbnail chính
MediaGallery item nhận `description` (alt text). Đặt title/artist ở đó thay vì dùng thumbnail component — đơn giản hơn và tự động hiển thị.

---

## 4. Media Delivery Tier (chất lượng nguồn)

| Tier | Nguồn | Ưu tiên |
|---|---|---|
| T1 (thấp, do-n-browse) | media_hints từ Discord native | 0 network |
| T2 (bình thường) | dịch vụ proxies hiện có (`FxEmbed`, `ifx`, `facebed`, `tnktok`) | ~2 API call |
| T3 (cao, ít giới hạn) | proxy thứ 3 (`tikwm`, `oginstagram`, `meta og:image`) | fallback, đôi khi đồng thời |
| T4 (bất hạn chế) | yt-dlp / hosted worker (cần quyết định trước) | dài hạn, token, quota |

Tất cả tiers cần: `HEAD` validate status/content-type/size ≠ 0 trước khi gán URL.

---

## 5. Platform Adapter Matrix (đã vàng từ live probes)

| Platform | Adapter | Evidence (HTTP/status) | Config note |
|---|---|---|---|
| X | `FxEmbedAdapter` → `api.fxtwitter.com/{user}/status/{id}` | 200, `tweet.media.all[].url` = `video.twimg.com` mp4 | Tồn tại 2 tên hiển thị: fixupx/fxtwitter (Drop) |
| IG | `IfxAdapter` + `OgInstagramAdapter` | ifx HEAD 200 image/jpeg (gallery 5), oginstagram `og:image` HEAD 200 | Cache signed URL tối đa 300s |
| FB | `FacebedAdapter` + `rewrite_social_link` (facebook.com → www.facebed.com) | facebed 200 HTML, không có og:video thật (link 412) | Cần test với link FB reel thật |
| TikTok | `TiktokProxyAdapter` + `TikwmAdapter` + `rewrite_social_link` (→www.tnktok.com) | tikwm `data.play`, tnktok redirect CDN | Hiện fallback link unfurl đã implement |

---

## 6. UX trên Discord (sử dụng Bất ché một chút)

### 6.1 Best Practice UX
- Giữ text trong `TextDisplay` và các ảnh trong `MediaGallery`, đặt container ở dạng blur vừa phải.
- Sử dụng spoiler khi `ZENE_MEDIA_SUPPRESS=true` ở kênh chung/large contexts — ảnh là ẩn vùng.
- Sử dụng spoiler (`ZENE_MEDIA_SPOILER=true`) để tránh "Accidental NSFW preview" trong những kênh non-NSFW.
- Cung cấp link gốc bên dưới cùng media (e.g. CTA: button link → "Xem bài gốc").

### 6.2 Responsive Layout (approx, Ũ mắt trên mobile)
- Hạn chế kéo theo chiều rộng (trong layout): tốt nhất chỉ hiển thị text trong `TextDisplay`, gallery là ở dưới cùng.
- TokenStyle (snippet) chỉ sử dụng proper JS để không làm rỗng web.

---

## 7. Provenance & Confidence (live probe 2026-11-24)

- ✅ FxEmbed reachable: `GET https://api.fxtwitter.com/And116633/status/2124382980173070656`
- ✅ ifx: `GET https://ifx.up.railway.app/p/Df_8LXvH7xO/media/0..4` trả JPEG
- ✅ oginstagram: `GET https://oginstagram.com/p/Df_8LXvH7xO/` → `og:image` (exp-checked)
- ⚠️iger: research run failed upstream — claims trên đây đến từ probe HTTP trực tiếp local

---

## 8. Config Options (Sẵn sàng implement)

```python
# Formato  audioTextDisplay (tham khảo)
ZENE_MEDIA_SUPPRESS=false        # bật suppress thông báo ẩn
ZENE_MEDIA_SPOILER=false         # spoiler cho card media
ZENE_MEDIA_RATE_LIMIT=30         # rate ảnh/min (cần implement)
ZENE_MEDIA_ADAPTERS="tnktok,ifx,oginstagram,meta"  # ordering (cần implement)
```

---

## 9. Roadmap 15 → 90 điểm (priority: Gãy cao trước)

| P | Nội dung |
|---|---|
| P1 | Từ ngữ "media delivery ladder" thành module (class ladder adapter, đơn giản hóa fallback) |
| P2 | Media Preview + CTA (link button "Xem bài gốc") sinh động |
| P3 | Video download (transcode 2MB → upload file) — tham số `ZENE_MEDIA_UPLOAD_ENABLE=true` |
| P4 | Tracking rate limit, health endpoint live (p50/p95, durations per adapter) |
| P5 | Amplitude A/B của 2 cách gửi card (link vs upload) qua `ZENE_MEDIA_WALKABILITY=true` |

---

## 10. Command card (Quick ref)

| Mục đích | Lệnh |
|---|---|
| Khởi động thử (nếu đã có token) | `start.ps1` |
| Deploy (tự chạy khi đăng nhập) | `install-autostart.ps1` (chạy 1 lần) |
| Tự kiểm tra ping/up | `curl http://127.0.0.1:8080/health` |
| Test link TikTok | `https://www.tiktok.com/@supraman40999/video/7684014589700230414` |

---

## 11. References (Primary Sources — đã verify)

- https://docs.discord.com/developers/link-previews/overview
- https://docs.discord.com/developers/link-previews/component-embeds
- https://docs.discord.com/developers/components/reference
- https://docs.discord.com/developers/resources/message (nonce, flags scanning)
- https://docs.discord.com/developers/topics/rate-limits
- https://discord.com/blog/improving-our-mobile-experience (gallery UX)
- https://github.com/seriaati/embed-fixer (proxy bytes, opt-out)
- https://github.com/okdargy/fxTikTok/blob/hono-rewrite/README.md (mirror rewrite)
- ZENE MCP memory claims: `ig-carousel-reuse-native-embeds`, `tiktok-embed-robustness`, `social-mirror-rewrite-map-2026-11`, `direct-media-sources-2026-11`, `zene-social-embed-design-strategy`
