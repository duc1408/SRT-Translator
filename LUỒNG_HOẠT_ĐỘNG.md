# 📋 LUỒNG HOẠT ĐỘNG ỨNG DỤNG SRT-TRANSLATOR

## 🎯 Tổng quan
Ứng dụng dịch phụ đề SRT tự động với giao diện đồ họa, hỗ trợ dịch song song đa luồng và tự phục hồi lỗi thông minh.

---

## 🔄 LUỒNG HOẠT ĐỘNG CHÍNH

### 1️⃣ KHỞI ĐỘNG ỨNG DỤNG
```
┌─────────────────────────────────────┐
│   Người dùng chạy: python app.py    │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Khởi tạo giao diện Tkinter         │
│  - Tải cấu hình từ config.json      │
│  - Thiết lập theme tối (dark mode)  │
│  - Hiển thị sidebar + panel chính   │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Hiển thị vùng kéo thả file         │
│  "Kéo thả file .srt vào đây"        │
└─────────────────────────────────────┘
```

---

### 2️⃣ THÊM FILE PHỤ ĐỀ
```
┌──────────────────────────────────────────────────────┐
│  Người dùng thêm file (3 cách):                      │
│  ① Nhấn nút "＋ Thêm file"                           │
│  ② Nhấn nút "📁 Thêm folder"                         │
│  ③ Kéo thả file/folder vào vùng drop zone           │
└──────────────┬───────────────────────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Lọc file .srt                      │
│  - Kiểm tra phần mở rộng            │
│  - Loại bỏ file trùng lặp           │
│  - Đọc kích thước file              │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Hiển thị danh sách file            │
│  - Tên file                         │
│  - Kích thước (KB)                  │
│  - Trạng thái: "Chờ dịch"           │
│  - Checkbox đánh dấu chọn           │
└─────────────────────────────────────┘
```

---

### 3️⃣ CẤU HÌNH DỊCH THUẬT
```
┌─────────────────────────────────────┐
│  SIDEBAR - Cài đặt dịch thuật      │
├─────────────────────────────────────┤
│  🔑 API KEYS                        │
│  - Nhập 1 hoặc nhiều OpenRouter key │
│  - Mỗi key = 1 worker song song     │
├─────────────────────────────────────┤
│  🌐 NGÔN NGỮ ĐÍCH                   │
│  - Indonesian, Thai, Vietnamese...  │
│  - 16 ngôn ngữ được hỗ trợ          │
├─────────────────────────────────────┤
│  🎬 LOẠI NỘI DUNG                   │
│  - Tự động nhận diện                │
│  - Film/Drama, Anime, Wuxia...      │
├─────────────────────────────────────┤
│  🤖 MODEL AI                        │
│  - Chọn model dịch (7 options)      │
│  - Mặc định: ling-2.6-flash         │
├─────────────────────────────────────┤
│  📦 BATCH SIZE                      │
│  - Số blocks dịch mỗi lần (10-100)  │
│  - Mặc định: 45 blocks              │
└─────────────────────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Nhấn "💾 Lưu cấu hình"             │
│  → Ghi vào config.json              │
└─────────────────────────────────────┘
```

---

### 4️⃣ BẮT ĐẦU DỊCH - LUỒNG CHÍNH
```
┌─────────────────────────────────────┐
│  Nhấn "▶ BẮT ĐẦU DỊCH"              │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  KIỂM TRA ĐIỀU KIỆN                 │
│  ✓ Có ít nhất 1 API key?            │
│  ✓ Có file nào được chọn?           │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  ĐỌC VÀ PHÂN TÍCH FILE SRT          │
│  (core/srt_parser.py)               │
├─────────────────────────────────────┤
│  1. Tự động phát hiện encoding      │
│     - UTF-8 BOM, UTF-8, GBK, CP1252 │
│  2. Sửa lỗi định dạng SRT           │
│     - Chuyển dấu . thành ,          │
│     - Loại bỏ ký tự đặc biệt        │
│  3. Tách thành các SrtBlock         │
│     - idx: số thứ tự                │
│     - timestamp: thời gian          │
│     - text: nội dung phụ đề         │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  PHÁT HIỆN NGÔN NGỮ NGUỒN           │
│  - Quét 50 blocks đầu               │
│  - Nhận diện: Chinese, Japanese,    │
│    Korean, Arabic, Thai, Cyrillic   │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  CHIA CÔNG VIỆC SONG SONG           │
│  - Số worker = min(số key, 20)      │
│  - Chia blocks thành N chunks       │
│  - Mỗi worker xử lý 1 chunk         │
└──────────────┬──────────────────────┘
               ↓
         ┌─────┴─────┐
         ↓           ↓
    [Worker 1]  [Worker 2] ... [Worker N]
         ↓           ↓
    (Xem chi tiết bên dưới)
```

