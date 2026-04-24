# ChatbotV2

Chatbot RAG hai miền — HR nội bộ + chính sách bên ngoài, giao diện và phản hồi tiếng Việt.

**Stack:** FastAPI + Next.js 15 + Gemini (`gemini-3.1-flash-lite-preview`) + ChromaDB + Microsoft Entra ID + sentence-transformers (cross-encoder rerank).

> **Lưu ý:** thư mục `deploy/`, `doc/`, `plans/`, file `docker-compose*.yml` và `backend/.env` / `frontend/.env*` đều **không commit lên git** (xem `.gitignore`). Tài liệu vận hành nội bộ chỉ tồn tại local.

---

## Khởi động nhanh (Dev)

### 1. Backend

```bash
cd backend
cp .env.example .env          # điền GEMINI_API_KEY, AZURE_AD_*, FAKE_AUTH_EMAIL=admin@company.com (dev)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install sentence-transformers   # bắt buộc để cross-encoder rerank hoạt động

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Kiểm tra: `curl http://localhost:8000/healthz` → `{"status":"ok"}`

Lần đầu start chậm thêm ~15s vì download model `cross-encoder/ms-marco-MiniLM-L-6-v2` từ HuggingFace Hub. Lần sau dùng cache local nên nhanh.

### 2. Frontend

```bash
cd frontend
cp .env.local.example .env.local    # điền NEXTAUTH_SECRET, AZURE_AD_*, NEXT_PUBLIC_API_URL=http://localhost:8000/api
npm install
npm run dev
```

Mở: http://localhost:3000

### 3. Tạo dữ liệu mẫu (tùy chọn)

```bash
cd backend
.venv/Scripts/python.exe scripts/generate_cskh_pdf.py   # tạo data/cskh-tech-store.pdf 4 trang
```

Vào **Quản trị → Tài liệu** để upload PDF, đợi status `processing` → `ready`, sau đó test ở `/ask` (External) hoặc `/chat` (Internal).

---

## Cấu trúc dự án (chỉ phần được commit)

```
chatbotv2/
  backend/          FastAPI app, RAG pipeline, services, models, scripts
    app/
    scripts/        generate_cskh_pdf.py — sinh PDF CSKH mẫu
    tests/
    requirements.txt
    .env.example
  frontend/         Next.js 15 App Router + Tailwind, brand #253956, UI tiếng Việt
    src/
    package.json
    .env.local.example
  README.md
  SETUP.md
  .gitignore
```

Các phần **không commit** (giữ local):
- `deploy/` — Dockerfiles helpers, nginx config, systemd unit, install/deploy/backup scripts cho VM Debian
- `doc/` — kế hoạch, đặc tả phase, báo cáo subagent, hướng dẫn triển khai chi tiết, chat-flow architecture deep-dive
- `plans/` — kế hoạch nội bộ
- `docker-compose*.yml` — dev và prod stack
- `backend/.env`, `frontend/.env*` — secrets

---

## Tính năng chính

| Mục | Mô tả |
|---|---|
| **Hai chế độ** | `/chat` (Internal, đăng nhập Microsoft Entra ID) và `/ask` (External, anonymous, rate-limited) |
| **RAG pipeline** | Hybrid retrieval (vector Gemini + BM25) → RRF merge → cross-encoder rerank → top 3 chunks |
| **Stateful chat** | Session LRU 500 / TTL 30 phút, rehydrate 20 turns gần nhất từ DB khi cold-start |
| **Gemini context cache** | Tự tạo cache khi corpus đủ lớn (>1024 tokens), giảm cost token đáng kể |
| **Bảng quản trị** | CRUD tài liệu PDF, cài đặt runtime (không cần restart), danh sách quản trị viên, lịch sử trò chuyện (xuất CSV, xóa theo bộ lọc) |
| **Fail-closed** | Khi RAG retrieve 0 chunks → trả fallback cố định, không gọi LLM (tránh hallucinate) |
| **Quan sát** | JSON logs, metrics ring buffer (`/admin/metrics`), timing middleware ghi từng stage |
| **i18n** | Toàn bộ UI và error messages tiếng Việt; system prompt Gemini giữ tiếng Anh để bảo toàn chất lượng RAG |

---

## Cài đặt runtime quan trọng (qua /admin/settings)

| Khóa | Mặc định | Ghi chú |
|---|---|---|
| `TOP_K_FINAL` | 3 | Số chunks gửi cho LLM sau rerank |
| `TOP_K_VECTOR` | 12 | Số candidates lấy từ vector + BM25 trước RRF |
| `LLM_TEMPERATURE` | 0.2 | Tăng → đa dạng nhưng dễ hallucinate |
| `LLM_MAX_OUTPUT_TOKENS` | 800 | Cắt câu trả lời dài |
| `ANONYMOUS_SHOW_SOURCES` | `true` | Đặt `false` để ẩn chip nguồn ở `/ask` (external mode) |
| `MAX_UPLOAD_SIZE_MB` | 20 | Giới hạn file PDF upload |
| `HISTORY_RETENTION_DAYS` | 90 | Sau ngưỡng này, background task xóa turn cũ |
| `RATE_LIMIT_EXTERNAL_PER_MIN` | 10 | Per IP cho `/external/chat` |
| `RATE_LIMIT_INTERNAL_PER_MIN` | 60 | Per email cho `/internal/chat` |

---

## Trạng thái phát triển

Tất cả 9 phase đã hoàn thành (xem `doc/plan/plan.md` local). 253 backend tests passing, 12 Playwright E2E specs.

Có sẵn:
- ✅ Dual-mode chat với SSE streaming
- ✅ MSAL Entra ID + JWT validation backend
- ✅ Hybrid RAG (vector + BM25 + rerank) hoạt động đầy đủ
- ✅ Bảng quản trị: tài liệu, cài đặt, quản trị viên, lịch sử
- ✅ Logs, metrics, audit trail
- ✅ UI tiếng Việt hoàn chỉnh

---

## Câu hỏi thường gặp

**Q: Vì sao "Bạn tên là gì?" trả lời fallback "Tôi không tìm thấy thông tin..."?**
A: Fail-closed guard. Khi corpus rỗng hoặc câu hỏi không match chunk nào → bot không gọi LLM để tránh hallucinate. Upload tài liệu giới thiệu (ví dụ `scripts/generate_cskh_pdf.py`) để bot trả lời được câu chào hỏi.

**Q: Cross-encoder rerank không hoạt động?**
A: Cài `pip install sentence-transformers` và restart backend. Log sẽ thấy `CrossEncoderReranker loaded: cross-encoder/ms-marco-MiniLM-L-6-v2`.

**Q: Lỗi "Objects are not valid as a React child" khi chat?**
A: Đã fix trong `use-chat-stream.ts` và `api-client.ts` — backend đôi khi trả `detail` dạng object thay vì string, frontend giờ ép về string trước khi render.

**Q: Bot không trả lời tiếng Việt dù UI tiếng Việt?**
A: System prompt Gemini cố ý giữ tiếng Anh để chỉ thị tone/citation cho mô hình. Để bot trả lời tiếng Việt, sửa `backend/app/llm/prompts/internal_system.txt` và `external_system.txt` thêm câu "Always respond in Vietnamese".
