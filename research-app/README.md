# Universal Research App

Công cụ nghiên cứu tự động, dựa trên bằng chứng thực, được vận hành bởi Gemini AI + Google Search.

> **Phiên bản hiện tại:** v0.2 — Citation Engine  
> **Trạng thái:** Đã kiểm thử & triển khai, sẵn sàng dùng hàng ngày

---

## Tổng quan

Universal Research App nhận một câu hỏi nghiên cứu và tạo ra:

- Báo cáo phân tích có cấu trúc (tóm tắt, phát hiện chính, bằng chứng, kết luận)
- Trích dẫn số inline `[1]`, `[2]`… gắn trực tiếp vào nội dung
- Danh sách tài liệu tham khảo định dạng APA 7
- File Markdown xuất ra để lưu trữ hoặc tiếp tục chỉnh sửa

Mọi dữ liệu đều đến từ **Google Search grounding thật** — không bịa đặt nguồn.

---

## Yêu cầu hệ thống

| Yêu cầu | Chi tiết |
|---|---|
| Python | 3.10 trở lên |
| Gemini API Key | Miễn phí tại [aistudio.google.com](https://aistudio.google.com) |
| Git | Để triển khai lên Streamlit Cloud |

---

## Chạy cục bộ (Local)

```bash
# 1. Vào thư mục project
cd ~/Documents/AI/universal-skills/research/research-app

# 2. Tạo môi trường ảo
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# 3. Cài đặt thư viện
pip install -r requirements.txt

# 4. Tạo file .env
cp .env.example .env
# Mở .env và thêm: GEMINI_API_KEY=your_actual_api_key

# 5. Khởi động
streamlit run app.py
# Mở trình duyệt: http://localhost:8501
```

---

## Triển khai lên Streamlit Community Cloud (Khuyến nghị)

Cách này cho phép dùng app từ bất kỳ thiết bị nào, không cần mở máy tính cá nhân.

### Bước 1 — Đẩy code lên GitHub

Repository hiện tại: [harper-nguyen/universal-research](https://github.com/harper-nguyen/universal-research)

Nếu cần đẩy cập nhật mới:
```bash
cd ~/Documents/AI/universal-skills/research
git add -A
git commit -m "mô tả thay đổi"
git push
```

### Bước 2 — Kết nối Streamlit Cloud

1. Vào [share.streamlit.io](https://share.streamlit.io) và đăng nhập bằng GitHub
2. Chọn repository `universal-research`, branch `main`
3. Main file path: `research-app/app.py`

### Bước 3 — Thêm API Key (Secrets)

Trong phần **Advanced settings → Secrets**:
```toml
GEMINI_API_KEY = "your_actual_gemini_api_key"
```

### Bước 4 — Deploy

Nhấn **Deploy**. App sẽ chạy tại URL dạng:
`https://universal-research-harper-nguyen.streamlit.app`

---

## Cách sử dụng hiệu quả

### Đặt câu hỏi tốt

App hoạt động tốt nhất với câu hỏi **phân tích**, không phải câu hỏi tra cứu đơn giản:

| Không hiệu quả | Hiệu quả |
|---|---|
| "AI là gì?" | "Các mô hình AI nào đang dẫn đầu trong lĩnh vực xử lý ngôn ngữ tự nhiên năm 2024–2025 và điểm mạnh/yếu của từng mô hình?" |
| "Giá vàng hôm nay?" | "Các yếu tố vĩ mô nào đang ảnh hưởng đến giá vàng trong năm 2025 và xu hướng ngắn hạn là gì?" |
| "ChatGPT tốt không?" | "So sánh GPT-4o, Gemini 2.5 Pro và Claude Sonnet về khả năng lập luận, chi phí và ứng dụng thực tế" |

### Chọn độ sâu phân tích phù hợp

| Chế độ | Khi nào dùng |
|---|---|
| **Quick Summary** | Cần nắm nhanh tổng quan trong 1–2 phút |
| **Standard** | Nghiên cứu thường ngày, cân bằng giữa chiều rộng và chiều sâu |
| **Deep Dive** | Phân tích học thuật, ra quyết định quan trọng, cần trích dẫn đầy đủ |

### Làm gì với kết quả

- **Đọc inline citations** `[1]`, `[2]` để biết claim nào được hỗ trợ bởi nguồn nào
- **Kiểm tra References** — mỗi nguồn đều có URL thực để mở và đọc trực tiếp
- **Download report (.md)** — lưu vào Obsidian, Notion, hoặc bất kỳ editor nào

---

## Kiến trúc kỹ thuật

```
research/
├── SKILL.md                    ← Bộ nguyên tắc nghiên cứu (nguồn sự thật duy nhất)
└── research-app/
    ├── app.py                  ← Ứng dụng Streamlit chính
    ├── citations.py            ← Citation Engine: Source model, APA 7, dedup, inline [N]
    ├── requirements.txt        ← Thư viện Python
    ├── test_smoke.py           ← 13 kiểm thử tích hợp cơ bản
    ├── test_citations.py       ← 47 kiểm thử đơn vị + adversarial
    ├── test_sdk_integration.py ← Kiểm thử schema Gemini SDK thực tế
    └── .streamlit/config.toml  ← Cấu hình giao diện
```

**Luồng xử lý:**
```
Câu hỏi của bạn
  → Gemini API (kèm google_search tool)
      → Google Search grounding (tìm nguồn thực)
          → SKILL.md (định hướng phân tích)
              → Báo cáo + citations [N] + ## References
```

---

## Giới hạn hiện tại (v0.2)

| Giới hạn | Mô tả |
|---|---|
| **Metadata nguồn** | Chỉ có tiêu đề và URL; không có tác giả, năm, tạp chí, DOI |
| **Inline citations** | Phụ thuộc Gemini trả về `grounding_supports`; nếu không có, vẫn hiển thị References |
| **Xác minh nguồn** | Dùng search snippet, không đọc toàn văn bài báo |
| **Rate limit** | Free tier ~15 requests/phút; app tự thử model dự phòng nếu bị giới hạn |
| **Lưu trữ** | Không lưu lịch sử; mỗi lần tải lại trang là bắt đầu mới |

---

## Lộ trình nâng cấp đề xuất

### Ngay bây giờ — Dùng hiệu quả hơn
- Đặt câu hỏi phân tích, không phải tra cứu đơn giản
- Dùng **Deep Dive** cho nghiên cứu quan trọng
- Lưu báo cáo `.md` vào Obsidian để xây dựng knowledge base cá nhân

### v0.3 — Metadata học thuật *(sắp tới)*
- Tích hợp OpenAlex / Crossref để điền tác giả, năm, tạp chí, DOI
- APA 7 đầy đủ thay vì chỉ tiêu đề + URL

### v0.4 — Lịch sử & lưu trữ
- Lưu lịch sử câu hỏi và báo cáo theo phiên
- Export PDF hoặc HTML

### v0.5 — Nguồn học thuật chuyên biệt
- Tích hợp Semantic Scholar cho bài báo khoa học
- Hỗ trợ tra cứu tài liệu y khoa (PubMed)

---

## Kiểm thử

```bash
source venv/bin/activate
python test_smoke.py            # 13 smoke tests
python test_citations.py        # 47 unit + adversarial tests
python test_sdk_integration.py  # SDK schema integration
```

Kết quả mong đợi: **60 / 60 PASS**
