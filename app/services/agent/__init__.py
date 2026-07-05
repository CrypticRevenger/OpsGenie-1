"""Agentic WhatsApp assistant: tool-calling agent over deterministic DB tools.

The LLM decides *which* read tool to call and phrases the answer; every tool
executes deterministic Python that owns the numbers, so the "LLM never computes
money" rule holds (and is checked again by money_guard before sending).
"""
