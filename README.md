# SRT Subtitle Translator

Công cụ dịch file phụ đề `.srt` song song tốc độ cao, sử dụng **AI-Box API** (DeepSeek V4 Flash).  
Hỗ trợ tối đa **20 workers song song**, tự động self-healing, và chuẩn **Dubbing/TTS**.

---

## ✨ Tính năng

- 🚀 **20 API keys → 20 workers song song** — dịch cực nhanh
- 🎯 **Dubbing-grade prompt** — Zero-shift rule, Ellipsis bridging, Timestamp-aware compression
- 🔄 **4 lớp self-healing** — tự động retry khi có block lỗi
- 📖 **Glossary** — nhập thuật ngữ đặc thù (tên nhân vật, địa danh)
- 🌐 **16 ngôn ngữ** — Indonesian, Vietnamese, Thai, Japanese, Korean, Arabic...
- 🎬 **6 loại nội dung** — Film, Anime, Wuxia, News, Documentary, Auto

---

## ⚙️ Yêu cầu

- **Python 3.10+** (không cần cài thêm thư viện nào — dùng 100% standard library)
- **API Key** từ [api.ai-box.vn](https://api.ai-box.vn/console/token)

---

## 🚀 Cài đặt nhanh (1 lệnh)

```bash
# 1. Clone repo
git clone https://github.com/YOUR_USERNAME/SRT-Translator.git
cd SRT-Translator

# 2. Tạo config từ mẫu
copy config.example.json config.json   # Windows
# hoặc:
cp config.example.json config.json     # Mac/Linux

# 3. Chạy app
python app.py
```

> Sau khi mở app, nhập API key vào ô **API KEYS** rồi nhấn **Lưu cấu hình**.

---

## 📁 Cấu trúc project

```
SRT-Translator/
├── app.py                  # Giao diện chính (Tkinter)
├── config.example.json     # Config mẫu (copy → config.json)
├── run.bat                 # Chạy nhanh trên Windows
├── core/
│   ├── translator.py       # Engine dịch song song
│   └── srt_parser.py       # Đọc/ghi file SRT
└── test_sample.srt         # File SRT mẫu để test
```

---

## ⚡ Chạy nhanh trên Windows

Double-click file `run.bat` hoặc:

```bat
run.bat
```

---

## 📖 Cách dùng Glossary

Trong ô **GLOSSARY** của sidebar, nhập theo định dạng:

```
Naruto = Naruto
Konoha = Làng Lá
Sensei = Thầy
```

Mỗi dòng 1 cặp `Tên gốc = Tên dịch`. Glossary sẽ được áp dụng nhất quán cho toàn bộ file.

---

## 🛠️ Cấu hình nâng cao (`config.json`)

| Key | Mặc định | Mô tả |
|-----|----------|-------|
| `api_keys` | `[]` | Danh sách API key (1 key = 1 worker) |
| `model` | `deepseek-v4-flash` | Model AI (`deepseek-v4-flash` hoặc `deepseek-v4-pro`) |
| `target_language` | `indonesian` | Ngôn ngữ đích |
| `content_type` | `auto` | Loại nội dung (`auto`, `film`, `anime`, `wuxia`, `news`, `documentary`) |
| `batch_size` | `40` | Số blocks mỗi lần gọi API |
| `glossary` | `{}` | Bảng thuật ngữ `{"Từ gốc": "Từ dịch"}` |

---

## 📄 License

MIT
