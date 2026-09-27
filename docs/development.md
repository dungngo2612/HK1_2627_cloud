# Nhật ký phát triển EquipmentDesk

Hiện tại đang triển khai OpenStack VM; tiến độ và điểm chặn SSH ở cuối tài liệu.
Các phần dưới ghi lịch sử; quyết định mới nhất được ưu tiên khi có thay đổi phạm vi.

## Bước 1 — Khung project và database — 2026-09-24

Yêu cầu hiện hành chuyển sang **Python/Flask**, thay thế đề xuất Java/Spring Boot
trước đó. Bước này chỉ dựng khung, cấu hình, database và kiểm tra. Dừng sau bước này.
Không triển khai OpenStack, AWS, S3, backup hoặc điều phối.

Kiểm tra trước khi chỉnh sửa: workspace chỉ có `.idea/` và `.venv/`, không có code
ứng dụng, không có Git repository hay file hướng dẫn AGENTS.md áp dụng được tìm thấy.
Giữ nguyên cấu hình `.idea/`, dùng lại `.venv` và cài dependency project vào đó.
Python hệ thống và venv là 3.14.2. Máy có Homebrew PostgreSQL 16.10; server không
phản hồi tại localhost:5432 khi kiểm tra.
Không đọc/sửa dữ liệu trong cụm PostgreSQL sẵn có.

## Các phần đã tạo

- Application factory `create_app`, main Blueprint và trang Jinja2/CSS giới thiệu.
- Tách `models`, `services`, `forms`, `templates`, `static`, `tests`.
  Services/forms mới là package dành cho bước tiếp theo, chưa có workflow.
- Extension SQLAlchemy, Flask-Migrate, Flask-Login và CSRFProtect khởi tạo trong factory.
  User loader đọc user theo id; helper hash/check password dùng Werkzeug.
  Chưa có route đăng nhập/đăng xuất hoặc tài khoản demo.
- `.env.example`, `.gitignore`, dependency chạy/dev và lock phiên bản thực tế.
- Migration `0001_initial_schema` tạo 5 bảng, index, PK/FK/unique/CHECK và trigger timestamp.
  `downgrade()` tháo trigger/function và xóa bảng theo thứ tự FK.
- README hướng dẫn macOS, PostgreSQL, dotenv, migration, Terminal, PyCharm và pytest.

## Quyết định cần giữ nhất quán

1. **Config:** DATABASE_URL và SECRET_KEY bắt buộc. Không có password/secret mặc định.
   `.env` được python-dotenv nạp từ root project, không ghi đè biến môi trường.
   Chỉ hỗ trợ PostgreSQL qua psycopg 3, chuẩn hóa `postgresql://` sang `postgresql+psycopg://`.
2. **Storage:** APP_STORAGE_ROOT mặc định `./data`, resolve theo root project để không
   phụ thuộc working directory. Chỉ cấu hình, chưa tạo thư mục/ghi file. Có thể đổi
   thành `/srv/cloudrescue-data` mà không sửa code; quyền filesystem do người chạy cấp.
3. **Local server:** `run.py` bind 127.0.0.1, PORT mặc định 8080, debug tắt.
   App factory không kết nối DB, không tự migrate hay seed. Trang `/` không xác nhận DB sẵn sàng.
4. **Schema:** users không có email/role; loan_items không có quantity; attachments
   không có stored_name. Dùng đúng danh sách cột của yêu cầu Python mới nhất.
5. **Thiết bị:** một row là một thiết bị vật lý; code duy nhất. Status lưu VARCHAR
   với CHECK: AVAILABLE/BORROWED/MAINTENANCE. Không dùng PostgreSQL ENUM để tránh
   phức tạp khi đổi danh sách trạng thái về sau.
6. **Phiếu mượn:** BORROWED/RETURNED; quá hạn tính bằng status BORROWED và
   expected_return_date < ngày xét. Đến hạn hôm nay chưa quá hạn. `is_overdue_on(date)`
   hỗ trợ ngày xác định; `is_overdue` dùng ngày local của máy chạy. Dùng DATE cho ngày nghiệp vụ.
7. **Ngày trả:** expected_return_date >= loan_date; actual_return_date nếu có phải
   >= loan_date. RETURNED bắt buộc có actual_return_date; BORROWED bắt buộc NULL.
8. **Lịch sử:** FK bắt buộc và ON DELETE RESTRICT; quan hệ ORM dùng passive_deletes
   để không tự null hóa/xóa lịch sử. Unique (loan_id, equipment_id) ngăn thiết bị trùng
   trong một phiếu, vẫn cho phép xuất hiện trong nhiều phiếu theo thời gian.
