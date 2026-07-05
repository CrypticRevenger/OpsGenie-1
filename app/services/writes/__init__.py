"""Deterministic write services — Phase 2A.

Every function here is the "Python does the arithmetic" half of the money
rule: no LLM ever computes or invents money. These are called only from
app/services/writes/pending_operation.py's execute_pending_operation, at
confirm time, against fresh DB state — never from a cached preview.
"""
