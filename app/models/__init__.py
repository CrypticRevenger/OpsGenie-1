"""ORM model registry for OpsGenie.

Importing this package registers all models with SQLAlchemy's mapper and
``Base.metadata``, which is required for Alembic autogenerate to detect the
full schema.

Import order follows the FK dependency chain so relationships resolve cleanly:
companies → dealers/suppliers/products → invoices → invoice_items/payments
→ all event and log tables.
"""

from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.cash_snapshot import CashSnapshot
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.import_log import ImportLog
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.morning_briefing import MorningBriefing
from app.models.notification_log import NotificationLog
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.models.supplier import Supplier

__all__ = [
    "ActivityEntityType",
    "ActivityEventType",
    "ActivityTimeline",
    "BusinessEvent",
    "BusinessEventType",
    "CashSnapshot",
    "Company",
    "Dealer",
    "ImportLog",
    "Invoice",
    "InvoiceDirection",
    "InvoiceItem",
    "InvoiceSource",
    "InvoiceStatus",
    "MorningBriefing",
    "NotificationLog",
    "Payment",
    "PaymentSource",
    "Product",
    "Supplier",
]
