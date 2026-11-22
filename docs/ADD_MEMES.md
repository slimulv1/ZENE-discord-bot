# Thêm meme bằng tay

Mọi nội dung meme nằm trong một file duy nhất: **`zene/data/memes.json`**.
Bạn không cần sửa code Python, không cần mở Excel/LibreOffice, và không cần cài
thêm thư viện để thêm meme.

> File Excel `zene/data/command_data/command_link.xlsx` và
> `extra_commands.json` chỉ giữ lại làm **fallback** nếu `memes.json` bị xoá.

---

## 1. Cấu trúc file JSON

```jsonc
{
  "version": 1,
  "description": "...",
  "text_triggers": {},        // nhắn đúng cụm → bot trả text
  "contains_triggers": [],    // tin nhắn CHỨA cụm → bot trả text/file
  "folder_triggers": {},      // nhắn đúng cụm → gửi ảnh ngẫu nhiên trong thư mục
  "choice_triggers": {},      // nhắn đúng cụm → chọn ngẫu nhiên 1 trong danh sách
  "command_texts": {},        // nội dung cho lệnh có sẵn (xinloi, samhoi...)
  "anxin_stories": [],        // danh sách cho lệnh z/anxin
  "assets": {}                // nhắn đúng cụm → gửi file ảnh/video
}
```

Mở bằng VS Code / Notepad++ / Notepad thường. Lưu đúng **UTF-8** (VS Code mặc
định UTF-8). Sau khi sửa, validate:

```powershell
python -m json.tool zene/data/memes.json
```

Nếu lỗi in ra vị trí dòng → bạn thiếu dấu phẩy / ngoặc / nháy kép.

> **Không tự khởi động lại bằng `z/restart`**: module `content.py` đọc JSON lúc
> import, và lệnh restart chỉ tạo lại bot trong cùng process. Phải **restart cả
> process**: `Ctrl+C` rồi chạy lại `python run.py`, hoặc
> `sudo systemctl restart zene-bot`, hoặc `docker compose restart`.

---

## 2. Thêm từng loại meme

### 2.1 Text trigger (nhắn đúng cụm → trả text)

Thêm vào `text_triggers`. **Key là toàn bộ nội dung tin nhắn** (không có prefix,
không dấu thừa), bot so sánh sau khi `lower()` + chuẩn hoá Unicode NFC.

```json
"text_triggers": {
  "tôi bị xúc phạm": "OMAE CỐ TÌNH CHỬI WATASHI DESU KA? ...",
  "chào bot": "Chào bạn, hôm nay bot khỏe!"
}
```

Dùng `\n` để xuống dòng. Không dùng prefix `z/` ở key.

### 2.2 Contains trigger (tin nhắn chứa cụm → trả text hoặc file)

Thêm phần tử vào `contains_triggers`. Dùng khi bạn muốn khớp cả câu có chứa
từ khoá. Các trường:

| Trường | Ý nghĩa |
|---|---|
| `name` | Tên nội bộ (duy nhất) |
| `pattern` | Cụm cần tìm |
| `response.kind` | `text` hoặc `file` |
| `response.value` | Nội dung text hoặc đường dẫn file |
| `priority` | Số càng lớn càng ưu tiên nếu nhiều cụm cùng khớp |
| `cooldown` | Giây giữa 2 lần phản hồi cho mỗi user (tuỳ chọn) |

```json
"contains_triggers": [
  {
    "name": "folontilo",
    "pattern": "là...",
    "response": { "kind": "text", "value": "...là Folontilô!😱😱" },
    "priority": 10
  },
  {
    "name": "siuu",
    "pattern": "siuu",
    "response": { "kind": "file", "value": "zene/data/video/siu.mp4" },
    "priority": 20,
    "cooldown": 2.0
  },
  {
    "name": "meme_moi",
    "pattern": " ÚI TRỜI ",
    "response": { "kind": "file", "value": "zene/data/video/huh.mp4" },
    "priority": 5,
    "cooldown": 3.0
  }
]
```

### 2.3 Folder trigger (ảnh ngẫu nhiên)

1. Tạo thư mục mới, ví dụ `zene/data/image/cat/`, bỏ vào đó các ảnh `1.jpg`, `2.png`…
2. Thêm vào `folder_triggers`:

```json
"folder_triggers": {
  "hảo hán": "haohan",
  "mèo": "cat"
}
```

Ai nhắn đúng `mèo` → bot gửi ngẫu nhiên 1 file trong `zene/data/image/cat/`.
Tên thư mục tính **tương đối với `zene/data/image/`**. Các thư mục đã được
index sẵn: `haohan`, `xaolon`, `auzam`, `no_horny`, `bonk`, `tv`.

