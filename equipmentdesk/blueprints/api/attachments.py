from io import BytesIO

from flask import Blueprint, jsonify, send_file

from equipmentdesk.services import attachments as service

bp = Blueprint("attachments_api", __name__, url_prefix="/api/attachments")


@bp.get("/<uuid:attachment_id>", strict_slashes=False)
def detail(attachment_id):
    return jsonify(service.serialize_attachment(service.get_attachment(attachment_id)))


@bp.get("/<uuid:attachment_id>/download", strict_slashes=False)
def download(attachment_id):
    attachment = service.get_attachment(attachment_id)
    data = service.download_bytes(attachment)
    return send_file(BytesIO(data), mimetype=attachment.content_type, as_attachment=True,
                     download_name=service.download_name(attachment), etag=False)
