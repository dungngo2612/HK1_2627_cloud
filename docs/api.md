# EquipmentDesk API

API chạy cùng ứng dụng local mặc định tại `http://127.0.0.1:8080`. Endpoint dữ liệu
cần cookie session đã đăng nhập. Mọi POST/PUT và upload cần CSRF token thuộc đúng
session đó. API không dùng bearer token/JWT.

## Endpoint

| Phương thức | URL | Đăng nhập | CSRF |
| --- | --- | --- | --- |
| GET | `/health/live` | Không | Không |
| GET | `/health/ready` | Không | Không |
| GET | `/api/csrf-token` | Không | Không |
| GET | `/api/equipment?q=...&page=1` | Có | Không |
| POST | `/api/equipment` | Có | Có |
| GET | `/api/equipment/<equipment_id>` | Có | Không |
| PUT | `/api/equipment/<equipment_id>` | Có | Có |
| GET | `/api/loans?page=1` | Có | Không |
| POST | `/api/loans` | Có | Có |
| GET | `/api/loans/<loan_id>` | Có | Không |
| POST | `/api/loans/<loan_id>/return` | Có | Có |
| POST | `/api/loans/<loan_id>/attachments` | Có | Có |
| GET | `/api/attachments/<attachment_uuid>` | Có | Không |
| GET | `/api/attachments/<attachment_uuid>/download` | Có | Không |

Nếu chưa đăng nhập, API dữ liệu trả JSON 401; web chuyển đến `/login`. CSRF thiếu,
sai hoặc hết hạn trả 400. Dùng cùng hostname và scheme cho login/API để cookie session
được gửi đúng. Token mặc định hết hạn sau 60 phút; lấy token mới qua endpoint CSRF.

## Đăng nhập và lấy CSRF

Sau khi chạy `seed-demo-data`, dùng `DEMO_USERNAME` và mật khẩu đã dùng khi user được
tạo lần đầu. Nếu chỉ tạo user, chạy `create-demo-user`. Thay giá trị mẫu trong Terminal:

```bash
EQUIPMENTDESK_USERNAME='demo'
printf 'Mật khẩu demo: '
read -r -s EQUIPMENTDESK_PASSWORD
printf '\n'
EQUIPMENTDESK_COOKIES="$(mktemp)"

# Tạo anonymous session và lấy token cho form login.
EQUIPMENTDESK_CSRF="$(curl -fsS -c "$EQUIPMENTDESK_COOKIES" \
  http://127.0.0.1:8080/api/csrf-token \
  | python -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')"

curl -i -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  --data-urlencode "username=$EQUIPMENTDESK_USERNAME" \
  --data-urlencode "password=$EQUIPMENTDESK_PASSWORD" \
  --data-urlencode "csrf_token=$EQUIPMENTDESK_CSRF" \
  http://127.0.0.1:8080/login

# Login xoay session; lấy token mới trước các thao tác thay đổi dữ liệu.
EQUIPMENTDESK_CSRF="$(curl -fsS -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  http://127.0.0.1:8080/api/csrf-token \
  | python -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')"
```

Gửi cookie với `-b "$EQUIPMENTDESK_COOKIES"`; với POST/PUT, thêm
`-H "X-CSRFToken: $EQUIPMENTDESK_CSRF"`. Login thành công trả 303. Login sai trả 401
với trang form và thông báo chung. Logout là POST `/logout`, cũng yêu cầu CSRF.

## Thiết bị

```bash
curl -sS -b "$EQUIPMENTDESK_COOKIES" \
  'http://127.0.0.1:8080/api/equipment?q=DEMO-EQ-006&page=1'

curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"code":"LT-LOCAL-001","name":"Laptop kiểm thử","category":"Máy tính","location":"Phòng 201"}' \
  http://127.0.0.1:8080/api/equipment

curl -i -X PUT -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"code":"LT-LOCAL-001","name":"Laptop kiểm thử","category":"Máy tính","location":"Phòng kỹ thuật","status":"MAINTENANCE"}' \
  "http://127.0.0.1:8080/api/equipment/$EQUIPMENT_ID"
```

Trước PUT, đặt `EQUIPMENT_ID` bằng id trong response POST hoặc GET.

List trả `{items, page, per_page, total, pages}`. POST trả 201 và `Location`; PUT trả
200. Trường `id`, timestamps và trạng thái BORROWED do client cung cấp không được chấp
nhận. Chỉ được đổi trực tiếp AVAILABLE ↔ MAINTENANCE; mượn/trả phải qua API phiếu.

