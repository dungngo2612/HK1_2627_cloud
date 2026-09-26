from contextlib import contextmanager
import os
from pathlib import Path
import re
from uuid import uuid4

_EXTENSIONS = {"pdf", "png", "jpg"}
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


class UnsafeStoragePath(ValueError):
    """Metadata cannot address an allowed attachment file."""


class LocalStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()

    @staticmethod
    def _name(relative_path, identifier):
        if not isinstance(relative_path, str):
            raise UnsafeStoragePath("Invalid attachment path")
        match = re.fullmatch(r"uploads/([0-9a-f]{32})\.(pdf|png|jpg)", relative_path)
        if not match or match.group(1) != identifier.hex or match.group(2) not in _EXTENSIONS:
            raise UnsafeStoragePath("Invalid attachment path")
        return relative_path.removeprefix("uploads/")

    @contextmanager
    def _uploads(self, *, create):
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_fd = os.open(self.root, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        try:
            if create:
                try:
                    os.mkdir("uploads", mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            uploads_fd = os.open("uploads", os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=root_fd)
            try:
                yield uploads_fd
            finally:
                os.close(uploads_fd)
        finally:
            os.close(root_fd)

    def save(self, identifier, extension, data):
        if extension not in _EXTENSIONS:
            raise UnsafeStoragePath("Unsupported extension")
        relative_path = f"uploads/{identifier.hex}.{extension}"
        name = self._name(relative_path, identifier)
        with self._uploads(create=True) as directory:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, "wb") as target:
                    target.write(data)
                    target.flush()
                    os.fsync(target.fileno())
            except Exception:
                os.unlink(name, dir_fd=directory)
                raise
        return relative_path

    def read(self, relative_path, identifier, limit):
        name = self._name(relative_path, identifier)
        with self._uploads(create=False) as directory:
            descriptor = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=directory)
            with os.fdopen(descriptor, "rb") as source:
                return source.read(limit + 1)

    def remove(self, relative_path, identifier):
        name = self._name(relative_path, identifier)
        with self._uploads(create=False) as directory:
            os.unlink(name, dir_fd=directory)

    def probe(self):
        """Confirm uploads already exists and can be safely read and written; never mkdir."""
        name = f".healthcheck-{uuid4().hex}"
        with self._uploads(create=False) as directory:
            descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                payload = uuid4().bytes
                with os.fdopen(descriptor, "r+b") as probe_file:
                    probe_file.write(payload)
                    probe_file.flush()
                    probe_file.seek(0)
                    if probe_file.read(len(payload)) != payload:
                        raise OSError("Storage probe read did not match write")
            finally:
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
