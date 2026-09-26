# EquipmentDesk

Ứng dụng Flask quản lý thiết bị, chạy local trên macOS và PyCharm.
Đã có đăng nhập/đăng xuất, danh sách/tìm kiếm/chi tiết/thêm/sửa thiết bị, tạo phiếu mượn
nhiều thiết bị và trả toàn bộ phiếu bằng web tiếng Việt và API dùng session. Tất cả user
đã đăng nhập có cùng quyền vận hành dữ liệu demo.
Chưa có đăng ký, phân quyền, JWT hoặc xóa thiết bị.
Không có tích hợp cloud hay backup.

## Python và dependency

Workspace đã có `.venv` dùng **Python 3.14.2**. Bộ dependency trong
`requirements-lock.txt` đã được cài với interpreter này. Dùng Flask 3.1,
SQLAlchemy 2.0, psycopg 3, Flask-Migrate/Alembic, Flask-Login, Flask-WTF, Jinja2,
python-dotenv và pytest; không cần Java/Maven.

```bash
cd /path/to/equipmentdesk
# Chỉ chạy lệnh tạo venv nếu chưa có .venv:
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

`requirements.txt` chứa dependency chạy ứng dụng với giới hạn phiên bản;
`requirements-dev.txt` bổ sung pytest. `requirements-lock.txt` khóa cả dependency
trực tiếp và gián tiếp đã dùng để kiểm tra (bao gồm pytest).
Khi chủ động cập nhật dependency, cài `requirements-dev.txt`, chạy lại tests rồi
cập nhật lock bằng `python -m pip freeze > requirements-lock.txt`.

## PostgreSQL local

Nếu đã có PostgreSQL, sử dụng bản hiện có. Máy được kiểm tra có Homebrew PostgreSQL
16.10, nhưng không có phản hồi tại `localhost:5432` lúc kiểm tra.
Với máy chưa cài PostgreSQL:

```bash
brew install postgresql@16
brew services start postgresql@16
```

Thêm binary vào PATH cho Terminal hiện tại (hoạt động với cả Homebrew Intel/Apple Silicon):

```bash
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
pg_isready -h localhost -p 5432
```

Chỉ tạo role/database dưới đây khi chúng **chưa tồn tại**. Với database đã có dữ liệu,
chọn một database mới dành riêng cho project; không chạy migration vào database đó.
Lệnh `-P` hỏi password tương tác để không ghi password thật vào tài liệu:

```bash
createuser -h localhost -U "$USER" -P equipmentdesk
createdb -h localhost -U "$USER" --owner=equipmentdesk equipmentdesk
```

Homebrew thường dùng user macOS làm superuser của cụm mới; nếu PostgreSQL của bạn
có admin khác, thay `-U "$USER"` bằng tên admin đó. Không cần quyền superuser cho
role ứng dụng. Các lệnh trên là hướng dẫn, scaffold không tự thực thi chúng.

## Cấu hình .env

```bash
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
```

Sửa `.env`: thay `SECRET_KEY=CHANGE_ME` bằng chuỗi vừa tạo và thay password trong
`DATABASE_URL` bằng password role PostgreSQL. Nếu password chứa `@`, `:`, `/`, `#`
hoặc ký tự đặc biệt, cần percent-encode phần password trong URL.

| Biến | Giá trị / ý nghĩa |
| --- | --- |
| `DATABASE_URL` | Bắt buộc: `postgresql+psycopg://equipmentdesk:...@localhost:5432/equipmentdesk` |
| `SECRET_KEY` | Bắt buộc: chuỗi ngẫu nhiên ít nhất 32 ký tự, không commit |
| `APP_STORAGE_ROOT` | Mặc định `./data`, đường dẫn tương đối được tính từ thư mục project |
| `PORT` | Mặc định `8080`, số nguyên từ 1 đến 65535 |
| `DEMO_USERNAME` | Chỉ dùng cho lệnh seed/tạo user demo; 1–80 ký tự sau khi bỏ khoảng trắng ở hai đầu |
| `DEMO_PASSWORD` | Chỉ dùng cho lệnh seed/tạo user demo; user mới cần 8–128 ký tự, không chỉ có khoảng trắng |

