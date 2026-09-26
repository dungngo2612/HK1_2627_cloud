from enum import StrEnum


class EquipmentStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    BORROWED = "BORROWED"
    MAINTENANCE = "MAINTENANCE"


class LoanStatus(StrEnum):
    BORROWED = "BORROWED"
    RETURNED = "RETURNED"