9. **Attachment:** UUID v4 do Python sinh lúc ORM insert; SQL thủ công phải truyền UUID.
   relative_path duy nhất, tương đối, chặn thành phần `.`/`..`, backslash và dấu `:`.
   size >= 0, sha256 là 64 ký tự hex thường. MIME/name không rỗng, loan_id bắt buộc.
   Chưa có đọc/ghi file hay tính hash file thật; metadata chỉ sẵn sàng cho bước sau.
10. **Timestamp:** TIMESTAMPTZ, server default CURRENT_TIMESTAMP; trigger tự cập nhật
    updated_at cho equipment/loans ngay cả với SQL trực tiếp. PostgreSQL CURRENT_TIMESTAMP
    là thời điểm bắt đầu transaction, không phải đồng hồ thay đổi từng câu lệnh.
11. **Khóa/text:** BIGINT tự tăng cho 4 bảng; username/code/loan_code phân biệt hoa thường.
    full_name/name/category/condition_before bắt buộc và không chỉ chứa dấu cách;
    description/location/note/condition_after nullable.
12. **Migration:** không dùng create_all. Migration độc lập với model runtime.
    Alembic autogenerate không bao quát CHECK và trigger; phải review/viết tay khi thay đổi.

## Kiểm tra và môi trường

- Cài dependency thành công vào `.venv` trên Python 3.14.2; phiên bản cụ thể trong
  `requirements-lock.txt`.
- `python -m compileall -q equipmentdesk migrations tests run.py`: đạt.
- `python -m pip check`: đạt, không có xung đột dependency.
- `python -m pytest -q` không có TEST_DATABASE_URL: **12 passed, 23 skipped**.
  Skip chỉ áp dụng cho các test cần PostgreSQL.
- Kiểm tra PostgreSQL đầy đủ với TEST_DATABASE_URL trên cụm tạm tách biệt:
  **35 passed trong 1.23 giây**, không skip. Đã chạy upgrade → downgrade → upgrade,
  so sánh schema/model (gồm server defaults), quan hệ, UUID, unique, CHECK, FK,
  ngày trả, lịch sử thiết bị và trigger updated_at qua SQL trực tiếp.
- Flask CLI `db upgrade --sql`: đạt, sinh SQL của đủ 5 bảng và timestamp trigger
  mà không cần kết nối database.
- Cụm thử chỉ nghe Unix socket riêng, không dùng cổng TCP, không thay đổi cấu hình hoặc
  dữ liệu PostgreSQL đã có. Sandbox ban đầu chặn shared memory/socket; chạy cụm thử và
  kết nối kiểm tra đã dùng quyền mở rộng cho đúng đường dẫn cụm tạm.
- Đã dừng cụm PostgreSQL thử sau khi kiểm tra. Không tạo `.env` chứa secret thật,
  không tạo/migrate database ứng dụng `equipmentdesk` và không để web server chạy nền.
  Người dùng cần tạo database local mới, điền `.env`, chạy `db upgrade` rồi `python run.py`
  theo README. Không còn kiểm tra nào bị chặn do thiếu PostgreSQL trong lần bàn giao này.

## Bước 2 — Đăng nhập và quản lý thiết bị — 2026-09-24

Đã đọc code và nhật ký bước 1 trước khi sửa. Giữ nguyên model và migration hiện có;
không thêm bảng, không áp dụng migration vào database ứng dụng sẵn có.
Không thêm dependency, tiếp tục Python 3.14.2 và bộ phiên bản trong requirements-lock.txt.

### Phần đã hoàn thành

- Blueprint auth: GET/POST `/login`, POST `/logout`, session Flask-Login, hash mật khẩu
  Werkzeug scrypt. Không có đăng ký/JWT/role; mọi user đăng nhập đều vận hành dữ liệu demo.
- CLI `flask --app equipmentdesk:create_app create-demo-user` đọc DEMO_USERNAME và
  DEMO_PASSWORD từ môi trường (bao gồm `.env` do factory nạp). User mới có full_name
  bằng username. Username 1–80 ký tự; mật khẩu mới 8–128 ký tự, không toàn khoảng trắng.
  Chạy lại không sửa thông tin/mật khẩu user hiện có; unique constraint xử lý cả chạy
  đồng thời. Không tạo tài khoản hoặc thay mật khẩu lúc khởi động ứng dụng.