## Phiếu mượn, file và trả thiết bị

Chọn một thiết bị AVAILABLE có thật từ GET `/api/equipment`. Đặt `EQUIPMENT_ID` bên
dưới bằng ID đó; các request này chạy luồng mượn, đính
kèm file, tải lại đúng byte và trả thiết bị:

```bash
TODAY="$(date +%F)"
DUE="$(date -v+7d +%F)" # cú pháp ngày macOS
EQUIPMENT_ID=6 # đặt bằng id AVAILABLE lấy từ GET /api/equipment

# Tạo phiếu; actor/user_id được lấy từ session, không truyền trong body.
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d "{\"loan_date\":\"$TODAY\",\"expected_return_date\":\"$DUE\",\"note\":\"Kiểm tra local\",\"items\":[{\"equipment_id\":$EQUIPMENT_ID,\"condition_before\":\"Hoạt động tốt\"}]}" \
  http://127.0.0.1:8080/api/loans
```

Response 201 chứa `id`; dùng ID đó cho các bước dưới:

```bash
LOAN_ID=1 # thay bằng id trong response tạo phiếu

# Upload multipart/form-data, field tên file là "file". Để curl tự đặt Content-Type/boundary.
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -F 'file=@/path/to/bien-ban.pdf' \
  "http://127.0.0.1:8080/api/loans/$LOAN_ID/attachments"

# Thay ATTACHMENT_UUID bằng id trong response; tải về rồi đối chiếu SHA-256.
curl -f -b "$EQUIPMENTDESK_COOKIES" \
  "http://127.0.0.1:8080/api/attachments/ATTACHMENT_UUID/download" \
  -o bien-ban-tai-ve.pdf
shasum -a 256 /path/to/bien-ban.pdf bien-ban-tai-ve.pdf

# Trả đủ chính xác equipment_id đã có trong phiếu.
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d "{\"actual_return_date\":\"$TODAY\",\"items\":[{\"equipment_id\":$EQUIPMENT_ID,\"condition_after\":\"Đã kiểm tra, đủ phụ kiện\"}]}" \
  "http://127.0.0.1:8080/api/loans/$LOAN_ID/return"
```

POST loan trả 201, return trả 200; thiết bị chuyển BORROWED khi mượn và AVAILABLE khi
trả. Mượn nhiều thiết bị thì gửi mỗi thiết bị một object trong `items` và trả lại đủ
các ID đó. Chỉ PDF/PNG/JPEG hợp lệ tối đa 10 MiB được chấp nhận. Upload trả metadata
gồm attachment UUID, MIME xác minh, size và SHA-256; GET metadata không trả nội dung.
Download trả attachment và kiểm tra lại kích thước/hash trước khi gửi.

Web tương ứng: `/equipment`, `/equipment/new`, `/loans`, `/loans/new`,
`/loans/<id>`; chi tiết phiếu có upload/download và form trả toàn bộ. Các form tự gửi
CSRF. Logout bằng nút web hoặc POST `/logout` kèm token.

## Health check và lỗi

- GET `/health/live`: công khai, HTTP 200 khi app nhận request; database/storage là
  `not_checked`.
- GET `/health/ready`: công khai, `SELECT 1` và file probe read/write trong thư mục
  uploads đã tồn tại; HTTP 200 nếu sẵn sàng, 503 nếu database hoặc storage lỗi. Không
  tạo thư mục khi thiếu; tạo `data/uploads` nếu chưa seed/upload.
- API lỗi dùng `{error: {code, message, fields}}`. 401 đăng nhập, 400 CSRF/JSON, 404
  không tồn tại, 409 conflict, 413 quá cỡ, 415 sai media type, 422 validation và 503
  dependency không sẵn sàng. Response không trả secret hoặc stack trace.

Xem thêm hướng dẫn app và database trong [README.md](../README.md). Tài liệu API này
không chứa user/password thật; credentials phải lấy từ cấu hình local.

Sau khi hoàn tất, có thể đăng xuất và bỏ cookie jar:

```bash
curl -i -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  --data-urlencode "csrf_token=$EQUIPMENTDESK_CSRF" \
  http://127.0.0.1:8080/logout
rm "$EQUIPMENTDESK_COOKIES"
unset EQUIPMENTDESK_PASSWORD EQUIPMENTDESK_CSRF EQUIPMENTDESK_COOKIES
```
