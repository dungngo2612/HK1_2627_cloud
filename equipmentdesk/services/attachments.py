from hashlib import sha256
from io import BytesIO
import logging
from uuid import UUID, uuid4
import warnings

from flask import current_app
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from werkzeug.utils import secure_filename

from equipmentdesk.extensions import db
from equipmentdesk.models import Attachment
from equipmentdesk.storage.local import LocalStorage, UnsafeStoragePath
from .errors import ServiceError
from .loans import get_loan

MAX_FILE_SIZE = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


def _storage():
    return LocalStorage(current_app.config["APP_STORAGE_ROOT"])


def _original_name(raw_name):
    if not isinstance(raw_name, str):
        raise ServiceError("File phải có tên hợp lệ.", fields={"file": ["Thiếu tên file."]})
    name = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip(" .")
    if not name or len(name) > 255:
        raise ServiceError("Tên file không hợp lệ hoặc dài quá 255 ký tự.", fields={"file": ["Tên file không hợp lệ."]})
    return name


def _image_type(data, expected):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != expected:
                    raise ValueError("Image format differs from signature")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                if image.format != expected:
                    raise ValueError("Image format differs from signature")
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ServiceError("File ảnh không hợp lệ hoặc bị hỏng.", fields={"file": ["Nội dung ảnh không hợp lệ."]}) from None


def _content_type(data):
    if data.startswith(b"%PDF-"):
        try:
            if b"%%EOF" not in data[-1024:]:
                raise ValueError("Missing PDF trailer")
            reader = PdfReader(BytesIO(data), strict=True)
            if len(reader.pages) < 1:
                raise ValueError("PDF has no page")
        except (PdfReadError, ValueError, TypeError, KeyError, OSError, OverflowError):
            raise ServiceError("File PDF không hợp lệ hoặc bị hỏng.", fields={"file": ["Nội dung PDF không hợp lệ."]}) from None
        return "application/pdf", "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        _image_type(data, "PNG")
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        _image_type(data, "JPEG")
        return "image/jpeg", "jpg"
    raise ServiceError("Chỉ chấp nhận file PDF, PNG hoặc JPEG hợp lệ.", fields={"file": ["Loại file không được hỗ trợ."]})


def create_attachment(loan_id, upload):
    get_loan(loan_id)  # Establish a valid parent before reading or writing the file.
    if upload is None:
        raise ServiceError("Vui lòng chọn file biên bản.", fields={"file": ["Chưa chọn file."]})
    original_name = _original_name(upload.filename)
    data = upload.stream.read(MAX_FILE_SIZE + 1)
    if not data:
        raise ServiceError("File không được rỗng.", fields={"file": ["File rỗng."]})
    if len(data) > MAX_FILE_SIZE:
        raise ServiceError("File không được vượt quá 10 MB.", status=413, code="file_too_large",
                           fields={"file": ["Vượt giới hạn 10 MB."]})
    content_type, extension = _content_type(data)
    identifier = uuid4()
    storage = _storage()
    try:
        relative_path = storage.save(identifier, extension, data)
    except (OSError, UnsafeStoragePath):
        logger.exception("Could not save attachment file")
        raise ServiceError("Không thể lưu file biên bản.", status=503, code="storage_unavailable") from None
    attachment = Attachment(id=identifier, loan_id=loan_id, relative_path=relative_path,
                            original_name=original_name, content_type=content_type,
                            size=len(data), sha256=sha256(data).hexdigest())
    try:
        db.session.add(attachment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            storage.remove(relative_path, identifier)
        except OSError:
            logger.exception("Could not clean up attachment after database failure")
        raise
    return attachment


def get_attachment(identifier):
    if not isinstance(identifier, UUID):
        raise ServiceError("Không tìm thấy file biên bản.", status=404, code="not_found")
    attachment = db.session.get(Attachment, identifier)
    if attachment is None:
        raise ServiceError("Không tìm thấy file biên bản.", status=404, code="not_found")
    return attachment


def download_bytes(attachment):
    try:
        data = _storage().read(attachment.relative_path, attachment.id, MAX_FILE_SIZE)
    except UnsafeStoragePath:
        raise ServiceError("Đường dẫn file không hợp lệ.", status=409, code="unsafe_storage_path") from None
    except FileNotFoundError:
        raise ServiceError("File vật lý không còn trên ổ đĩa.", status=404, code="file_missing") from None
    except OSError:
        logger.exception("Could not read attachment file")
        raise ServiceError("Không thể đọc file biên bản.", status=503, code="storage_unavailable") from None
    if len(data) != attachment.size or sha256(data).hexdigest() != attachment.sha256:
        raise ServiceError("File đã thay đổi so với thông tin lưu trong database.", status=409, code="file_integrity_error")
    return data


def download_name(attachment):
    name = secure_filename(attachment.original_name)
    extension = attachment.relative_path.rsplit(".", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem or 'bien_ban'}.{extension}"


def serialize_attachment(attachment):
    return {"id": str(attachment.id), "loan_id": attachment.loan_id,
            "relative_path": attachment.relative_path, "original_name": attachment.original_name,
            "content_type": attachment.content_type, "size": attachment.size,
            "sha256": attachment.sha256, "created_at": attachment.created_at.isoformat()}