- Web tiếng Việt: danh sách, tìm kiếm, phân trang, chi tiết, thêm và sửa thiết bị.
  Trang `/` chuyển đến danh sách. Trang login thay thế điểm vào công khai trước đây.
- API GET/POST `/api/equipment`, GET/PUT `/api/equipment/<id>`, chấp nhận dấu slash cuối.
  `<id>` là khóa số nguyên của thiết bị (diễn giải URL chi tiết trong yêu cầu).
- `services/equipment.py` dùng chung cho web và API, giữ toàn bộ validation, tìm kiếm,
  khóa row khi sửa, commit/rollback và thông báo mã trùng. Controller không tự ghi DB.
- Flask-WTF forms, template base/navigation/logout, CSRF meta tag, thông báo lỗi theo
  trường và trang lỗi tiếng Việt. Jinja tự escape các giá trị user nhập.
- README có hướng dẫn tạo user, chạy PyCharm, dùng curl lấy cookie session + CSRF,
  login, lấy lại token sau login, GET/POST/PUT và logout.

### Quyết định cho bước tiếp theo

1. Auth gate đăng ký **trước CSRFProtect**: API thiết bị chưa đăng nhập luôn trả JSON
   401, kể cả POST/PUT chưa có CSRF. Web chưa đăng nhập chuyển `/login`.
   Ngoại lệ công khai: login, static, GET `/api/csrf-token`. Không có CSRF exemption
   cho login/logout/web mutation/API mutation. Không bật CORS.
2. Login nhận form; gửi JSON vào login bị từ chối 415. Thông báo sai username/password
   dùng cùng một nội dung, không tiết lộ username tồn tại. Username không tồn tại vẫn
   thực hiện hash check giả. Password không lưu vào session hoặc in ra log.
3. Đăng nhập thành công xóa session trước khi login_user; không dùng remember-me.
   Luôn chuyển về danh sách, bỏ qua tham số next để không có redirect ra ngoài.
   Logout chỉ POST, xóa session. Client phải lấy token CSRF mới sau login/logout;
   token mặc định có hạn 60 phút. Response động đặt Cache-Control: no-store.
4. `current_user` được đưa vào context dưới dạng proxy để chỉ tải khi template cần.
   Trang lỗi DB không hiển thị navigation cần user; tránh truy vấn lại user trong lúc
   DB mất kết nối. API lỗi trả `{error: {code, message, fields}}`.
5. Service yêu cầu code/name/category trên cả POST và PUT; trim các trường text.
   Giới hạn theo schema, riêng description 10000 ký tự và mỗi request tối đa 128 KiB.
   Unknown fields và kiểu dữ liệu sai bị từ chối. PUT thiếu description/location xóa
   chúng về NULL; thiếu status giữ trạng thái hiện tại. POST thiếu status dùng AVAILABLE.
6. Chỉ được đổi trực tiếp AVAILABLE ↔ MAINTENANCE. Tạo/chuyển sang BORROWED bị từ
   chối 422; chuyển từ BORROWED sang trạng thái khác bị từ chối 409. Có thể sửa metadata
   của thiết bị BORROWED nếu giữ nguyên hoặc không gửi status. Web không hiển thị ô
   chọn status cho thiết bị đang mượn; service vẫn kiểm tra request giả mạo.
7. Update SELECT FOR UPDATE và populate_existing để đọc lại trạng thái từ DB ngay
   trong transaction; mọi lỗi rollback. Unique code được xử lý từ constraint DB nên
   không phụ thuộc kiểm tra trước khi INSERT có thể bị race.
8. Tìm kiếm không phân biệt hoa/thường theo code/name/category/location; không bỏ dấu
   tiếng Việt. Escape wildcard `%`/`_`, tối đa 200 ký tự. Phân trang 20 dòng, ID giảm dần,
   page phải là số nguyên 1–1000000. ID vượt giới hạn BIGINT được trả 404 trước khi query.
9. HTTP: 400 CSRF/JSON syntax/page, 401 chưa login, 404 không tồn tại, 409 conflict,
   413 quá kích thước, 415 sai content type, 422 validation, 503 database chưa sẵn sàng.
   Mã trùng hoặc request lỗi không được ghi dữ liệu một phần.

### Kiểm tra thực tế

- Compile Python: đạt; `pip check`: không có xung đột dependency.
- Bộ test ban đầu: 86 passed trên PostgreSQL 16.10 tạm.
- Bổ sung test login sai content type và mất kết nối khi tải session; test bắt được
  lỗi template tải user lần nữa khi DB lỗi. Đã sửa bằng context proxy và kiểm tra lại.
