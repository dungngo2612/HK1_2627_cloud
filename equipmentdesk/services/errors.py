class ServiceError(Exception):
    """An expected business/validation failure, safe to show to the user."""

    def __init__(self, message, *, code="validation_error", status=422, fields=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.fields = fields or {}
