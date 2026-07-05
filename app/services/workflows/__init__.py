"""Guided WhatsApp write workflows — Phase 2A.

Same contract as app/services/onboarding_flow.py and app/services/
followup.py: each handler only mutates Company.active_workflow /
workflow_scratch plus adds rows — it never commits. The webhook commits
once. Zero LLM reasoning inside; every field is asked for explicitly and
validated deterministically.
"""