- Unit tests sau sửa: **25 passed**.
- Lần chạy toàn bộ cuối trên PostgreSQL 16.10 tạm: **89 passed trong 10.64 giây**, không
  skip hoặc lỗi. Bao gồm các test regression của bước 1 và test mới của bước 2.
- Tests integration gồm migration/schema cũ, đăng nhập đúng/sai, logout, token CSRF
  thiếu/sai phiên/hết hạn, token đổi sau login, web/API create/update/search/detail,
  pagination, escape HTML, validation, mã trùng/rollback, trạng thái BORROWED,
  CLI idempotent và thiếu biến môi trường.
- Mỗi lần kiểm tra dùng cụm PostgreSQL tạm riêng và schema ngẫu nhiên; cụm tự dừng
  trong finally, kể cả khi test lỗi. Không sửa database ứng dụng hoặc user sẵn có.
  Đã xác nhận cụm thử cuối dừng sau khi test hoàn tất.
- Chưa chạy thử thủ công trên trình duyệt; các route HTML/JSON/session/cookie được
  kiểm tra qua Flask test client với PostgreSQL thật. Không để web server chạy nền.

## Bước 3 — Phiếu mượn/trả — 2026-09-24

Đã đọc code và toàn bộ nhật ký trước khi sửa. Dùng lại năm bảng và revision
`0001_initial_schema`; không thay đổi schema hoặc database ứng dụng đang có.

### Đã triển khai

- Web tiếng Việt: `/loans` danh sách 20 phiếu/trang; `/loans/<id>` chi tiết, tình
  trạng trước/sau từng thiết bị, trạng thái và quá hạn; `/loans/new` form chọn nhiều
  thiết bị AVAILABLE; POST `/loans/<id>/return` trả toàn bộ phiếu.
- API: GET/POST `/api/loans`, GET `/api/loans/<id>`, POST
  `/api/loans/<id>/return`; các URL nhận dấu `/` cuối. ID trong URL là ID phiếu.
  POST trả 201/Location khi tạo và 200 khi trả. JSON lỗi giữ cấu trúc bước 2.
- Blueprint web/API đều gọi `services/loans.py`, sử dụng Flask-Login session lấy
  `current_user.id` làm người tạo. API từ chối `user_id`/`status`/`loan_code` từ
  client; form web bỏ qua `user_id` giả mạo. Không có phân quyền khác trong demo.
- Một phiếu gồm 1–100 thiết bị vật lý, không lặp ID, mỗi thiết bị có
  `condition_before`; khi trả phải gửi đúng đủ các ID và `condition_after` từng cái.
  Ngày ISO `YYYY-MM-DD`; ngày hẹn trả và ngày trả không trước ngày mượn.
  Ghi chú tùy chọn. Loan code server tạo `PM-YYYYMMDD-<uuid hex>`.
- Tạo phiếu chỉ mượn AVAILABLE, chuyển tất cả sang BORROWED cùng một commit.
  Trả lưu actual_return_date/condition_after, chuyển phiếu RETURNED và tất cả thiết bị
  AVAILABLE cùng một commit; từ chối trả lần hai với 409.
- Quá hạn được tính từ BORROWED và expected_return_date < ngày local hiện tại;
  không lưu trạng thái OVERDUE. Phiếu RETURNED không hiện quá hạn.
- Các form thay đổi dữ liệu và API POST tiếp tục dùng CSRF/session của bước 2.
  README đã có cấu trúc request/response, ví dụ curl và quy tắc transaction.

### Transaction và khóa

1. `create_loan` dùng scoped SQLAlchemy session hiện tại của request, kể cả transaction
   đọc user đã được Flask-Login mở. Mỗi equipment được `SELECT ... FOR UPDATE` theo ID
   **tăng dần**, `populate_existing=True` để không dùng trạng thái cũ trong identity map.
   Chỉ ghi loan/items/status sau khi tất cả đều tồn tại và AVAILABLE. Commit duy nhất
   cuối hàm; mọi exception rollback cả dữ liệu và nhả khóa.
2. `return_loan` khóa row loan đầu tiên, từ chối nếu đã RETURNED, kiểm tra chính xác
   items/ngày trả rồi khóa thiết bị theo ID tăng dần. Xác nhận thiết bị vẫn BORROWED
   trước khi cập nhật. Hai request trả cùng phiếu được tuần tự hóa ở row loan.