Application factory dùng `python-dotenv` để nạp **đúng file `.env` ở root project**
với `override=False`; biến môi trường đã được export luôn được ưu tiên.
Không cần `source .env`. `.env` và `data/` đã được bỏ qua trong Git.
Có thể đặt `APP_STORAGE_ROOT=/srv/cloudrescue-data` khi môi trường có quyền ghi.
File đính kèm được lưu dưới `APP_STORAGE_ROOT/uploads/`; thư mục được tạo khi upload
đầu tiên. `APP_STORAGE_ROOT` phải là thư mục riêng do ứng dụng sở hữu hoặc người chạy
ứng dụng cấp quyền ghi.

## Chạy migration

Kích hoạt `.venv`, cấu hình `.env`, kiểm tra URL trỏ đúng database mới rồi chạy:

```bash
python -m flask --app equipmentdesk:create_app db upgrade
python -m flask --app equipmentdesk:create_app db current
python -m flask --app equipmentdesk:create_app db check
```

Revision đầu tiên là `0001_initial_schema`. Alembic tạo 5 bảng nghiệp vụ và bảng
`alembic_version`. Không dùng `create_all`; khởi động web không tự migrate.
Muốn xem SQL mà không kết nối database:

```bash
python -m flask --app equipmentdesk:create_app db upgrade --sql
```

Khi thay đổi model ở bước sau, sinh migration mới, đọc kỹ file trước khi áp dụng:

```bash
python -m flask --app equipmentdesk:create_app db migrate -m "describe change"
python -m flask --app equipmentdesk:create_app db upgrade
```

`db check` so sánh model với schema, nhưng Alembic không tự nhận diện mọi thay đổi
CHECK constraint hoặc trigger; các thay đổi này cần migration viết tay.
`db downgrade base` xóa các bảng của project nên chỉ dùng trên database thử có thể bỏ.

## Chạy ứng dụng

```bash
python run.py
```

