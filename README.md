# ZENE Discord Bot

Bot Discord đa năng: meme, tiện ích, tra cứu AV info, giá xăng, âm lịch… Chạy được
trên **máy x86 (Windows/Linux/macOS)** và **Raspberry Pi 4 / 5**.

- Entry point khuyến nghị: `python run.py`
- Entry point legacy (để rollback): `python main.py`
- Yêu cầu: **Python 3.10+** (khuyến nghị 3.11), discord.py 2.x.

---

## 1. Chức năng

Bot có **40 lệnh prefix** (gõ `z/`, `Z/`, `h/` hoặc `H/` trước tên lệnh) và
**6 lệnh slash** trên Discord UI (`/...`). Một số lệnh là *hybrid* (dùng được cả hai).

### 1.1 Slash command (gõ `/` trên Discord)

| Lệnh | Mô tả | Ghi chú |
|---|---|---|
| `/amlich` | Âm lịch hôm nay: can chi, tuổi xung, giờ Hoàng Đạo | hybrid |
| `/avt` | Xem ảnh đại diện (embed ảnh 512px + link) | hybrid |
| `/cmd` | Danh sách lệnh asset, có nút phân trang | hybrid |
| `/code <arg>` | Tra cứu phim theo mã qua av-wiki.net | hybrid, **chỉ kênh NSFW** |
| `/giaxanghomnay` | Giá xăng dầu Petrolimex 2 khu vực | hybrid |
| `/haha` | Ghép avatar vào ảnh "3 chó tuyết" | hybrid |
| `/idol <arg>` | Tra cứu diễn viên + tối đa 4 tác phẩm | hybrid, **chỉ kênh NSFW** |

### 1.2 Lệnh tiện ích / thông tin

| Lệnh | Chức năng |
|---|---|
| `z/info @user` | Thông tin ngẫu nhiên về một thành viên |
| `z/trans <text>` | Dịch sang tiếng Việt |
| `z/han <text>` | Hán → Việt (hvdic.thivien.net) |
| `z/wiki <từ khóa>` | Tóm tắt Wikipedia tiếng Việt |
| `z/cmd` | Liệt kê các lệnh asset nạp từ `command_link.xlsx` |
| `z/camon @user`, `z/non @user` | Câu chúc/jokes có tag thành viên |
| `z/vanmau <chủ đề>` | Các đoạn text "văn mẫu" |
| `z/anxin`, `z/xinloi`, `z/sapnupuas`, `z/samhoi`, `z/hotro` | Text meme có sẵn |

### 1.3 Lệnh ảnh / video

| Lệnh | Chức năng |
|---|---|
| `z/avt`, `z/haha`, `z/tv` | Avatar / ghép avatar (xem mục 1.1) |
| `z/auzam`, `z/nohorny`, `z/bonk` | Ảnh ngẫu nhiên từ thư mục tương ứng |
| `z/wake` | Video wake |
| `z/waifu`, `z/mlem`, `z/slap` | Ảnh SFW/động tác từ API ngoài |

### 1.4 Lệnh NSFW (bắt buộc kênh đã đánh dấu NSFW)

| Lệnh | Chức năng |
|---|---|
| `z/code`, `z/idol` | av-wiki.net, embed song ngữ JP/VN, ảnh fallback từ FANZA |
| `z/hen`, `z/hentai`, `z/hentrap`, `z/henneko`, `z/henbj` | API ảnh NSFW (giới hạn ≤ 10 ảnh/lần) |
| `z/nhentai <id>`, `z/search <từ khóa>` | Tra cứu/tìm doujin |

Nếu dùng ngoài kênh NSFW, bot trả lời `Qua kênh NSFW mà xài` / `Lệnh này chỉ dùng được trong kênh NSFW.`

### 1.5 Lệnh vận hành

| Lệnh | Quyền | Chức năng |
|---|---|---|
| `z/health` | mọi người | uptime, ping, số guild, extension lỗi |
| `z/stats` | mọi người | đếm trigger hit, asset miss… |
| `z/extensions` | mọi người | cog đã load / failed |
| `z/reload <module>` | owner | reload cog nóng |
| `z/restart` | owner | đóng bot rồi supervisor respawn |
| `z/shutdown` | owner | tắt an toàn |

### 1.6 Phản hồi tự động (`on_message`)

Ngoài lệnh, bot còn phản hồi ~18 cụm từ text có sẵn (ví dụ `tôi bị xúc phạm`,
`là...` → Folontilô, `siuu`, `hảo hán`, `xaolon`, `300 bài code thiếu nhi`) và
~40 mapping "lệnh → file ảnh/video" từ `zene/data/command_data/command_link.xlsx`.
Toàn bộ nội dung meme nằm trong **`zene/data/memes.json`** (nguồn dữ liệu duy
nhất); file Excel `command_link.xlsx` và `extra_commands.json` chỉ giữ lại làm
fallback tương thích. Dữ liệu được nạp **một lần lúc boot**, có cooldown theo
từng người, bỏ qua tin nhắn từ bot khác, chặn path traversal. Muốn thêm meme:
sửa JSON, không cần đụng code hay mở LibreOffice.