3. Test cạnh tranh dùng hai HTTP client/session/connection PostgreSQL riêng. Hook
   giữ request đầu sau khi `FOR UPDATE` đã lấy khóa; `pg_blocking_pids` xác nhận
   request thứ hai bị PostgreSQL chặn, rồi giải phóng. Có test thiết bị gửi theo
   thứ tự ngược nhau, rollback của request đầu để request chờ tiếp tục, và hai request
   trả chỉ một lần được ghi. Không dùng SQLite hoặc khóa Python để thay khóa DB.
4. Test chèn lỗi sau flush SQL để chứng minh rollback loan, loan_items và trạng thái
   equipment; sau rollback request khác lấy khóa và hoàn tất. Với trạng thái bất nhất
   do SQL ngoài service, trả phiếu báo 409 thay vì tự ý đổi dữ liệu.

### Kiểm tra thực tế

- `python -m compileall -q equipmentdesk tests`: đạt.
- `python -m pip check`: đạt, không có xung đột dependency.
- `python -m pytest -q` khi không đặt TEST_DATABASE_URL: **32 passed, 106 skipped**;
  skip chỉ gồm test cần PostgreSQL.
- Toàn bộ tests trên **PostgreSQL 16.10 tạm riêng**: **138 passed trong 50.20 giây**,
  không skip, lỗi hoặc xfail. Bao gồm regression của bước 1–2 và test mới cho
  mượn/trả, validation, user session, CSRF, rollback sau SQL flush, khóa thứ tự ID,
  chờ khóa thật và hai request trả đồng thời.
- Cụm thử chỉ nghe Unix socket riêng trong `/private/tmp`, tạo database
  `equipmentdesk_test` riêng, mỗi module dùng schema ngẫu nhiên. Đã dừng cụm thử
  sau khi test. Không chạy migration hoặc ghi vào database ứng dụng của người dùng.
- Chưa mở trình duyệt thủ công; route HTML/API và session được kiểm tra qua Flask
  test client nối tới PostgreSQL thật. Không để web server chạy nền.

## Việc cho giai đoạn sau

Chỉ làm khi có yêu cầu tiếp tục:

- Nếu thêm trả từng phần, phân quyền hoặc sửa phiếu, thiết kế thêm transaction và
  các invariant tương ứng trước khi mở thao tác ghi mới.
- Quyết định timezone nghiệp vụ rõ ràng nếu chạy ngoài múi giờ local.

Dừng sau bước 3 theo yêu cầu.

## Bước 4 — Upload/download biên bản — 2026-09-24

Đã đọc code và các bước trong nhật ký trước khi sửa. Dùng bảng `attachments`, quan hệ
`Loan.attachments` và CHECK constraint của `0001_initial_schema`; không thêm migration,
không ghi nội dung hoặc absolute path vào database.

### Phần đã triển khai

- API POST `/api/loans/<loan_id>/attachments` (dấu slash cuối được chấp nhận), GET
  `/api/attachments/<uuid>` metadata và GET `/api/attachments/<uuid>/download`.
  Upload dùng `multipart/form-data`, tên field `file`, session đăng nhập + CSRF.
- Trang chi tiết `/loans/<id>` có form tải lên, danh sách metadata và link download.
  Biên bản gắn với một phiếu có thật; loan id sai trả 404 trước khi tạo file.
- Nội dung PDF được parse bằng pypdf ở strict mode, phải có trang và trailer EOF.
  PNG/JPEG được mở, verify và decode đầy đủ bằng Pillow. Content-Type client bị bỏ qua.
  Hỏng/giả định dạng trả 422. File rỗng trả 422; dung lượng thực tế trên 10 MiB trả 413.
- SHA-256 và size tính từ byte stream đã đọc, không tin header size của client.
  content_type metadata được suy ra từ định dạng thực tế; file vật lý dùng UUID server
  với phần mở rộng `.pdf`, `.png` hoặc `.jpg` theo nội dung, không theo filename.
- `original_name` lưu basename đã lọc separator/control chars; download dùng
  `secure_filename` và ép phần mở rộng khớp loại file thực tế. Content-Disposition là
  attachment, mọi response có `X-Content-Type-Options: nosniff`.
- `LocalStorage` ghi dưới `APP_STORAGE_ROOT/uploads` bằng `dir_fd`, O_EXCL, O_NOFOLLOW,
  mode 700/600. Read/delete chỉ nhận `uploads/<UUID attachment ID>.<allowed extension>`;
  mở directory/file bằng descriptor và chặn symlink, traversal/absolute path.
- Download xác thực ID, relative_path, file tồn tại, size và SHA-256 trước khi trả byte.
  Metadata còn/file mất trả 404 `file_missing`; path sai trả 409; nội dung bị đổi trả
  409 `file_integrity_error`. Permission/storage lỗi trả thông báo 503.