Mở [EquipmentDesk local](http://127.0.0.1:8080). `run.py` đọc `PORT` trong cấu hình,
bind `127.0.0.1` và mặc định tắt debug. Nếu dùng trực tiếp `flask run`, cần truyền
`--port 8080` hoặc `FLASK_RUN_PORT`, vì Flask CLI không tự đọc biến `PORT` tùy chỉnh.
Trang `/` chuyển đến danh sách thiết bị; nếu chưa đăng nhập, chuyển đến `/login`.
Tạo user demo theo hướng dẫn bên dưới trước khi đăng nhập.

Trong **PyCharm**:

1. Mở thư mục project, chọn interpreter `<project>/.venv/bin/python`.
2. Cài dependency trong Terminal của PyCharm theo hướng dẫn trên.
3. Tạo `.env`, chạy migration và `seed-demo-data` từ Terminal (hoặc
   `create-demo-user` nếu chỉ muốn tạo user, không cần dữ liệu mẫu).
4. Tạo Python Run Configuration: script `run.py`, working directory là root project,
   interpreter là `.venv`.
5. Run rồi mở URL local. Có thể đặt biến trong Run Configuration; chúng được ưu tiên
   hơn `.env`. Không cần plugin Flask hay plugin dotenv riêng.

## Cấu trúc

```text
equipmentdesk/
  __init__.py          # create_app, đăng ký extension và blueprint
  config.py            # dotenv, kiểm tra cấu hình và đường dẫn
  extensions.py        # SQLAlchemy, Migrate, LoginManager, CSRF
  blueprints/main/     # chuyển trang chính đến danh sách thiết bị
  blueprints/auth/     # login/logout bằng session
  blueprints/equipment/# web danh sách/tìm kiếm/chi tiết/thêm/sửa
  blueprints/api/      # API thiết bị, phiếu mượn/trả và endpoint CSRF
  blueprints/loans/    # web danh sách, chi tiết, tạo và trả phiếu
  blueprints/health/   # health live/ready công khai
  cli.py              # create-demo-user và seed-demo-data
  http.py             # bảo vệ truy cập, lỗi HTML/JSON
  models/              # 5 model, quan hệ, trạng thái, hash password
  services/            # auth, equipment, loans, attachments, seed
  storage/local.py     # file UUID, đọc/ghi an toàn dưới APP_STORAGE_ROOT/uploads
  forms/               # Flask-WTF login, equipment và loans
  templates/           # Jinja2 login, danh sách, chi tiết, form và trang lỗi
  static/css/          # CSS local
migrations/
  env.py               # migration online/offline dùng config của app
  versions/            # migration schema, không phụ thuộc model tại runtime
  alembic.ini
  script.py.mako
tests/                 # pytest độc lập DB và integration PostgreSQL
docs/development.md    # quyết định, tiến độ và điểm cần tiếp tục
run.py                 # entry point cho Terminal/PyCharm
```

## Database và quy ước

- `users` → nhiều `loans`; mỗi `loans` thuộc một user, có nhiều `loan_items` và `attachments`.
- Mỗi `equipment` là một thiết bị vật lý. Không có cột `quantity` hay tồn kho.
  Một thiết bị xuất hiện trong nhiều phiếu theo lịch sử; cặp `(loan_id, equipment_id)` duy nhất.
- Equipment: `AVAILABLE`, `BORROWED`, `MAINTENANCE`. Loan: `BORROWED`, `RETURNED`.
  Quá hạn là đang `BORROWED` và ngày hẹn trả nhỏ hơn ngày đang xét, không lưu trạng thái `OVERDUE`.
- Ngày mượn/trả là PostgreSQL `DATE`. Ngày hẹn trả và ngày thực trả không trước ngày mượn.
  `BORROWED` phải có ngày thực trả NULL; `RETURNED` phải có ngày thực trả.
- Timestamp dùng `TIMESTAMPTZ`, database tự gán `created_at`; trigger cập nhật `updated_at`
  trên equipment/loans, kể cả khi sửa trực tiếp bằng SQL.
- PK dạng BIGINT tự tăng, riêng attachment dùng UUID v4 do Python sinh khi INSERT qua ORM.
  Khi INSERT attachment bằng SQL, bên gọi phải truyền UUID.
- Các FK đều NOT NULL và `ON DELETE RESTRICT` để giữ lịch sử, không tự xóa dây chuyền.
  Có index trên FK; unique ghép của loan_items đã hỗ trợ truy vấn theo loan_id.
- Attachment lưu đường dẫn tương đối duy nhất, tên gốc, MIME type, size không âm và SHA-256
  64 ký tự hex chữ thường. CHECK chặn đường dẫn tuyệt đối và thành phần `.`/`..`.
- User lưu password hash bằng Werkzeug; không tạo tài khoản demo hoặc seed tự động.
  Username/code phân biệt hoa thường. Chưa có email/role theo schema của bước Python này.

## Tạo user demo và đăng nhập

Điền `DEMO_USERNAME` và `DEMO_PASSWORD` trong `.env` (hoặc export vào môi trường),
chạy migration rồi gọi:

```bash
python -m flask --app equipmentdesk:create_app create-demo-user
```

Lệnh chủ động tạo user, hash mật khẩu bằng Werkzeug (scrypt), đặt full_name bằng
username. Không in password/hash ra Terminal. Nếu username đã tồn tại, lệnh thông báo
và giữ nguyên user/password, kể cả khi `DEMO_PASSWORD` đã đổi. Hai lệnh chạy đồng thời
cũng được bảo vệ bởi unique constraint. Không có user nào được tạo khi khởi động app.

Mở `/login`, đăng nhập bằng thông tin vừa cấu hình. Login dùng form POST và CSRF.
Đăng xuất là **POST `/logout`** với CSRF, qua nút ở thanh điều hướng. Khi đăng nhập
thành công, session cũ được xóa trước khi thiết lập session đăng nhập; đăng xuất xóa
session. Không sử dụng remember-me. Cookie session được ký bằng SECRET_KEY,
HttpOnly và SameSite=Lax; cấu hình local dùng HTTP trên 127.0.0.1.

## Seed dữ liệu demo

Seed là lệnh tường minh; app không chạy seed hoặc thay dữ liệu khi khởi động. Sau
`db upgrade`, đặt `DEMO_USERNAME` và `DEMO_PASSWORD` trong `.env` rồi chạy:

```bash
python -m flask --app equipmentdesk:create_app seed-demo-data
```

Trên database trống, lệnh tạo user demo, 20 thiết bị vật lý, 10 phiếu (5 đang mượn,
5 đã trả) và 5 biên bản PDF/PNG/JPEG hợp lệ. User được tạo bằng cùng quy tắc hash
mật khẩu của `create-demo-user`; không in password. Các thiết bị đang được mượn khớp
với phiếu BORROWED; thiết bị của phiếu RETURNED ở trạng thái AVAILABLE. File được lưu
qua dịch vụ upload hiện tại trong `APP_STORAGE_ROOT/uploads`, gồm kiểm tra định dạng,
UUID, SHA-256 và metadata.

Lệnh chạy lại không nhân bản mã `DEMO-EQ-*`, `DEMO-LOAN-*` hay các file mẫu, không
đổi tên/mật khẩu user có sẵn, và không cập nhật bản ghi đã có. Nếu mã thiết bị mẫu
đã được dùng với trạng thái không khớp nghiệp vụ, phiếu liên quan được bỏ qua để giữ
nguyên bản ghi đó. Tài khoản đăng nhập là `DEMO_USERNAME` và mật khẩu `DEMO_PASSWORD`
đã dùng khi user được tạo lần đầu; đổi biến môi trường về sau không đổi mật khẩu user.

## Health check

Hai endpoint công khai, không cần cookie đăng nhập:

| URL | Ý nghĩa |
| --- | --- |
| `GET /health/live` | Trả HTTP 200 nếu Flask nhận request; không truy vấn database hoặc storage. Hai trường phụ thuộc trả `not_checked`. |
| `GET /health/ready` | Chạy `SELECT 1` và kiểm tra đọc/ghi thư mục `APP_STORAGE_ROOT/uploads`; trả 200 nếu cả hai đạt, nếu không trả 503. |

Response JSON có các trường `status`, `database`, `storage` (giá trị `ok`, `error`,
`not_checked` hoặc `not_ready`). Lỗi chỉ tiết lộ trạng thái, không trả thông tin kết nối,
đường dẫn riêng tư hay stack trace. Readiness tạo file probe ngẫu nhiên trong thư mục
uploads hiện có, đọc lại và dọn ngay; không tạo `APP_STORAGE_ROOT` hoặc `uploads` nếu
đang thiếu. Lệnh seed hoặc upload đầu tiên tạo thư mục. Nếu chưa seed/upload, có thể
tạo thư mục cho cấu hình local mặc định trước khi đòi readiness xanh:

```bash
mkdir -p data/uploads
curl -i http://127.0.0.1:8080/health/live
curl -i http://127.0.0.1:8080/health/ready
```

## Quản lý thiết bị

Trang `/equipment` tìm kiếm không phân biệt hoa/thường theo mã, tên, loại hoặc vị trí;
20 kết quả mỗi trang. Ký tự `%` và `_` trong từ khóa được tìm đúng như ký tự thường.
Mở thiết bị để xem chi tiết, dùng nút thêm/sửa để cập nhật.

Web và API đều gọi `services/equipment.py`; quy tắc dữ liệu giống nhau:

- `code`, `name`, `category` bắt buộc, bỏ khoảng trắng đầu/cuối, tối đa 80/200/100 ký tự.
- `location` tối đa 200, `description` tối đa 10000 ký tự; có thể null hoặc trống.
- Mã thiết bị duy nhất, phân biệt hoa thường. Mã trùng trả lỗi rõ ràng theo trường code.
- Chỉ thao tác trực tiếp giữa `AVAILABLE` và `MAINTENANCE`.
- Không được tạo thiết bị `BORROWED`, chuyển thiết bị sang `BORROWED` hoặc chuyển
  thiết bị đang `BORROWED` sang trạng thái khác. Thiết bị đang mượn vẫn sửa được thông
  tin mô tả, giữ nguyên trạng thái. Service khóa row khi cập nhật và đọc lại trạng thái
  trước khi kiểm tra để tránh dùng trạng thái cũ.
- API từ chối trường ngoài danh sách (ví dụ id, quantity, created_at).
  JSON tối đa 128 KiB; multipart tối đa 10 MiB/file cộng 128 KiB cho multipart.
  Dữ liệu không hợp lệ không được lưu một phần.

Bước này không thay đổi schema; dùng migration `0001_initial_schema` hiện có.

## API bằng cookie session và CSRF

Danh sách endpoint và ví dụ request nối tiếp có trong [docs/api.md](docs/api.md).

| Phương thức | URL | Kết quả |
| --- | --- | --- |
| GET | `/api/csrf-token` | Token CSRF gắn với cookie session; dùng cả trước login |
| GET | `/api/equipment?q=...&page=1` | `{items, page, per_page, total, pages}` |
| POST | `/api/equipment` | Tạo thiết bị, HTTP 201 và header Location |
| GET | `/api/equipment/<id>` | Chi tiết thiết bị, HTTP 200 |
| PUT | `/api/equipment/<id>` | Sửa thiết bị, HTTP 200 |

Các route equipment chấp nhận cả URL có/không có dấu `/` cuối. Các thao tác thiết bị
đều yêu cầu session đăng nhập. Endpoint CSRF là ngoại lệ công khai để client có thể
bắt đầu đăng nhập; không trả dữ liệu thiết bị hay thông tin user. Không bật CORS.

POST/PUT API yêu cầu `Content-Type: application/json` và header `X-CSRFToken`.
PUT yêu cầu đủ code/name/category như POST; description/location bỏ qua sẽ được xóa
về null, status bỏ qua sẽ giữ nguyên trạng thái hiện tại. POST bỏ status mặc định
AVAILABLE. Timestamp và id là trường chỉ đọc.

Ví dụ trên Terminal macOS với `curl`; thay `YOUR_DEMO_PASSWORD` bằng mật khẩu đã đặt.
Dùng cùng hostname `127.0.0.1` trong toàn bộ các bước:

```bash
# 1. Lấy token trước login, đồng thời lưu cookie session.
EQUIPMENTDESK_COOKIES="$(mktemp)"
EQUIPMENTDESK_CSRF="$(curl -fsS -c "$EQUIPMENTDESK_COOKIES" \
  http://127.0.0.1:8080/api/csrf-token \
  | python -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')"

# 2. Login là form POST, không phải JSON; thành công trả HTTP 303.
# Thay username nếu DEMO_USERNAME của bạn không phải demo.
curl -i -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  --data-urlencode 'username=demo' \
  --data-urlencode 'password=YOUR_DEMO_PASSWORD' \
  --data-urlencode "csrf_token=$EQUIPMENTDESK_CSRF" \
  http://127.0.0.1:8080/login

# 3. Login tạo session mới: lấy token mới trước khi ghi dữ liệu.
EQUIPMENTDESK_CSRF="$(curl -fsS -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  http://127.0.0.1:8080/api/csrf-token \
  | python -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')"

# 4. GET chỉ cần session.
curl -sS -b "$EQUIPMENTDESK_COOKIES" \
  'http://127.0.0.1:8080/api/equipment?q=laptop&page=1'

# 5. POST tạo thiết bị; xem id trong JSON hoặc Location của response.
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"code":"LT-DEMO-001","name":"Laptop demo","category":"Máy tính","status":"AVAILABLE","location":"Phòng 201"}' \
  http://127.0.0.1:8080/api/equipment

# 6. Thay 1 bằng id vừa được trả về. Chạy POST cùng mã lần nữa sẽ trả 409.
curl -i -X PUT -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"code":"LT-DEMO-001","name":"Laptop demo","category":"Máy tính","status":"MAINTENANCE","location":"Phòng kỹ thuật"}' \
  http://127.0.0.1:8080/api/equipment/1

# 7. Đăng xuất và xóa cookie jar tạm của ví dụ.
curl -i -b "$EQUIPMENTDESK_COOKIES" -c "$EQUIPMENTDESK_COOKIES" \
  --data-urlencode "csrf_token=$EQUIPMENTDESK_CSRF" http://127.0.0.1:8080/logout
rm "$EQUIPMENTDESK_COOKIES"
```

Trên trang web đã đăng nhập, cũng có thể lấy token bằng
`document.querySelector('meta[name="csrf-token"]').content` và gọi `fetch` cùng origin
với `credentials: 'same-origin'`, header `X-CSRFToken` và `Content-Type: application/json`.
Token mặc định hết hạn sau 60 phút; lấy token mới nếu nhận `csrf_error`.
Token lấy từ client/session khác không dùng được cho cookie của bạn.

API trả lỗi JSON nhất quán, ví dụ mã trùng:

```json
{
  "error": {
    "code": "duplicate_code",
    "message": "Mã thiết bị đã tồn tại.",
    "fields": {"code": ["Mã thiết bị đã tồn tại. Vui lòng chọn mã khác."]}
  }
}
```

| HTTP | Ý nghĩa |
| --- | --- |
| 401 | Chưa đăng nhập (kể cả POST/PUT chưa gửi CSRF); web sẽ chuyển về login |
| 400 | CSRF thiếu/sai/hết hạn, JSON sai cú pháp hoặc page không hợp lệ |
| 404 | Không tìm thấy thiết bị |
| 409 | Mã trùng, thiết bị không sẵn sàng, trạng thái không khớp hoặc phiếu đã trả |
| 413 | Request quá lớn |
| 415 | API không nhận được Content-Type JSON |
| 422 | Validation: trường bắt buộc, độ dài, kiểu, trạng thái, hoặc trường lạ |
| 503 | Database chưa sẵn sàng hoặc chưa migrate |

## Phiếu mượn và trả thiết bị

Chọn **Phiếu mượn** ở thanh điều hướng (`/loans`), rồi **Tạo phiếu mượn** (`/loans/new`).
Form hiển thị các thiết bị AVAILABLE; tích chọn nhiều thiết bị và ghi tình trạng trước
khi mượn cho từng thiết bị đã chọn. Người tạo lấy từ session đang đăng nhập, không có
ô chọn user. Thiết bị có thể vừa được người khác mượn sau khi mở form; service sẽ kiểm
tra lại trạng thái dưới khóa PostgreSQL khi gửi form.

Mở chi tiết `/loans/<id>` để xem các thiết bị và tình trạng trước/sau. Khi còn BORROWED,
form **Trả toàn bộ phiếu** yêu cầu ngày trả và tình trạng sau khi trả của từng thiết bị.
Mọi user đã đăng nhập có thể xem/trả phiếu demo, kể cả phiếu do user khác tạo; người tạo
ban đầu của phiếu được giữ nguyên. Chưa có trả từng phần, sửa hoặc xóa phiếu.

Quy tắc dùng chung cho web/API:

- Từ 1 đến 100 thiết bị, không lặp ID. Mỗi thiết bị phải tồn tại và đang AVAILABLE.
- Ngày mượn/ngày hẹn trả bắt buộc, định dạng `YYYY-MM-DD`; ngày hẹn trả >= ngày mượn.
  Form mặc định ngày local hôm nay; API phải truyền ngày rõ ràng. Chưa cấm nhập ngày
  tương lai hoặc ghi nhận lịch sử, miễn thỏa thứ tự ngày.
- `condition_before` và `condition_after` lúc trả: chuỗi không trống, tối đa 2000 ký tự.
  `note` tùy chọn, tối đa 10000 ký tự. Các chuỗi được trim.
- `loan_code` do server tạo dạng `PM-YYYYMMDD-<uuid hex>`; không nhận loan_code, status
  hoặc user_id từ body API. Web cũng không dùng user_id gửi từ client.
- Tạo phiếu BORROWED thành công chuyển **tất cả** thiết bị sang BORROWED trong một commit.
- Trả phiếu yêu cầu đúng, đủ và không lặp thiết bị thuộc phiếu; ngày trả >= ngày mượn.
  Lưu actual_return_date, condition_after, đổi phiếu thành RETURNED và thiết bị AVAILABLE
  trong cùng transaction. Thiết bị có thể được mượn lại bằng phiếu mới sau đó.
- Trả lần thứ hai bị từ chối 409, không ghi đè tình trạng sau trả và không làm thay đổi
  thiết bị đã được mượn lại trong phiếu khác.
- `is_overdue = status == BORROWED AND expected_return_date < ngày local hôm nay`.
  Đến hạn hôm nay chưa quá hạn; phiếu RETURNED không còn hiện badge Quá hạn. Database
  vẫn chỉ lưu BORROWED/RETURNED, không lưu trạng thái OVERDUE.

### API phiếu mượn

Dùng cookie session và `X-CSRFToken` như phần API thiết bị. Các URL chấp nhận dấu `/`
cuối. `<id>` là ID phiếu, không phải ID thiết bị:

| Phương thức | URL | Kết quả |
| --- | --- | --- |
| GET | `/api/loans?page=1` | Danh sách 20 phiếu/trang, mới nhất trước |
| GET | `/api/loans/<id>` | Chi tiết và danh sách items |
| POST | `/api/loans` | Tạo phiếu, HTTP 201, header Location trỏ đến chi tiết |
| POST | `/api/loans/<id>/return` | Trả toàn bộ phiếu, HTTP 200 |

List có dạng `{items, page, per_page, total, pages}`; mỗi phiếu có `item_count`,
`is_overdue`, thông tin user và ngày, không nhúng chi tiết thiết bị trong list.
Detail/create/return còn có `items` gồm id của loan_item, equipment_id, code, name,
condition_before và condition_after. `user_id`, `status`, `loan_code` là dữ liệu trả
về do server xác định, không phải trường client được gửi.

Ví dụ body tạo phiếu (thay ID 1, 2 bằng hai thiết bị AVAILABLE có thật):

```json
{
  "loan_date": "2026-09-24",
  "expected_return_date": "2026-10-01",
  "note": "Mượn phục vụ buổi học",
  "items": [
    {"equipment_id": 1, "condition_before": "Hoạt động tốt, đủ bộ sạc"},
    {"equipment_id": 2, "condition_before": "Màn hình tốt, vỏ có vết xước nhỏ"}
  ]
}
```

Sau khi lấy session/CSRF ở bước 1–3 của ví dụ phía trên, có thể gọi:

```bash
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"loan_date":"2026-09-24","expected_return_date":"2026-10-01","items":[{"equipment_id":1,"condition_before":"Hoạt động tốt"},{"equipment_id":2,"condition_before":"Đủ phụ kiện"}]}' \
  http://127.0.0.1:8080/api/loans

curl -sS -b "$EQUIPMENTDESK_COOKIES" http://127.0.0.1:8080/api/loans

# Thay 1 trong URL bằng ID phiếu trả về từ POST, giữ đủ ID thiết bị thuộc phiếu.
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -d '{"actual_return_date":"2026-09-25","items":[{"equipment_id":1,"condition_after":"Hoạt động tốt, đủ bộ sạc"},{"equipment_id":2,"condition_after":"Tình trạng như khi mượn"}]}' \
  http://127.0.0.1:8080/api/loans/1/return
```

## Biên bản đính kèm

Trang chi tiết phiếu (`/loans/<id>`) hiển thị file đã đính kèm và form tải file mới
lên. Chọn PDF/PNG/JPEG thật, dung lượng từ 1 byte đến **10 MiB**. Phần mở rộng và
`Content-Type` gửi từ client không quyết định loại file: ứng dụng kiểm tra cấu trúc
PDF bằng pypdf và đọc/kiểm tra ảnh PNG/JPEG bằng Pillow. File phải có ít nhất một
trang nếu là PDF. Tên file vật lý do server sinh bằng UUID; file nằm ngoài `static/`
trong `APP_STORAGE_ROOT/uploads/`, quyền thư mục/file lần lượt 700/600 trên macOS.

Database chỉ lưu metadata: attachment UUID, loan ID, đường dẫn tương đối như
`uploads/UUID.pdf`, tên gốc đã lấy basename, MIME type được xác minh, size thực tế,
SHA-256 của byte đã nhận và thời gian tạo. Không lưu file trong PostgreSQL hoặc lưu
absolute path. Không đổi schema/migration hiện có.

API upload dùng session cookie và CSRF của phiên đăng nhập. `curl -F` tự tạo boundary
`multipart/form-data`; không tự đặt header Content-Type:

```bash
curl -i -b "$EQUIPMENTDESK_COOKIES" \
  -H "X-CSRFToken: $EQUIPMENTDESK_CSRF" \
  -F 'file=@/absolute/path/to/bien-ban.pdf' \
  http://127.0.0.1:8080/api/loans/1/attachments

# Xem metadata rồi lấy attachment UUID từ kết quả POST.
curl -sS -b "$EQUIPMENTDESK_COOKIES" http://127.0.0.1:8080/api/attachments/<UUID>
curl -f -b "$EQUIPMENTDESK_COOKIES" \
  http://127.0.0.1:8080/api/attachments/<UUID>/download \
  -o bien-ban-tai-ve.pdf
```

Metadata của một file ở `GET /api/attachments/<UUID>`; file được tải bằng
`GET /api/attachments/<UUID>/download`. Download luôn là attachment, dùng tên an toàn
theo basename và phần mở rộng khớp nội dung đã nhận. Stream được đọc lại từ file, kiểm
tra size và SHA-256 trước khi gửi. Nếu metadata còn mà file đã mất, API trả 404 với
`error.code=file_missing`; nếu file/metadata bị thay đổi, trả 409 `file_integrity_error`.
Tên đường dẫn vật lý chỉ được chấp nhận khi có đúng mẫu `uploads/<UUID>.<pdf|png|jpg>`
và UUID trùng attachment ID. Kiểm tra thêm root bằng file descriptor, từ chối symlink,
absolute path và `..`; file không được phục vụ trực public từ static.

Upload ghi file trước commit metadata để có thể tính hash. Nếu insert/commit database
thất bại, transaction rollback và file mới ghi được xóa. Nếu ứng dụng không có quyền
ghi APP_STORAGE_ROOT, API báo lỗi lưu trữ 503. Request JSON vẫn giới hạn 128 KiB;
request tổng giới hạn 10 MiB cộng 128 KiB overhead multipart.

Các lỗi vẫn theo `{error: {code, message, fields}}`: 422 nếu dữ liệu/thiết bị lặp/ngày
không hợp lệ; 404 nếu không có phiếu/thiết bị; 409 nếu thiết bị không sẵn sàng,
`already_returned` nếu trả lặp hoặc `equipment_state_conflict` nếu dữ liệu trạng thái
không khớp. Chưa đăng nhập trả JSON 401; thiếu/sai CSRF sau đăng nhập trả JSON 400.

### Transaction và khóa hàng

`services/loans.py` dùng transaction của SQLAlchemy scoped session trong request
(kể cả transaction đọc đã bắt đầu khi Flask-Login tải user). Chỉ commit một lần sau
khi hoàn thành; mọi exception rollback. Chạy PostgreSQL với mức cô lập mặc định
READ COMMITTED. Không dùng SQLite hoặc khóa Python để thay thế khóa database.

- Tạo phiếu: khóa `equipment` bằng `SELECT ... FOR UPDATE`, từng ID theo thứ tự tăng
  dần, refresh dữ liệu trong identity map rồi kiểm tra AVAILABLE. Chỉ sau khi đủ thiết
  bị hợp lệ mới ghi loan, loan_items và đổi trạng thái.
- Trả phiếu: khóa row `loans` trước để tuần tự hóa hai lần trả; kiểm tra chưa RETURNED,
  đối chiếu items, rồi khóa tất cả equipment theo ID tăng dần trước khi ghi.
- Request cạnh tranh chờ khóa. Sau commit của request trước, request tiếp theo đọc
  lại trạng thái đã thay đổi rồi bị từ chối nếu thiết bị không còn AVAILABLE/phiếu đã trả.
  Nếu request trước rollback, khóa được nhả và request chờ có thể tiếp tục.
- Quy tắc bảo vệ áp dụng qua service. SQL thủ công có thể phá invariant liên bảng;
  luồng trả sẽ báo conflict nếu trạng thái thiết bị không khớp, không tự sửa dữ liệu đó.

Không đổi schema trong bước này; migration hiện có tiếp tục được dùng.

## Kiểm tra

```bash
python -m compileall -q equipmentdesk migrations tests run.py
python -m pip check
python -m pytest -q
```

Không có `TEST_DATABASE_URL`, tests PostgreSQL được **skip rõ ràng**; các test còn lại
không cần PostgreSQL đang chạy. Để kiểm tra migration và ràng buộc trên PostgreSQL thật,
tạo database thử riêng (tên bắt buộc `equipmentdesk_test`):

```bash
createdb -h localhost -U "$USER" --owner=equipmentdesk equipmentdesk_test
export TEST_DATABASE_URL='postgresql+psycopg://equipmentdesk:YOUR_URL_ENCODED_PASSWORD@localhost:5432/equipmentdesk_test'
python -m pytest -q
```

Tests tạo schema ngẫu nhiên riêng trong database thử, chạy upgrade → downgrade →
upgrade, kiểm tra schema/model và ràng buộc rồi xóa **schema thử do chính tests tạo**.
Không dùng `DATABASE_URL` cho tests, không sửa bảng đã có trong database ứng dụng.
Không cần `.env` để chạy tests. Kết quả lần kiểm tra thực tế nằm ở `docs/development.md`.

Chạy riêng luồng phiếu hoặc test cạnh tranh khi đã đặt TEST_DATABASE_URL:

```bash
python -m pytest tests/test_loans.py -q
python -m pytest tests/test_loans.py -q -k 'concurrent or rollback_releases'
```

Tests locking dùng các HTTP request trên Flask test client riêng, session SQLAlchemy
và connection PostgreSQL riêng. Test chủ động giữ transaction đầu sau khi đã khóa row,
dùng `pg_blocking_pids` để xác nhận transaction thứ hai đang chờ thật, rồi nhả khóa.
Có test hai request mượn với thứ tự ID đảo ngược, request lỗi rollback để request chờ
mượn thành công, và hai request trả chỉ một lần được ghi. Test chèn exception **sau
flush SQL** xác nhận rollback cả loan, loan_items và trạng thái thiết bị. Timeout
statement/lock chỉ đặt cho connection test để lỗi locking không treo bộ test.

Tài liệu dependency: [Flask](https://flask.palletsprojects.com/),
[Flask-Migrate](https://flask-migrate.readthedocs.io/),
[SQLAlchemy](https://docs.sqlalchemy.org/en/20/),
[Psycopg và Python được hỗ trợ](https://www.psycopg.org/).