### 1.7 Đặc tính vận hành 24/7

- **Supervisor**: `login()` có timeout, `connect()` chạy dài; mỗi lần thoất bất
  thường đều tính là crash và restart với exponential backoff + jitter.
- **Fail-soft**: cog lỗi không làm chết bot; `/extensions` liệt kê, `z/reload` sửa nóng.
- **Resilience**: circuit breaker + retry + timeout cho mọi HTTP/SDK ngoài.
- **aiohttp session dùng chung** + **cache TTL** (avwiki 5p, dịch 24h, giá xăng 30p).
- **Health endpoint** `GET /health` trả JSON, `503` khi degraded.
- **Bản tin hàng ngày** (tuỳ chọn): gửi âm lịch + giá xăng vào kênh chỉ định,
  giờ được cấu hình theo timezone (`ZENE_DIGEST_CHANNEL_ID`).
- **Log JSON xoay vòng** tại `logs/zene.log`, tự redact token.

---

## 2. Tạo bot trên Discord Developer Portal

1. Vào <https://discord.com/developers/applications> → **New Application** → đặt tên.
2. Tab **Bot** → **Reset Token** → copy token (chỉ lấy lúc này).
3. Bật **Message Content Intent** (bắt buộc để lệnh prefix hoạt động).
   Chỉ bật **Server Members Intent** nếu bạn đặt `ZENE_MEMBERS_INTENT=true`.
4. Tab **OAuth2 → URL Generator**:
   - Scopes: `bot` + `applications.commands` (cái sau bắt buộc để có slash command).
   - Bot Permissions: *Send Messages*, *Embed Links*, *Attach Files*,
     *Read Message History*, *Use Slash Commands*.
5. Mở URL sinh ra → thêm bot vào server.
6. Đánh dấu NSFW cho kênh dùng `code`/`idol`/`hen*`/`nhentai`:
   **Channel Settings → NSFW Toggle**.
7. Đặt owner: lấy User ID (bật Developer Mode, right-click tên → Copy User ID) rồi
   điền vào `ZENE_OWNER_IDS` trong `.env`.

> Bot cần vài phút để Discord cache slash command. Nếu chưa hiện, restart bot hoặc
> đợi; `tree.sync()` đã chạy lúc boot.

---

## 3. Cài đặt trên máy x86 (Windows / Linux / macOS)

### Windows (PowerShell)

```powershell
git clone https://github.com/slimulv1/ZENE-discord-bot.git
cd ZENE-discord-bot
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy config.example.txt .env
notepad .env          # điền DISCORD_TOKEN, ZENE_OWNER_IDS
python run.py
```

Nếu chính sách thực thi chặn Activate.ps1:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

### Linux / macOS

```bash
git clone https://github.com/slimulv1/ZENE-discord-bot.git
cd ZENE-discord-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp config.example.txt .env
nano .env
python run.py
```

### Kiểm tra sau khi cài

```bash
python -m unittest discover -s tests -v   # 9 test
python -m ruff check .                    # cần: pip install ruff
curl http://127.0.0.1:8080/health
```

---

## 4. Cài đặt trên Raspberry Pi 4 / 5

Khuyến nghị **Raspberry Pi OS 64-bit (Bookworm)**. Pi 4 (≥2GB RAM) và Pi 5 đều chạy tốt.