- File được ghi/fync trước khi commit metadata. Mọi lỗi database rollback session và
  xóa file vừa tạo; test lỗi sau flush INSERT xác nhận schema không còn row hoặc file.
- Thêm Pillow/pypdf vào requirements và lock để parse/verify ảnh/PDF thật trên Python
  3.14; không dùng magic bytes đơn lẻ.

### Kiểm tra thực tế

- `python -m compileall -q equipmentdesk migrations tests run.py`: đạt.
- `python -m pip check`: đạt sau khi cài Pillow/pypdf; không có dependency xung đột.
- Không có TEST_DATABASE_URL: lần chạy cuối **32 passed, 124 skipped**; skip chỉ là
  tests yêu cầu PostgreSQL.
- Trên PostgreSQL 16.10 thử riêng, **156 passed trong 32.40 giây**, không skip,
  lỗi hoặc xfail. Bao gồm test upload/download đúng byte và SHA-256, PDF/PNG/JPEG,
  từ chối file rỗng/sai định dạng/quá 10 MiB, CSRF/đăng nhập, file mất, path traversal,
  symlink, dữ liệu file bị đổi và dọn file khi INSERT metadata lỗi.
- Tests storage dùng APP_STORAGE_ROOT trong `tmp_path`, không ghi `./data` hoặc database
  của người dùng. Test concurrent/transaction trước đó tiếp tục dùng PostgreSQL test.
- PostgreSQL test chạy trong cụm 16.10 riêng, chỉ Unix socket dưới `/private/tmp`, dùng
  database `equipmentdesk_test`; đã dừng cụm sau khi test. Không chạy migration hay ghi
  vào database ứng dụng. Không mở web server nền.

Dừng sau bước 4 theo yêu cầu.

## Bước 5 — Seed và health check — 2026-09-24

Đã đọc code và nhật ký trước khi sửa. Không đổi schema/migration, không tự chạy migration,
seed hoặc tạo storage khi app khởi động.

### Đã triển khai

- Thêm lệnh riêng `flask --app equipmentdesk:create_app seed-demo-data`, dùng
  `DEMO_USERNAME`/`DEMO_PASSWORD`. Lệnh dùng `create_demo_user` để hash mật khẩu và giữ
  nguyên user đã có; không tự chạy khi khởi động web.
- Seed bản ghi bằng mã ổn định: 20 thiết bị, 10 phiếu (5 BORROWED, 5 RETURNED), có
  loan_items nhất quán với trạng thái equipment. Trạng thái/mô tả/ghi chú của bản ghi
  đã có không bị cập nhật. Nếu dữ liệu đã có xung đột trạng thái, bỏ qua loan đó.
- Tạo 5 PDF/PNG/JPEG hợp lệ qua `services/attachments.create_attachment`, dùng chung
  kiểm tra nội dung, UUID, storage, SHA-256 và metadata. Kiểm tra theo attachment ID/
  tên seed giúp chạy lần hai không sinh thêm file mẫu.
- GET `/health/live` công khai luôn trả 200 và không gọi DB/storage.
- GET `/health/ready` kiểm tra `SELECT 1` và đọc/ghi file probe độc nhất trong
  `APP_STORAGE_ROOT/uploads`, đọc lại rồi dọn; không tạo root/uploads còn thiếu.
  JSON chỉ có trạng thái tổng thể, database và storage, không có exception/secret.
- README bổ sung lệnh migration/seed, account credentials theo env, quy tắc rerun và
  ví dụ health check.

### Kiểm tra thực tế

- Compileall: đạt; `pip check`: đạt, không xung đột dependency.
- Không có `TEST_DATABASE_URL`: **36 passed, 126 skipped**; PostgreSQL test được skip.
- Toàn bộ test trên PostgreSQL 16.10 tạm riêng: **162 passed trong 41.48 giây**, không
  skip/fail. Seed test chạy lệnh hai lần, xác nhận số lượng ổn định, sửa thử dữ liệu
  user/equipment/loan rồi xác nhận seed giữ nguyên các sửa đổi; mở PDF/ảnh mẫu và so
  size/SHA-256 metadata với byte tải từ storage. Health test kiểm tra 200 khi sẵn sàng,
  DB lỗi, storage lỗi và thư mục uploads bị thiếu.
- Cụm test chỉ nghe Unix socket riêng tại `/private/tmp`, database `equipmentdesk_test`;
  đã dừng sau test. Không kết nối/migrate database ứng dụng. Không để web server nền.

