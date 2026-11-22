# ZENE Discord Bot

Bot gửi meme cho Discord server.

## Chạy bản khuyến nghị (24/7)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # điền DISCORD_TOKEN
python run.py
```

`run.py` dùng lớp `zene_core/`: supervisor tự restart, extension lỗi không làm
chết bot, asset nạp một lần, log JSON có xoay vòng và endpoint `/health`.
Xem chi tiết tại [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md).

Test logic thuần: `python -m unittest discover -s tests -v`

Docker: `docker compose up -d --build`, sau đó `curl http://localhost:8080/health`.

## Chạy bản legacy (để rollback)

1. Chạy file install_lib trong `/utils`
2. Thêm TOKEN vào `TOKEN.json` trong `/zene`
3. Chạy `main.py`

> Lưu ý: bản legacy có nhiều vấn đề về độ tin cậy (đọc Excel mỗi tin nhắn,
> restart không ổn định, ghi ảnh dùng chung...). Chỉ dùng để tương thích ngược.