---

### 5️⃣ QUY TRÌNH DỊCH CỦA MỖI WORKER
```
┌─────────────────────────────────────────────────────┐
│  WORKER N - Xử lý 1 chunk blocks                    │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  CHIA CHUNK THÀNH CÁC BATCH                         │
│  - Mỗi batch = batch_size blocks (mặc định 45)      │
│  - Bỏ qua blocks âm nhạc: ♪, [Music], [Applause]   │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  XỬLÝ TỪNG BATCH                                    │
└──────────────┬──────────────────────────────────────┘
               ↓
    ╔═══════════════════════════════════════════════╗
    ║  LAYER 1: GỌI API VỚI RETRY                   ║
    ╚═══════════════════════════════════════════════╝
               ↓
┌─────────────────────────────────────────────────────┐
│  1. Tạo prompt cho AI                               │
│     System: "Bạn là chuyên gia dịch phụ đề..."     │
│     User: "[0] text1\n[1] text2\n..."              │
├─────────────────────────────────────────────────────┤
│  2. Gửi request đến OpenRouter API                  │
│     - Model: đã chọn                                │
│     - Temperature: 0.25                             │
│     - Timeout: 90 giây                              │
├─────────────────────────────────────────────────────┤
│  3. Xử lý response                                  │
│     - Parse JSON: [{"idx":0,"text":"..."}]          │
│     - Fallback: regex [N] text                      │
├─────────────────────────────────────────────────────┤
│  4. Retry nếu thất bại (tối đa 4 lần)              │
│     - HTTP 429/503: đợi 2^n * 2 giây               │
│     - Lỗi khác: đợi 3 giây                         │
└──────────────┬──────────────────────────────────────┘
               ↓
    ╔═══════════════════════════════════════════════╗
    ║  LAYER 1B: KIỂM TRA KẾT QUẢ                   ║
    ╚═══════════════════════════════════════════════╝
               ↓
┌─────────────────────────────────────────────────────┐
│  Phát hiện blocks chưa dịch:                        │
│  ✗ Block bị thiếu trong response                    │
│  ✗ Text giống hệt nguồn (không thay đổi)           │
│  ✗ Vẫn còn ký tự ngôn ngữ nguồn (>50%)             │
└──────────────┬──────────────────────────────────────┘
               ↓
         ┌─────┴─────┐
         ↓           ↓
    [Có lỗi]    [Không lỗi]
         ↓           ↓
┌─────────────┐  ┌──────────────┐
│ RETRY NGAY  │  │ Tiếp tục     │
│ chỉ blocks  │  │ batch tiếp   │
│ bị lỗi      │  │              │
│ (3 lần)     │  │              │
└─────────────┘  └──────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│  Cập nhật thanh tiến trình                          │
│  - Số blocks đã xong / tổng số                      │
│  - Phần trăm hoàn thành                             │
└─────────────────────────────────────────────────────┘
```

---