Dừng sau bước 5 theo yêu cầu.

## Bước 6 — Rà soát sẵn sàng chạy local — 2026-09-24

### Rà soát và hoàn thiện

- Thêm `tests/test_workflow.py` kiểm thử xuyên suốt giao diện bằng PostgreSQL thật:
  login → xem thiết bị → tạo phiếu → upload PDF → download đúng byte/checksum → trả;
  xác nhận loan RETURNED, tình trạng sau trả và equipment AVAILABLE.
- Bổ sung hướng dẫn API riêng ở `docs/api.md`, gồm cookie session, xoay CSRF sau login,
  endpoint, ví dụ thiết bị/mượn/upload/download/trả, health và logout.
- Cập nhật `.env.example` để chỉ rõ seed/user tạo tường minh; `.gitignore` loại `.env`,
  `.venv`, `data/`, `uploads/` runtime. Dò lại source/docs không thấy credential thật
  hoặc đường dẫn home cá nhân; chỉ còn placeholder/thông tin giả dành riêng cho tests.
- Không đổi schema/migration, không tạo `.env`, không chạy seed vào database local.

### Kiểm tra thực tế

- `python -m compileall -q equipmentdesk migrations tests run.py`: đạt.
- `python -m pip check`: đạt, không broken requirements.
- Không có TEST_DATABASE_URL: **36 passed, 127 skipped**. Skip là PostgreSQL test;
  app/unit/health tests không cần database vẫn chạy.
- Toàn bộ suite trong PostgreSQL 16.10 cluster mới riêng: **163 passed trong 32.20 giây**,
  không skip/fail. Fixture chạy migration upgrade → downgrade → upgrade trên schema mới;
  có test transaction/locking, seed hai lần không nhân đôi và giữ sửa đổi của user,
  checksum file mẫu, CSRF/session, health dependency failures, và luồng giao diện end-to-end.
- Cluster kiểm thử và database `equipmentdesk_test` được tạo tạm trong `/private/tmp`;
  PostgreSQL đã được stop tự động sau test. Không truy cập database app
  `equipmentdesk`, không xóa dữ liệu hiện có, không để app server chạy nền.
- Kiểm tra giao diện chức năng bằng Flask test client với database PostgreSQL và file
  thật; chưa thực hiện kiểm tra hiển thị thủ công trong trình duyệt/PyCharm.

Dừng sau bước 6 theo yêu cầu.

## Triển khai OpenStack VM — 2026-09-25 (đang chờ kết nối SSH)

- Đã kiểm tra OpenStack từ controller: `equipmentdesk-vm` đang ACTIVE trên compute;
  địa chỉ private `10.20.30.173`, floating `10.10.10.176`. Volume `cloudrescue-data`
  5 GB đang `in-use`, gắn vào VM ở `/dev/vdb`. Chưa thể xác nhận mount/PGDATA từ trong VM.
- Đường SSH Mac → controller tại localhost:2222 hoạt động. Controller → floating IP
  trực tiếp báo `No route to host`; controller → private IP timeout. Phiên SSH hiện
  có trên controller đi qua user `vboxuser` của compute, nhưng không bật SSH
  ControlMaster; phiên mới tới compute yêu cầu mật khẩu. Không đọc, in hoặc xin
  mật khẩu/private key qua chat.
- Đã yêu cầu tunnel SSH nội bộ trên controller, local port 2230, để tiếp tục thao tác
  VM sau khi người dùng xác thực compute trong terminal của họ. Chưa có tunnel khi
  ghi dòng này.
- Đã tạo `requirements-deploy.txt` để cài Gunicorn trên Ubuntu cùng dependencies
  ứng dụng. Đã đóng gói source không chứa `.venv`, `.env`, `.idea`, data/uploads;
  SHA-256 `84eea771794a4fa3c163a98cd493163764702d51e86b27e41d75080f53265ed0`.
  Archive tạm ở home user controller: `~/equipmentdesk-release-20260925.tar.gz`,
  mode 0600. Chưa chuyển archive lên VM, chưa cài PostgreSQL/app, chưa migration/seed.
- Giữ nguyên PostgreSQL, volume và dữ liệu VM; chưa thay đổi mạng controller/compute
  hoặc mở security group.

### Lượt kiểm chứng 2026-09-25

- Yêu cầu kiểm chứng app trước/sau reboot. Đã kiểm tra lại controller: tunnel
  localhost:2230 vẫn chưa mở; phiên SSH hiện có qua compute vẫn không có
  ControlMaster, và phiên mới tới `vboxuser@10.10.10.72` từ chối public key.