### 2.4 Choice trigger (chọn ngẫu nhiên 1 trong danh sách)

```json
"choice_triggers": {
  "300 bài code thiếu nhi": [
    "Câu chuyện 1...",
    "Câu chuyện 2..."
  ],
  "khôn ngoan": [
    "Hôm nay nên làm việc tử tế.",
    "Hôm nay nên ngủ nướng."
  ]
}
```

Mỗi lần nhắn đúng cụm, bot chọn 1 chuỗi ngẫu nhiên bằng `SystemRandom`.

### 2.5 Asset command (gửi ảnh/video theo cụm)

Đây là loại hay dùng nhất. Key là **cụm chat thường, không có prefix** — người
dùng chỉ cần gõ đúng `chào cậu`, không phải `z/chào cậu`.

1. Copy file vào `zene/data/image/` hoặc `zene/data/video/`.
2. Thêm vào `assets`:

```json
"assets": {
  "chào cậu": "zene/data/video/ChaoCau.mp4",
  "quan trọng": "zene/data/video/QT.mp4",
  "meme mới": "zene/data/image/nanana.png"
}
```

Gõ `z/cmd` trong Discord để thấy danh sách (có phân trang).

**Quy tắc đường dẫn**
- Tương đối với **gốc repo** (bắt đầu bằng `zene/data/...`).
- Không dùng `../`, bot chặn path traversal.
- File phải tồn tại; nếu mất, bot trả "Asset tạm thời không khả dụng".
- Mặc định giới hạn **8 MB** (`ZENE_MAX_ASSET_BYTES`). Video lớn nên nén lại.

### 2.6 Nội dung cho lệnh có sẵn

`command_texts` chứa text của 4 lệnh prefix cố định:

```json
"command_texts": {
  "hotro": "...",
  "xinloi": "...",
  "sapnupuas": "...",
  "samhoi": "..."
}
```

`anxin_stories` là danh sách cho `z/anxin`:

```json
"anxin_stories": ["Câu 1", "Câu 2"]
```

> Muốn tạo **lệnh prefix/slash mới** (ví dụ `z/meme`) thì phải viết thêm code trong
> cog — JSON chỉ thêm nội dung cho các lệnh và trigger đã có.

---

## 3. Kiểm tra sau khi thêm

```powershell
python -m json.tool zene/data/memes.json        # 1. JSON hợp lệ
python -m unittest discover -s tests -v          # 2. 9 test vẫn xanh
python run.py                                   # 3. khởi động lại process
```

Trong Discord:
- Gõ đúng cụm bạn vừa thêm để kiểm tra trigger/asset.
- `z/cmd` → kiểm tra asset xuất hiện trong danh sách.
- `z/stats` → `trigger_hits` / `excel_hits` tăng.
- `z/health` → bot READY, không có extension failed.

---

## 4. Lỗi thường gặp

| Triệu chứng | Nguyên nhân / cách sửa |
|---|---|
| Bot không khởi động, log lỗi `memes.json` | JSON sai cú pháp → chạy `python -m json.tool` |
| Sửa JSON nhưng không áp dụng | Chưa restart **process** (`z/restart` là chưa đủ) |
| Nhắn cụm nhưng bot không phản hồi | Key phải khớp chính xác sau `lower()` + NFC; thử bỏ dấu thừa/space |
| Báo "Asset tạm thời không khả dụng" | Sai đường dẫn hoặc file quá 8 MB |
| Ảnh/video hiện sai định dạng | Discord hỗ trợ png/jpg/gif/webp/mp4; tránh file lạ |
| Trigger bị spam | Thêm `cooldown` cho `contains_triggers` hoặc giảm tần suất |

---

## 5. Nội dung NSFW

`memes.json` **không có cờ NSFW riêng cho từng meme**. Nếu thêm ảnh nhạy cảm,
hãy gắn nó vào các lệnh đã chặn kênh (`/code`, `/idol`, `z/hen*`, `z/nhentai`)
hoặc chỉ dùng trong kênh đã bật NSFW, và đánh dấu kênh đó trong Discord.

---

## 6. Rollback

Nếu JSON lỗi, bạn có thể xoá/đổi tên `zene/data/memes.json`: bot sẽ tự fallback
sang `command_link.xlsx` + `extra_commands.json` (nội dung text vẫn cần JSON,
nên tốt nhất là sửa JSON thay vì xoá).