### 6️⃣ TỰ PHỤC HỒI ĐA LỚP (SELF-HEALING)
```
┌─────────────────────────────────────────────────────┐
│  Tất cả workers hoàn thành                          │
│  → Gộp kết quả theo thứ tự                          │
└──────────────┬──────────────────────────────────────┘
               ↓
    ╔═══════════════════════════════════════════════╗
    ║  LAYER 3: TỰ PHỤC HỒI VỚI MODEL CHÍNH         ║
    ╚═══════════════════════════════════════════════╝
               ↓
┌─────────────────────────────────────────────────────┐
│  Quét tìm blocks chưa dịch                          │
│  - So sánh với văn bản nguồn                        │
│  - Phát hiện ký tự ngôn ngữ nguồn còn sót           │
└──────────────┬──────────────────────────────────────┘
               ↓
         ┌─────┴─────┐
         ↓           ↓
    [Có lỗi]    [Không lỗi]
         ↓           ↓
┌─────────────┐  ┌──────────────┐
│ VÒNG 1      │  │ ✅ HOÀN      │
│ Retry với   │  │    THÀNH     │
│ key khác    │  │              │
└──────┬──────┘  └──────────────┘
       ↓
┌─────────────┐
│ VÒNG 2      │
│ Retry với   │
│ key khác    │
└──────┬──────┘
       ↓
┌─────────────┐
│ VÒNG 3      │
│ Retry với   │
│ key khác    │
└──────┬──────┘
       ↓
    [Vẫn còn lỗi?]
       ↓
    ╔═══════════════════════════════════════════════╗
    ║  LAYER 4: FALLBACK MODEL CASCADE              ║
    ║  (Dịch BẮT BUỘC - không bỏ cuộc!)            ║
    ╚═══════════════════════════════════════════════╝
               ↓
┌─────────────────────────────────────────────────────┐
│  Thử lần lượt 5 model dự phòng:                     │
│  1. google/gemini-2.5-flash-lite:free               │
│  2. google/gemma-3-27b-it:free                      │
│  3. meta-llama/llama-3.3-70b-instruct:free          │
│  4. deepseek/deepseek-chat                          │
│  5. openai/gpt-4o-mini                              │
├─────────────────────────────────────────────────────┤
│  Mỗi model thử 3 vòng với các key khác nhau        │
│  Dừng khi: 100% blocks đã dịch HOẶC hết model      │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  KẾT QUẢ CUỐI CÙNG                                  │
│  ✅ 100% dịch xong: "🎉 Hoàn thành 100%!"           │
│  ⚠️  Còn lỗi: "⚠️ X blocks không dịch được"         │
└─────────────────────────────────────────────────────┘
```

---

### 7️⃣ LƯU KẾT QUẢ
```
┌─────────────────────────────────────────────────────┐
│  GHI FILE SRT ĐÃ DỊCH                               │
│  (core/srt_parser.py - write_srt)                   │
├─────────────────────────────────────────────────────┤
│  Đường dẫn output:                                  │
│  <thư_mục_gốc>/output/<MÃ_NGÔN_NGỮ>/<tên_file>     │
│                                                     │
│  Ví dụ:                                             │
│  D:\Movies\movie.srt                                │
│  → D:\Movies\output\VI\movie.srt                    │
├─────────────────────────────────────────────────────┤
│  Định dạng:                                         │
│  - Encoding: UTF-8 with BOM                         │
│  - Line ending: \n (Unix style)                     │
│  - Cấu trúc: idx → timestamp → text → blank         │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  CẬP NHẬT GIAO DIỆN                                 │
│  - Trạng thái file: "✅ Hoàn thành"                 │
│  - Log: "💾 Đã lưu: <đường_dẫn>"                    │
│  - Thanh tiến trình: 100%                           │
└─────────────────────────────────────────────────────┘
```

---

### 8️⃣ HOÀN TẤT
```
┌─────────────────────────────────────────────────────┐
│  Tất cả file đã xử lý xong                          │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  Hiển thị thông báo hoàn thành                      │
│  - Log: "✅ ĐÃ HOÀN THÀNH TOÀN BỘ!"                 │
│  - Title bar: "✅ Dịch xong! — SRT Subtitle..."     │
│  - Nút "▶ BẮT ĐẦU DỊCH" hiện lại                    │
└──────────────┬──────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────┐
│  Người dùng có thể:                                 │
│  ① Kiểm tra file output trong thư mục output/       │
│  ② Thêm file mới để dịch tiếp                       │
│  ③ Thay đổi cấu hình và dịch lại                    │
│  ④ Xóa danh sách và bắt đầu mới                     │
└─────────────────────────────────────────────────────┘
```