### 4.1 Chuẩn bị hệ thống

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3 python3-venv python3-pip git curl
# Đảm bảo Python >= 3.10
python3 --version
```

Bật SSH nếu quản lý từ xa: `sudo raspi-config` → *Interface Options → SSH*.

### 4.2 Cài bot

```bash
cd ~
git clone https://github.com/slimulv1/ZENE-discord-bot.git
cd ZENE-discord-bot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install --only-binary=:all: -r requirements.txt
cp config.example.txt .env
nano .env     # điền DISCORD_TOKEN + ZENE_OWNER_IDS
python run.py
```

`--only-binary=:all:` tránh build numpy/Pillow từ source trên ARM (rất chậm).
Nếu còn sluggish, đặt thêm `ZENE_LOG_LEVEL=WARNING` trong `.env`.

### 4.3 Chạy như systemd service (tự khởi động khi reboot)

Tạo `/etc/systemd/system/zene-bot.service`:

```ini
[Unit]
Description=ZENE Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ZENE-discord-bot
EnvironmentFile=/home/pi/ZENE-discord-bot/.env
ExecStart=/home/pi/ZENE-discord-bot/.venv/bin/python /home/pi/ZENE-discord-bot/run.py
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zene-bot
sudo systemctl status zene-bot
journalctl -u zene-bot -f
```

### 4.4 Docker (tuỳ chọn, cả x86 lẫn ARM64)

```bash
cp config.example.txt .env   # điền token
docker compose up -d --build
docker compose logs -f
curl http://localhost:8080/health
```

`docker-compose.yml` dùng `restart: unless-stopped`, mount `logs/` và `zene/data`
(read-only), healthcheck qua `/health`.

---

## 5. Cấu hình (file `.env`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DISCORD_TOKEN` | (bắt buộc) | Token bot. Không commit file `.env`. |
| `ZENE_OWNER_IDS` | owner legacy | Comma-separated User ID được quyền reload/restart/shutdown |
| `ZENE_PREFIXES` | `z/,Z/,h/,H/` | Prefix lệnh |
| `ZENE_REQUIRED_EXTENSIONS` | 5 core cog | Cog bắt buộc |
| `ZENE_OPTIONAL_EXTENSIONS` | 7 legacy cog | Cog tùy chọn, lỗi thì vẫn chạy |
| `ZENE_DISABLED_EXTENSIONS` | rỗng | Tắt cog cụ thể |
| `ZENE_LOG_LEVEL` | `INFO` | `DEBUG/INFO/WARNING/ERROR` |
| `ZENE_LOG_DIR` | `./logs` | Thư mục log |
| `ZENE_MEMBERS_INTENT` | `false` | Bật Server Members Intent |
| `ZENE_IGNORE_BOTS` | `true` | Bỏ qua tin nhắn từ bot khác |
| `ZENE_TRIGGER_COOLDOWN` | `1.5` | Cooldown trigger tự động (giây) |
| `ZENE_MAX_RESTARTS` | `10` | Số lần restart tối đa trước khi dừng |
| `ZENE_STABLE_SECONDS` | `60` | Chạy ổn định ≥ giá trị này → reset failure counter |
| `ZENE_BOOT_TIMEOUT` | `120` | Timeout login (giây) |
| `HEALTH_HOST` / `HEALTH_PORT` | `127.0.0.1:8080` | Health endpoint (`0` để tắt) |
| `DMM_API_ID` / `DMM_AFFILIATE_ID` | rỗng | Chỉ cần cho `zene.dmm_tracker` (tắt mặc định) |
| `ZENE_DIGEST_CHANNEL_ID` | `0` | Kênh nhận bản tin hàng ngày (`0` = tắt) |
| `ZENE_DIGEST_HOUR` / `ZENE_DIGEST_MINUTE` | `6` / `30` | Giờ phát bản tin |
| `ZENE_DIGEST_TIMEZONE` | `Asia/Ho_Chi_Minh` | Múi giờ của lịch phát |
| `ZENE_DIGEST_PING` | `false` | Có `@everyone` trong bản tin không |

Xem `config.example.txt` để có bản mẫu đầy đủ.

---

## 6. Cấu trúc source

```
run.py                  entrypoint production (supervisor)
main.py                 entrypoint legacy (rollback)
zene_core/
  config.py             cấu hình từ env, immutable, redact token
  bot.py                ZeneBot: setup_hook, error handler, graceful close
  supervisor.py         restart/backoff, signal, health server
  resilience.py         retry, circuit breaker, token bucket
  net.py                aiohttp session chung + breaker
  assets.py             nạp Excel 1 lần, path an toàn, composite ảnh PNG
  triggers.py/content.py registry trigger + nội dung meme
  avwiki.py             client av-wiki.net + dịch + ảnh FANZA
  cogs/                 conversation, ops, avwiki, amlich, giaxang
dmm/                    client DMM đã vá (thay dmm-search3)
zene/                   cog legacy (NSFW, wiki, trans, nhentai…)
tests/test_core.py      unit test thuần
pyproject.toml          cấu hình ruff
```

---

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `PrivilegedIntentsRequired` | Bật **Message Content Intent** trong Developer Portal |
| `LoginFailure` | Token sai/cũ → Reset Token, cập nhật `.env` |
| Không thấy slash command | Cần scope `applications.commands`; đợi cache hoặc restart bot |
| `/code` báo dùng kênh NSFW | Bật NSFW cho kênh đó |
| Bot không phản hồi prefix | Kiểm tra `ZENE_PREFIXES`, Message Content Intent |
| `z/code` không có ảnh | av-wiki không có ảnh; bot fallback sang FANZA cần `DMM_API_ID`/`DMM_AFFILIATE_ID` |
| Dịch JP→VN trả nguyên JP | Google rate-limit (429); bot tự fallback, thử lại sau |
| Extension failed | `z/extensions` xem lý do, `z/reload <module>` sửa |
| Health trả 503 | Bot chưa READY hoặc có cog lỗi — xem log |

---

## 8. Phát triển

```bash
pip install ruff
python -m ruff check .
python -m ruff format .
python -m unittest discover -s tests -v
```

Mọi thay đổi nên giữ: không commit `.env`, không log token, mọi HTTP phải có
timeout + breaker, không blocking I/O trong async path.

*Legacy `main.py` và `zene/communicate.py` được giữ để rollback; bản production
luôn là `run.py`.*
