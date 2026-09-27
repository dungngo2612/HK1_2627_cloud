# EquipmentDesk — source inventory OpenStack

Ghi nhận ngày 2026-09-25. ID hạ tầng được truy vấn từ controller bằng OpenStack
CLI; hệ điều hành, mount, dịch vụ và đường dẫn dữ liệu được kiểm tra bằng SSH
trong VM. Không chứa credential hoặc private key.

| Mục | Giá trị | Nguồn / trạng thái |
| --- | --- | --- |
| VM | `equipmentdesk-vm` | OpenStack: `ACTIVE` |
| VM ID | `54d9dd9d-5294-47ef-b782-166b9bfd59f5` | OpenStack |
| Image | `equipmentdesk-ubuntu-24.04` (`20f68491-da97-4261-9614-4e9250eede76`) | OpenStack; guest Ubuntu 24.04.5 LTS |
| Hypervisor | `compute` | OpenStack |
| Flavor | `ds2G`, 2 vCPU, RAM 2048 MiB, root disk 10 GB | OpenStack |
| Network | `equipmentdesk-net` (`746b9d91-9e20-4f5c-9fb5-2c98bc53cfb8`) | OpenStack |
| Subnet | `equipmentdesk-subnet`, `10.20.30.0/24`, gateway `10.20.30.1` | OpenStack |
| Private IP | `10.20.30.173` | OpenStack |
| Floating IP | `10.10.10.176`, ID `2e303a39-29b6-44dd-a841-861e700bb505` | OpenStack: `ACTIVE` |
| Security group | `equipmentdesk-sg` (`8bbab239-9d0b-4cfd-8fbb-9c9a9503c044`) | OpenStack |
| Cinder volume | `cloudrescue-data`, ID `46f1a895-2fa8-4522-b4d2-ea296c7267d2`, 5 GB, `in-use` | OpenStack: gắn VM ở `/dev/vdb` |
| Filesystem UUID | `44afe0d1-db81-4914-ba5f-04949a02bded` | `findmnt` trong VM, `/dev/vdb`, ext4 |
| Mount point | `/srv/cloudrescue-data` | `findmnt` trong VM; fstab dùng UUID trên |
| PGDATA thực tế | `/srv/cloudrescue-data/postgres/equipmentdesk` | PostgreSQL 16 `SHOW data_directory`; cluster `16/equipmentdesk` |
| Uploads thực tế | `/srv/cloudrescue-data/uploads` | `APP_STORAGE_ROOT` của service, file upload thật và SHA-256 đã xác nhận |

## Truy cập

Controller có thể truy cập từ máy làm việc qua SSH localhost port 2222. Từ
controller, SSH tới VM dùng jump qua `vboxuser@10.10.10.72`, rồi đăng nhập
`ubuntu@10.10.10.176` bằng keypair `equipmentdesk-key` lưu trên controller.
Nhập xác thực tương tác tại terminal khi SSH yêu cầu. Lệnh trên controller:

```bash
ssh -J vboxuser@10.10.10.72 -i ~/.ssh/equipmentdesk-key ubuntu@10.10.10.176
```

Ứng dụng Gunicorn nghe `127.0.0.1:8080` trong VM; không mở port 8080 ra mạng.
Tạo tunnel trên controller:

```bash
ssh -J vboxuser@10.10.10.72 -i ~/.ssh/equipmentdesk-key \
  -L 127.0.0.1:8080:127.0.0.1:8080 ubuntu@10.10.10.176
# Mở http://127.0.0.1:8080 trên controller.
```

Để mở bằng trình duyệt macOS, giữ tunnel trên controller và chạy thêm trên Mac:

```bash
ssh -p 2222 -L 127.0.0.1:8080:127.0.0.1:8080 dungngo@127.0.0.1
# Mở http://127.0.0.1:8080 trên Mac.
```

Credential demo được tạo riêng trên VM tại `/etc/equipmentdesk/demo-credentials`
(mode 0600); username là `demo`. Người quản trị VM có thể đọc qua `sudo`, không
chép mật khẩu vào repo hoặc tài liệu. Cấu hình app ở
`/etc/equipmentdesk/equipmentdesk.env` (mode 0640, root:equipmentdesk).

## Bằng chứng kiểm chứng

- Migration: `flask db current` trả `0001_initial_schema (head)`; source ở
  `migrations/versions/0001_initial_schema.py`. Seed ở
  `equipmentdesk/services/seed.py` và `equipmentdesk/cli.py`: lần đầu tạo 20 thiết
  bị, 10 phiếu, 5 file; lần hai tạo 0. Truy vấn PostgreSQL sau reboot vẫn đếm
  `20,10,5` cho dữ liệu mẫu.
- Luồng thật qua Gunicorn: đăng nhập demo bằng session/CSRF, xem thiết bị, tạo phiếu
  ID 11, upload PDF, tải đúng byte rồi trả. Sau reboot, API trả phiếu `RETURNED`,
  PostgreSQL ghi `RETURNED|AVAILABLE`; attachment và file vật lý trên Cinder đều có
  SHA-256 `2701ffcfb1dfaa50e0122af7fd069e5357ba25d65bc8e7517ada9d608fb41b19`.
  PDF tải qua Chrome cũng có cùng checksum và mở được.
- `systemd` tự khởi động PostgreSQL rồi EquipmentDesk sau reboot; cả hai `enabled`
  và `active`. `/health/live` và `/health/ready` đều 200 trước và sau reboot.
  [Log reboot và service](evidence/reboot-and-services.txt) có boot ID khác, thời
  điểm khởi động PostgreSQL/Gunicorn, mount UUID và PGDATA. Mốc
  [trước reboot](evidence/pre-reboot.txt) cũng còn tại
  `/root/equipmentdesk-pre-reboot.txt` trên VM.
- [Kết quả đối chiếu trước/sau reboot](evidence/validation.json) ghi ID phiếu,
  attachment, checksum và trạng thái mà không chứa credential.
- [Ảnh danh sách thiết bị](evidence/equipment-list.png),
  [ảnh form tạo phiếu](evidence/create-loan-form.png),
  [ảnh chi tiết phiếu, form upload và nút tải file](evidence/loan-detail-full.png),
  [ảnh Chrome Download History](evidence/browser-download.png) và
  [PDF tải bằng Chrome](evidence/bien-ban-kiem-chung.pdf).

Không ghi database password, SECRET_KEY, demo password hoặc private key vào tài liệu.
URL ứng dụng qua SSH tunnel đã kiểm tra trên Mac tại `http://127.0.0.1:18082`
(ready 200); URL này chỉ tồn tại khi hai tunnel đang mở. Hai lệnh phía trên dùng
port 8080 để người vận hành tự mở lại. Không có URL public trực tiếp qua floating IP
vì Gunicorn chỉ bind loopback và không thêm ingress 8080.