---

## 🛡️ CƠ CHẾ BẢO VỆ 4 LỚP

### Layer 1: Batch Validation (Kiểm tra từng batch)
- Kiểm tra ngay sau mỗi lần gọi API
- Phát hiện blocks bị thiếu hoặc giống hệt nguồn
- Retry ngay lập tức chỉ với blocks lỗi

### Layer 2: Content-Change Detection (Phát hiện thay đổi nội dung)
- So sánh văn bản nguồn vs đích
- Phát hiện ký tự ngôn ngữ nguồn còn sót (>50%)
- Đánh dấu blocks cần dịch lại

### Layer 3: Multi-Pass Self-Healing (Tự phục hồi đa vòng)
- 3 vòng retry với model chính
- Mỗi vòng dùng API key khác nhau
- Batch size nhỏ hơn (20 blocks) để chính xác

### Layer 4: Fallback Model Cascade (Dự phòng model)
- Tự động chuyển sang 5 model dự phòng
- Mỗi model thử 3 vòng
- **DỊCH BẮT BUỘC** - không bỏ cuộc đến khi 100%

---

## 📊 SƠ ĐỒ KIẾN TRÚC

```
┌─────────────────────────────────────────────────────────┐
│                    APP.PY (GUI)                         │
│  ┌───────────────┐              ┌──────────────────┐    │
│  │   SIDEBAR     │              │   MAIN PANEL     │    │
│  │  - API Keys   │              │  - File List     │    │
│  │  - Settings   │              │  - Progress Bar  │    │
│  │  - Buttons    │              │  - Log Console   │    │
│  └───────────────┘              └──────────────────┘    │
└──────────────┬──────────────────────────────────────────┘
               ↓
┌──────────────────────────────────────────────────────────┐
│                  CORE MODULES                            │
├──────────────────────────────────────────────────────────┤
│  ┌────────────────────┐    ┌─────────────────────────┐  │
│  │  srt_parser.py     │    │   translator.py         │  │
│  │  - read_srt()      │    │   - translate_file()    │  │
│  │  - write_srt()     │    │   - _translate_chunk()  │  │
│  │  - detect_encoding │    │   - _api_call()         │  │
│  │  - repair_srt()    │    │   - _parse_response()   │  │
│  └────────────────────┘    │   - self_healing()      │  │
│                            │   - fallback_cascade()  │  │
│                            └─────────────────────────┘  │
└──────────────┬───────────────────────────────────────────┘
               ↓
┌──────────────────────────────────────────────────────────┐
│              OPENROUTER API                              │
│  - Nhận request dịch                                     │
│  - Gọi AI model (GPT, Claude, Gemini, Llama...)         │
│  - Trả về JSON response                                  │
└──────────────────────────────────────────────────────────┘
```

---

## 🎨 GIAO DIỆN NGƯỜI DÙNG