- Đã truy vấn thêm OpenStack để lập `docs/source-inventory.md`: VM/flavor/network,
  floating IP, security group và volume ID đều có giá trị xác minh. Filesystem UUID,
  mount thực tế, PGDATA, uploads, service và dữ liệu ứng dụng vẫn cần SSH vào guest.
- Chưa tạo phiếu kiểm chứng hoặc reboot VM; phải có mốc dữ liệu/file trước reboot
  mới đáp ứng phép so sánh sau reboot và tránh báo kết quả giả.

## Triển khai và kiểm chứng trên equipmentdesk-vm — 2026-09-25

- Sau khi xác thực SSH qua compute, đã kiểm tra guest Ubuntu 24.04.5, Python 3.12.3,
  volume ext4 `/dev/vdb` UUID `44afe0d1-db81-4914-ba5f-04949a02bded` mount tại
  `/srv/cloudrescue-data` theo fstab, còn khoảng 4.6 GB. `postgres/`, `uploads/`,
  `backups/` ban đầu rỗng và thuộc root; VM chưa có PostgreSQL/app. Không sửa
  controller/compute network hoặc security group.
- Đã chuyển source không kèm `.venv` macOS lên `/opt/equipmentdesk`; tạo venv Ubuntu
  Python 3.12.3, cài `requirements-deploy.txt` với Gunicorn 25.3.0. VM không phân giải
  DNS kho Ubuntu/PyPI; dùng proxy HTTP tạm chỉ nghe loopback controller qua SSH
  reverse tunnel để cài `python3.12-venv`, PostgreSQL 16 và Python dependencies.
- Tắt auto-create cluster mặc định trước khi cài PostgreSQL server. Tạo cluster
  `16/equipmentdesk` trực tiếp tại `/srv/cloudrescue-data/postgres/equipmentdesk`;
  `SHOW data_directory` xác nhận. Service PostgreSQL có `RequiresMountsFor` và
  `ConditionPathIsMountPoint` cho volume. App user `equipmentdesk` sở hữu
  `/srv/cloudrescue-data/uploads`; secret ở `/etc/equipmentdesk/equipmentdesk.env`
  (root:equipmentdesk, 0640), demo credential ở
  `/etc/equipmentdesk/demo-credentials` (root, 0600). Không chép secret vào repo.
- Migration `0001_initial_schema (head)` chạy thành công. Seed lần đầu tạo 1 user,
  20 thiết bị, 10 phiếu, 5 attachment; lần hai tạo 0. PostgreSQL đếm `20,10,5`.
  Gunicorn bind `127.0.0.1:8080`, systemd `equipmentdesk.service` enabled và yêu cầu
  PostgreSQL + mount Cinder. Tắt Gunicorn control socket không dùng để hết lỗi
  quyền `.gunicorn` trong source root-owned. `/health/live` và `/health/ready` đều 200.
- Qua HTTP thật trước reboot: login demo bằng session/CSRF, GET equipment, tạo phiếu
  ID 11, upload PDF 472 byte, download so byte bằng nhau và SHA-256
  `2701ffcfb1dfaa50e0122af7fd069e5357ba25d65bc8e7517ada9d608fb41b19`,
  trả phiếu. PostgreSQL ghi `RETURNED|AVAILABLE`; file vật lý ở
  `/srv/cloudrescue-data/uploads/c615fb35969945428b27b98a4c2a5031.pdf` có cùng hash.
- Đã lưu mốc trước reboot ở `/root/equipmentdesk-pre-reboot.txt`, reboot **chỉ** VM.
  Boot ID sau reboot khác trước; console cho thấy volume mount theo UUID rồi
  PostgreSQL/Gunicorn tự khởi động. VM boot chậm khoảng vài phút, không cần sửa cấu
  hình. Sau reboot: cả hai service enabled/active; live/ready 200; phiếu 11 vẫn
  RETURNED, thiết bị AVAILABLE, file tải lại trùng byte gốc và file vật lý; seed
  vẫn `20,10,5`. Log và ảnh bằng chứng ở `docs/evidence/`, inventory ở
  `docs/source-inventory.md`.
- Kiểm tra qua Chrome headless trên Mac bằng SSH tunnel: giao diện thiết bị và chi
  tiết phiếu hiển thị dữ liệu thật; click nút tải PDF trong trình duyệt, file tải
  có cùng SHA-256. Không mở port 8080 ra floating IP; URL Mac chỉ là localhost qua
  tunnel. Không triển khai OpenStack backup/AWS/S3/điều phối.
