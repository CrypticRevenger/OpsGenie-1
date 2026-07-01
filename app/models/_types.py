"""Reusable SQLAlchemy column type aliases.

Centralising these avoids repeating magic numbers (14, 2) across every model
and makes schema-wide changes a one-line edit.
"""

from sqlalchemy import Numeric

# Monetary amounts: up to 12 digits before the decimal, 2 after.
# Covers values up to ₹999,999,999,999.99 — sufficient for pilot scale.
Money = Numeric(14, 2)

# Quantities for invoice line items: 4 decimal places to support unit fractions
# (e.g. 0.5 kg, 2.25 litres).
Quantity = Numeric(14, 4)
