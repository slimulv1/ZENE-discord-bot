# Hướng dẫn cài ZENE Bot trên Windows (đầy đủ, dễ làm)

Tài liệu này dành cho người dùng Windows **chưa từng cài bot Discord**. Làm theo thứ tự
từng mục; sau mỗi mục có phần **"Kiểm tra"** để bạn biết mình đã làm đúng chưa.

> **Con đường ngắn nhất:** nếu bạn đã có repo, đã tạo bot và chỉ muốn chạy ngay → xem
> [Mục 5](#5-chạy-bot-lần-đầu). Muốn bot tự chạy khi bật máy → làm thêm [Mục 7](#7-chạy-247-và-quản-lý).

---

## 1. Hiểu nhanh trước khi làm

| Thuật ngữ | Là gì | Bạn cần làm gì |
|---|---|---|
| **Token** | "Chìa khóa" để bot đăng nhập | Giữ bí mật, không đưa cho ai, không gửi lên chat |
| **Owner ID** | ID tài khoản Discord của **bạn** (không phải ID bot) | Dùng để gỡ lệnh quản lý như `z/reload` |
| **Message Content Intent** | Quyền cho bot đọc nội dung tin nhắn | Phải bật trong Discord Developer Portal |
| **Scope** | Quyền đăng nhập OAuth2 | Tick `bot` + `applications.commands` |
| **Prefix / Slash** | `z/health` là prefix, `/health` là slash | Cả hai đều dùng được |

Có **2 cách chạy**, chọn 1:

| Cách | Khi nào dùng | Lệnh |
|---|---|---|
| **Thử nghiệm** | Lần đầu, muốn thấy log ngay trong terminal | `.\start.ps1` |
| **24/7** | Sau khi test ổn, muốn bot tự chạy mỗi lần đăng nhập | `.\install-autostart.ps1` (chạy 1 lần) |

`start.ps1` giữ token/ID **trong phiên PowerShell hiện tại** (đóng cửa sổ là mất).
`install-autostart.ps1` thì lưu vào **biến môi trường USER** để dùng mãi về sau —
sau khi chạy setup một lần, bạn **không phải gõ lại lệnh dài hay dán lại token**.

---

## 2. Chuẩn bị máy

1. **Python 3.11** (khuyến nghị): tải <https://www.python.org/downloads/windows/>.
   Khi cài, tick **"Add python.exe to PATH"**.
   Kiểm tra:
   ```powershell
   py -3.11 --version
   ```
2. **Git for Windows**: <https://git-scm.com/download/win> (cài mặc định là được).
   Kiểm tra: `git --version`.
3. **PowerShell**: dùng PowerShell đi kèm Windows 11 (không cần cài thêm).
   Nếu script bị chặn, dùng lệnh có `-ExecutionPolicy Bypass` ở các bước dưới.

**Kiểm tra:** cả 2 lệnh `py -3.11 --version` và `git --version` đều in ra số phiên bản.

---

## 3. Tạo bot trên Discord và lấy thông tin

### 3.1 Tạo ứng dụng + bot

1. Vào <https://discord.com/developers/applications> → **New Application** → đặt tên (vd `ZENE`).
2. Tab **Bot** → bấm **Reset Token** → **copy token** (chỉ hiện lúc này).
   → Đây là "chìa khóa", lưu tạm ở nơi an toàn, **không gửi vào chat/file repo**.
3. Vẫn ở tab **Bot**, bật công tắc **Message Content Intent**.
   Nếu quên, bot sẽ dừng ngay với lỗi `PrivilegedIntentsRequired`.

### 3.2 Lấy ID Discord của bạn

1. Discord → **User Settings → Advanced → Developer Mode: On**.
2. Chuột phải vào **tên bạn** (trong server hoặc danh sách bạn bè) → **Copy User ID**.
3. Dán vào đâu đó tạm — đây là `ZENE_OWNER_IDS` (chuỗi số, ví dụ `374186828174983169`).

### 3.3 Mời bot vào server

Vào **OAuth2 → URL Generator**, tick `bot` và `applications.commands`, rồi copy link.

**Link mời cơ bản** (memes, âm lịch, dịch, giá xăng, sửa link thành ảnh/video):

```
https://discord.com/oauth2/authorize?client_id=1574258169528713246&permissions=2147600384&scope=bot%20applications.commands
```

**Link mời đầy đủ** (thêm *Manage Webhooks* + *Manage Messages* so với bản cơ bản) —
dùng khi bạn muốn bot **xoá tin nhắn link của bạn và gửi lại mang tên/avatar bạn**.
Vì script mặc định dùng chế độ `impersonate`, **người mới nên dùng luôn link này**:

```
https://discord.com/oauth2/authorize?client_id=1574258169528713246&permissions=2684479488&scope=bot%20applications.commands
```

> **Lưu ý quan trọng:** nếu bạn đã mời bot bằng link cũ/cơ bản, hãy **mời lại bằng link đầy đủ**
> rồi chọn đúng server. Quyền được cập nhật ngay, **không cần restart bot**.
>
> Nếu bạn dùng bot của người khác thay vì bot của mình, thay `client_id=` bằng Client ID
> trong **Application → General Information** của ứng dụng đó.

**Kiểm tra:** trong server, bot hiện online (không có dấu "offline"), và gõ `/` thấy
tên lệnh của bot xuất hiện.

---

## 4. Cài đặt code

Mở PowerShell, chạy lần lượt:

```powershell
git clone https://github.com/slimulv1/ZENE-discord-bot.git
cd ZENE-discord-bot
py -3.11 -m venv .venv
powershell -NoProfile -ExecutionPolicy Bypass -Command ".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
```

Nếu bạn đã clone sẵn (ví dụ đang ở `C:\Users\slimu\Downloads\Zene Bot\ZENE-discord-bot`),
chỉ cần:

```powershell
cd "C:\Users\slimu\Downloads\Zene Bot\ZENE-discord-bot"
powershell -NoProfile -ExecutionPolicy Bypass -Command ".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
```

**Kiểm tra:** thư mục `.venv\Scripts\python.exe` tồn tại; lệnh pip không báo lỗi đỏ.

---

## 5. Chạy bot lần đầu

Trong thư mục dự án, chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Script sẽ hỏi:

1. `DISCORD_TOKEN` — dán token đã copy ở **3.1** (ký tự được ẩn khi gõ).
2. `ZENE_OWNER_IDS` — dán ID bạn đã copy ở **3.2** (phải là chuỗi số).

Sau đó bot chạy. Log được ghi dạng JSON, bạn sẽ thấy dòng tương tự:

```
{"level": "INFO", "message": "READY as ZENE#8150 | guilds=1", ...}
```

Trong đó `guilds` là **số server bot đang ở** — `guilds=1` nghĩa là bot đã vào đúng 1 server.

**Kiểm tra nhanh:**

- Trang trạng thái: mở <http://localhost:8080/> (hoặc `/health` để xem JSON).
- Trong Discord:
  - `/health` hoặc `z/health` → bot trả lời.
  - `/list` → hiện danh sách meme.
  - Gõ `siuu` → hiện video meme.
  - Gửi một link X/Instagram/Facebook/TikTok → bot phản hồi ảnh/video.

Giữ nguyên cửa sổ PowerShell này nếu bạn chỉ muốn test. Nhấn **Ctrl+C** để tắt bot
(dọn dẹp an toàn), hoặc đóng cửa sổ.

---

## 6. Cấu hình thêm (tuỳ chọn)

Các script đã bật sẵn cấu hình hợp lý: tự sửa link mạng xã hội, dịch sang tiếng Việt,
tự nạp `memes.json` khi bạn sửa file (mỗi ~30 giây).

Nếu muốn đổi:

| Mục đích | Biến | Giá trị |
|---|---|---|
| Không muốn bot "đóng vai" bạn | `ZENE_MEDIA_MODE` | `reply` thay vì `impersonate` |
| Chỉ lấy thumbnail, không tải video | `ZENE_MEDIA_USE_PROXIES` | `false` |
| Thay đổi cụm domain xử lý | `ZENE_MEDIA_ALLOWED_DOMAINS` | `x.com,instagram.com,...` |
| Tắt tự nạp meme | `ZENE_RELOAD_ON_CHANGE` | `false` |
| Bắt lại kiểm tra kênh NSFW | `ZENE_NSFW_ENABLED` | `true` (mặc định script để `false`; ảnh `/code` luôn làm mờ) |

Cách đặt đúng khi dùng script Windows:

- **Khuyến nghị**: sửa giá trị trong `start.ps1` (chạy tay) hoặc `zene-autostart.ps1`
  (chạy 24/7), rồi chạy lại script / restart task.
- **Không dùng `.env` cho 3 biến `ZENE_MEDIA_*` ở trên**: script đã export chúng trong
  phiên chạy, nên bot sẽ ưu tiên giá trị của script và bỏ qua giá trị trong `.env`.
- `.env` vẫn dùng được cho các biến **không bị script export**, ví dụ
  `ZENE_RELOAD_ON_CHANGE`: `copy config.example.txt .env` rồi mở sửa. File này đã có
  trong `.gitignore`, **không bao giờ commit**.

---

## 7. Chạy 24/7 và quản lý

Sau khi test ổn, thiết lập tự chạy **một lần**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-autostart.ps1
```

Script sẽ:

- hỏi lại token + ID (nếu bạn chạy ở phiên PowerShell mới), lưu vào **biến môi trường USER**;
- đăng ký Scheduled Task tên **`ZENE Bot`**, chạy `zene-autostart.ps1` mỗi lần bạn **đăng nhập**;
- tự khởi động lại bot sau 10 giây nếu process bot thoát.

> `install-autostart.ps1` **chỉ đăng ký task**, chưa chạy bot ngay. Để bot online luôn,
> chạy `Start-ScheduledTask -TaskName 'ZENE Bot'` hoặc đăng xuất rồi đăng nhập lại.

Quản lý:

```powershell
Stop-ScheduledTask -TaskName 'ZENE Bot'                                      # tạm dừng
Start-ScheduledTask -TaskName 'ZENE Bot'                                     # chạy lại
Get-ScheduledTask -TaskName 'ZENE Bot' | Select-Object State, TaskName        # xem trạng thái
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1 # gỡ task (giữ token)
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1 -ClearSecrets  # gỡ cả token/ID
```

Log chạy nền: `logs\autostart.log` (không chứa token).

**Giới hạn cần biết:**

- Task chạy **sau khi bạn đăng nhập**, không chạy khi máy chưa có phiên user.
- Muốn chạy ngay cả khi chưa đăng nhập, cần chạy như service với tài khoản hệ thống —
  không khuyến nghị vì liên quan lưu mật khẩu Windows.
- Token nằm trong biến môi trường cấp user (registry), tiến trình nào chạy bằng user đó
  cũng đọc được → đừng chia sẻ máy.

---

## 8. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `PrivilegedIntentsRequired` / log dừng ngay | Chưa bật Message Content Intent | Developer Portal → tab Bot → bật công tắc, restart bot |
| `LoginFailure` | Token sai/cũ | Reset Token rồi chạy lại script có `-Force` (xem mục 9) |
| `Không có thông tin` / bot không trả lời `z/...` | Prefix sai hoặc intent tắt | Kiểm tra Message Content Intent; prefix mặc định `z/` |
| Không thấy lệnh `/` | Thiếu scope `applications.commands` | Mời lại bot bằng link ở **3.3**, đợi vài phút |
| Gửi link nhưng bot ghi `403 Missing Permissions` | Bot thiếu Manage Webhooks / Manage Messages | Mời lại bằng **link đầy đủ** ở **3.3** |
| Bot reply đúng nhưng vẫn tên ZENE | Chế độ impersonate bị fallback | Xem dòng log `impersonate thất bại` ở trên |
| `autostart.log` báo `... missing` | Chưa chạy setup | Chạy lại `install-autostart.ps1` một lần |
| Trang `localhost:8080` không mở | Bot chưa READY hoặc port bị chiếm | Xem `logs\zene.log`; kiểm tra process bot đang chạy |
| `/code` báo cần kênh NSFW | Kênh chưa bật NSFW | Channel Settings → bật **NSFW** |
| Dịch ra nguyên tiếng Trung/Nhật | Google tạm chặn 429 | Bot tự fallback MyMemory; thử lại sau vài giây |

Nếu vẫn lỗi, xem log chi tiết: `logs\zene.log` và `logs\autostart.log`.

---

## 9. Bảo mật và cập nhật

- **Token là bí mật.** Nếu từng dán token vào chat/log, hãy **Reset Token** ngay trong
  Developer Portal. Vì biến USER đã được lưu từ trước, chạy lại script **không tự hỏi lại** —
  phải thêm `-Force`:

  ```powershell
  # Chạy tay (chỉ áp dụng cho cửa sổ hiện tại)
  powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Force

  # Đã setup autostart: cập nhật token/ID rồi khởi động lại task
  powershell -NoProfile -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Force
  Stop-ScheduledTask -TaskName 'ZENE Bot'
  Start-ScheduledTask -TaskName 'ZENE Bot'
  ```
- Không commit file `.env`; repo đã có `.gitignore` chặn `.env`, `.env.*`, cookie, v.v.
- Cập nhật bot:
  ```powershell
  cd "C:\Users\slimu\Downloads\Zene Bot\ZENE-discord-bot"
  git pull
  powershell -NoProfile -ExecutionPolicy Bypass -Command ".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
  Stop-ScheduledTask -TaskName 'ZENE Bot'
  Start-ScheduledTask -TaskName 'ZENE Bot'
  ```
  (Nếu chạy tay: đóng terminal rồi chạy lại `start.ps1`.)
- Giấy phép: **PolyForm Noncommercial 1.0.0** — dùng/sửa được, không bán lợi nhuận.

---

## Tóm tắt lệnh nhớ nhanh

```powershell
# Lần đầu / thử nghiệm
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1

# Tự chạy khi đăng nhập (chạy 1 lần)
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-autostart.ps1

# Dừng / chạy lại / gỡ
Stop-ScheduledTask -TaskName 'ZENE Bot'
Start-ScheduledTask -TaskName 'ZENE Bot'
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1
```
