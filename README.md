# Bảng theo dõi thị trường — hướng dẫn cài đặt

Hệ thống gồm 3 phần, đều chạy miễn phí trên GitHub (trừ phí API Claude, khoảng 3–5 đô/tháng):

```
GitHub Actions (theo lịch)
  ├─ vnstock: giá + báo cáo tài chính 190 mã  ──┐
  ├─ RSS: tin tức CafeF, VnExpress, Vietstock   ├─► code tính chỉ báo, backtest, điểm nổi bật
  ├─ Claude Haiku: viết nhận định               │
  ├─ Claude Sonnet: kiểm chứng (✅ / ⚠️)        ┘
  ├─► docs/data.json  ──► Dashboard (GitHub Pages)
  └─► Bot Zalo: bản tin 8:00 và 15:30
```

## Lịch chạy (giờ Việt Nam)
| Giờ | Việc |
|---|---|
| 08:00 thứ 2–6 | Gửi bản tin sáng qua Zalo |
| 15:30 thứ 2–6 | Cập nhật giá, kỹ thuật, tin; nhận định ngành + 8 mã nổi bật; gửi bản tin chiều |
| 10:00 thứ 7 | Nhận định cho tất cả 190 mã |
| Ngày 25 tháng 1/4/7/10 | Tải lại báo cáo tài chính quý |

## Cài đặt (làm 1 lần, khoảng 20 phút)

1. **Tạo kho GitHub**: đăng nhập github.com → New repository → tên ví dụ `bang-theo-doi` → chọn *Private* → Create. Tải toàn bộ thư mục này lên (Add file → Upload files, kéo cả thư mục vào).
2. **Thêm khoá bí mật**: Settings → Secrets and variables → Actions → *New repository secret*:
   - `ANTHROPIC_API_KEY`: tạo tại platform.claude.com (nạp trước ~5 đô). Bỏ trống nếu chưa muốn bật AI — hệ thống vẫn chạy, chỉ thiếu phần nhận định.
   - `ZALO_BOT_TOKEN`: lấy khi tạo bot ở bot.zaloplatforms.com.
3. **Bật dashboard**: Settings → Pages → Source: *Deploy from a branch* → Branch `main`, thư mục `/docs` → Save. Sau 1–2 phút có địa chỉ dạng `https://<tên>.github.io/bang-theo-doi/`.
   (Kho *Private* cần gói GitHub trả phí để bật Pages; nếu dùng gói miễn phí thì để kho *Public* — dữ liệu chỉ là số liệu thị trường công khai, không có khoá bí mật.)
4. **Ghi địa chỉ dashboard vào bản tin**: Settings → Secrets and variables → Actions → tab *Variables* → `DASHBOARD_URL` = địa chỉ ở bước 3.
5. **Chạy thử lần đầu**: tab Actions → `cap-nhat-du-lieu` → *Run workflow* → mode `daily`. Xem log để kiểm tra.

## Kiểm tra lần chạy đầu tiên (quan trọng)
- **vnstock**: thư viện hay đổi tên hàm/cột giữa các phiên bản. Nếu log báo lỗi ở `[giá]` hoặc `[BCTC]`, mở `src/data_source.py` — mọi chỗ đọc vnstock nằm ở đây; bảng `RATIO_ALIASES` dò tên cột theo nhiều phiên bản.
- **Đối chiếu số liệu**: mở 5–10 mã trên dashboard, so giá, RSI, MA với TradingView/FireAnt. Lệch > 1% → báo để sửa.
- **Cảnh báo dữ liệu**: nếu một mã hiện "⚠️ Phiên ... vượt biên độ", nguồn đang trả giá chưa điều chỉnh cho cổ tức/phát hành thêm. Xem mục dưới.
- **RSS**: nếu một nguồn tin lỗi, log ghi `[news] bỏ qua ...` — sửa đường dẫn trong `src/news.py`.

## Điều chỉnh giá khi phát hành thêm / cổ tức
Ngày GDKHQ, giá tham chiếu bị hạ. Nếu không điều chỉnh lịch sử, biểu đồ có "vực" giả và MA/RSI/đỉnh 52 tuần sai.
`src/adjust.py` có công thức của Sở GDCK:
`P_ref = (P_trước − cổ tức tiền + giá PH × tỷ lệ mua) / (1 + tỷ lệ mua + tỷ lệ thưởng)`
và hàm `suspicious_gaps()` tự phát hiện phiên giá đổi vượt biên độ (dấu hiệu dữ liệu chưa điều chỉnh).

## Test bot Zalo
1. Tạo bot tại bot.zaloplatforms.com, lấy token.
2. Nhắn `/start` cho bot từ Zalo của bạn.
3. Chạy workflow với mode `morning` → bot gửi bản tin cho mọi người đã nhắn `/start`.
4. Nếu không nhận được: mở `src/zalo.py`, so tên hàm `sendMessage` / `getUpdates` và tham số với tài liệu của Zalo Bot Platform.

## Chạy thử trên máy (không cần mạng, không cần khoá)
```bash
pip install -r requirements.txt
MOCK=1 python src/build.py --no-send
python -m http.server -d docs 8000   # mở http://localhost:8000
```

## Thay đổi thường gặp
- Đổi danh sách mã/ngành: `config/sectors.json`.
- Đổi model AI: biến môi trường `WRITER_MODEL`, `CHECKER_MODEL` (mặc định `claude-haiku-5-5`, `claude-sonnet-5-5`).
- Đổi tiêu chí "mã nổi bật": hàm `score()` trong `src/build.py`.
- Thêm tín hiệu backtest: `src/backtest.py`.

## Lưu ý pháp lý
Hệ thống được thiết kế để **mô tả dữ liệu, không khuyến nghị mua/bán/nắm giữ** (hoạt động tư vấn đầu tư chứng khoán cần giấy phép UBCKNN). Prompt AI cấm ngôn ngữ khuyến nghị và bước kiểm chứng gắn ⚠️ nếu lọt. Trước khi thu phí, nên hỏi ý kiến người có chuyên môn pháp lý.