```
┌─────────────────────────────────────────────────────────────┐
│  SRT Subtitle Translator                              [_][□][X]│
├──────────────┬──────────────────────────────────────────────┤
│              │  Danh sách file phụ đề (.srt)               │
│  SRT         │  [＋ Thêm file] [📁 Folder] [✓ Chọn tất]    │
│  Subtitle    ├──────────────────────────────────────────────┤
│  Translator  │  ☑ │ Tên file      │ Kích thước │ Trạng thái│
│              │ ───┼───────────────┼────────────┼───────────│
│ ─────────    │  ☑ │ movie1.srt    │ 45.2 KB    │ Chờ dịch  │
│              │  ☑ │ movie2.srt    │ 38.7 KB    │ Chờ dịch  │
│ 🔑 API KEYS  │  ☑ │ episode3.srt  │ 52.1 KB    │ Chờ dịch  │
│ [________]   │                                              │
│ [________]   │  ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░  45%     │
│ 2 key(s)     │  1250/2800 blocks                           │
│              ├──────────────────────────────────────────────┤
│ 🌐 NGÔN NGỮ  │  📋 Nhật ký dịch thuật        [Xóa log]    │
│ [Vietnamese] │  ┌────────────────────────────────────────┐ │
│              │  │[18:30:15] ▶ Bắt đầu dịch 3 file(s)...  │ │
│ 🎬 LOẠI      │  │[18:30:16] 🚀 2 worker(s) song song      │ │
│ [Film/Drama] │  │[18:30:18] 📄 Đang dịch: movie1.srt     │ │
│              │  │[18:30:25] ✅ Worker 1 done (450 blocks) │ │
│ 🤖 MODEL     │  │[18:30:27] 💾 Đã lưu: output/VI/...     │ │
│ [ling-2.6..] │  │[18:30:28] ✅ Hoàn thành                 │ │
│              │  └────────────────────────────────────────┘ │
│ 📦 BATCH     │                                              │
│ [━━━━━━━━]   │                                              │
│ 45 blocks    │                                              │
│              │                                              │
│ [💾 Lưu cấu  │                                              │
│  hình]       │                                              │
│              │                                              │
│ [▶ BẮT ĐẦU   │                                              │
│  DỊCH]       │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

---

## 🔧 CÁC TÍNH NĂNG ĐẶC BIỆT

### ✨ Dịch song song đa luồng
- Mỗi API key = 1 worker độc lập
- Tối đa 20 workers cùng lúc
- Tự động chia đều công việc

### 🔄 Tự động phát hiện encoding
- UTF-8 BOM, UTF-8, GBK/GB2312, CP1252
- Sửa lỗi định dạng SRT tự động
- Loại bỏ ký tự đặc biệt

### 🛡️ Tự phục hồi thông minh
- 4 lớp bảo vệ chống lỗi
- Retry tự động với nhiều model
- Đảm bảo 100% blocks được dịch

### 🎯 Nhận diện ngôn ngữ nguồn
- Tự động phát hiện: Chinese, Japanese, Korean, Arabic, Thai, Cyrillic
- So sánh văn bản nguồn vs đích
- Phát hiện blocks chưa dịch chính xác

### 📊 Theo dõi tiến trình realtime
- Thanh tiến trình chi tiết
- Log console với màu sắc
- Cập nhật trạng thái từng file

### 🎨 Giao diện đẹp mắt
- Dark theme hiện đại
- Responsive, có thể resize
- Kéo thả file dễ dàng

---

## 📝 LƯU Ý QUAN TRỌNG

1. **API Keys**: Cần ít nhất 1 OpenRouter API key để hoạt động
2. **Định dạng output**: File được lưu trong `output/<MÃ_NGÔN_NGỮ>/`
3. **Encoding**: Output luôn là UTF-8 with BOM (tương thích Windows)
4. **Batch size**: Tăng = nhanh hơn nhưng tốn token, giảm = chính xác hơn
5. **Model**: Model miễn phí có thể chậm hoặc giới hạn rate-limit
6. **Retry**: Hệ thống tự động retry, không cần can thiệp thủ công

---

## 🚀 CÁCH SỬ DỤNG NHANH

1. **Chạy ứng dụng**: `python app.py`
2. **Nhập API key** vào ô "🔑 API KEYS"
3. **Chọn ngôn ngữ đích** (ví dụ: Vietnamese)
4. **Thêm file .srt** (kéo thả hoặc nhấn nút)
5. **Nhấn "▶ BẮT ĐẦU DỊCH"**
6. **Đợi hoàn thành** → File output trong thư mục `output/`

---

**Phiên bản**: 4.0 - Mandatory Translation  
**Ngày tạo**: 22/06/2026  
**Ngôn ngữ**: Tiếng Việt
