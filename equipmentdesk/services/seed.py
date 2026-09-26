from datetime import date, timedelta
from io import BytesIO

import sqlalchemy as sa
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from werkzeug.datastructures import FileStorage

from equipmentdesk.extensions import db
from equipmentdesk.models import Attachment, Equipment, Loan, LoanItem, LoanStatus, User
from equipmentdesk.services.attachments import create_attachment
from equipmentdesk.services.auth import create_demo_user

_EQUIPMENT = [
    (f"DEMO-EQ-{number:03}", name, category, location)
    for number, (name, category, location) in enumerate([
        ("Laptop Dell Latitude", "Máy tính", "Phòng thiết bị A"),
        ("Laptop Lenovo ThinkPad", "Máy tính", "Phòng thiết bị A"),
        ("Máy chiếu Epson", "Trình chiếu", "Tủ thiết bị tầng 2"),
        ("Máy ảnh Canon EOS", "Máy ảnh", "Phòng truyền thông"),
        ("Micro không dây Shure", "Âm thanh", "Phòng thiết bị B"),
        ("Loa di động JBL", "Âm thanh", "Phòng thiết bị B"),
        ("Máy tính bảng iPad", "Máy tính bảng", "Phòng thiết bị A"),
        ("Webcam Logitech", "Thiết bị ngoại vi", "Phòng họp 1"),
        ("Bộ phát Wi-Fi TP-Link", "Mạng", "Kho tầng 1"),
        ("Màn hình Dell 24 inch", "Màn hình", "Phòng thiết bị A"),
        ("Bàn phím cơ Keychron", "Thiết bị ngoại vi", "Phòng thiết bị A"),
        ("Chuột Logitech MX", "Thiết bị ngoại vi", "Phòng thiết bị A"),
        ("Máy quét Epson", "Máy văn phòng", "Văn phòng"),
        ("Máy in Brother", "Máy văn phòng", "Văn phòng"),
        ("Tripod Manfrotto", "Máy ảnh", "Phòng truyền thông"),
        ("Đèn LED quay phim", "Ánh sáng", "Phòng truyền thông"),
        ("Máy ghi âm Zoom", "Âm thanh", "Phòng truyền thông"),
        ("Bộ chuyển đổi USB-C", "Thiết bị ngoại vi", "Tủ thiết bị tầng 2"),
        ("Ổ cứng di động 1 TB", "Lưu trữ", "Phòng thiết bị A"),
        ("Bộ sạc đa cổng", "Phụ kiện", "Phòng thiết bị A"),
    ], start=1)
]

_ATTACHMENT_SAMPLES = (
    (1, "bien-ban-demo-01.pdf", "application/pdf"),
    (2, "bien-ban-demo-02.png", "image/png"),
    (3, "bien-ban-demo-03.jpg", "image/jpeg"),
    (4, "bien-ban-demo-04.pdf", "application/pdf"),
    (5, "bien-ban-demo-05.png", "image/png"),
)


def _sample_bytes(number, content_type):
    if content_type == "application/pdf":
        writer = PdfWriter()
        writer.add_blank_page(width=420, height=300)
        writer.add_metadata({"/Title": f"EquipmentDesk - Biên bản mẫu {number}"})
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    image = Image.new("RGB", (640, 400), (232, 241, 250))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 616, 376), radius=18, outline=(31, 78, 121), width=4)
    draw.text((52, 58), "EQUIPMENTDESK", fill=(31, 78, 121))
    draw.text((52, 105), f"Bien ban thiet bi mau {number}", fill=(33, 43, 54))
    output = BytesIO()
    image.save(output, format="PNG" if content_type == "image/png" else "JPEG")
    return output.getvalue()


def _create_demo_records(user):
    equipment_by_code = {
        row.code: row for row in db.session.scalars(sa.select(Equipment)).all()
    }
    equipment_created = 0
    created_equipment_codes = set()
    for number, (code, name, category, location) in enumerate(_EQUIPMENT, start=1):
        if code in equipment_by_code:
            continue
        # Equipment 1–5 belong to active loans; historical-loan devices remain AVAILABLE.
        status = "BORROWED" if number <= 5 else "AVAILABLE"
        equipment = Equipment(code=code, name=name, category=category,
                              description="Thiết bị mẫu do lệnh seed tạo.",
                              location=location, status=status)
        db.session.add(equipment)
        equipment_by_code[code] = equipment
        created_equipment_codes.add(code)
        equipment_created += 1
    db.session.flush()

    today = date.today()
    loans_by_code = {
        row.loan_code: row for row in db.session.scalars(sa.select(Loan)).all()
    }
    loans_created = 0
    skipped_loans = []
    for number in range(1, 11):
        loan_code = f"DEMO-LOAN-{number:03}"
        if loan_code in loans_by_code:
            continue
        equipment = equipment_by_code[f"DEMO-EQ-{number:03}"]
        is_borrowed = number <= 5
        expected_status = "BORROWED" if is_borrowed else "AVAILABLE"
        expected_seed_details = _EQUIPMENT[number - 1]
        seed_owned = equipment.code in created_equipment_codes or (
            equipment.name == expected_seed_details[1]
            and equipment.category == expected_seed_details[2]
            and equipment.location == expected_seed_details[3]
            and equipment.description == "Thiết bị mẫu do lệnh seed tạo."
        )
        if not seed_owned or equipment.status != expected_status:
            # A colliding, already-existing user record is left untouched.
            skipped_loans.append(loan_code)
            continue
        loan_date = today - timedelta(days=3 + number)
        returned = not is_borrowed
        loan = Loan(
            loan_code=loan_code,
            user_id=user.id,
            loan_date=loan_date,
            expected_return_date=today + timedelta(days=7) if is_borrowed else loan_date + timedelta(days=3),
            actual_return_date=loan_date + timedelta(days=2) if returned else None,
            status=LoanStatus.BORROWED if is_borrowed else LoanStatus.RETURNED,
            note="Phiếu mẫu do lệnh seed tạo.",
        )
        loan.items.append(LoanItem(
            equipment=equipment,
            condition_before="Tốt, hoạt động bình thường",
            condition_after="Tốt, hoạt động bình thường" if returned else None,
        ))
        db.session.add(loan)
        loans_by_code[loan_code] = loan
        loans_created += 1
    db.session.commit()
    return equipment_created, loans_created, skipped_loans, loans_by_code


def seed_demo_data(username, password):
    user_created = create_demo_user(username, password)
    user = db.session.scalar(sa.select(User).where(User.username == username.strip()))
    equipment_created, loans_created, skipped_loans, loans_by_code = _create_demo_records(user)

    attachments_created = 0
    for loan_number, filename, content_type in _ATTACHMENT_SAMPLES:
        loan = loans_by_code.get(f"DEMO-LOAN-{loan_number:03}")
        if loan is None or loan.user_id != user.id or loan.note != "Phiếu mẫu do lệnh seed tạo.":
            continue
        existing = db.session.scalar(sa.select(Attachment.id).where(
            Attachment.loan_id == loan.id,
            Attachment.original_name == filename,
        ).limit(1))
        if existing is not None:
            continue
        data = _sample_bytes(loan_number, content_type)
        attachment = create_attachment(
            loan.id,
            FileStorage(stream=BytesIO(data), filename=filename, content_type="application/octet-stream"),
        )
        attachments_created += 1

    return {
        "user_created": user_created,
        "equipment_created": equipment_created,
        "loans_created": loans_created,
        "attachments_created": attachments_created,
        "skipped_loans": skipped_loans,
    }
