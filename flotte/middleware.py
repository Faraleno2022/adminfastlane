"""Compatibilité : le middleware est désormais ``core.tenancy.TenancyMiddleware``."""
from core.tenancy import TenancyMiddleware as FlotteEntrepriseMiddleware  # noqa: F401
