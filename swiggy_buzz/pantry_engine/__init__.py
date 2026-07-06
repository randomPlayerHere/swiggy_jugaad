"""Core IP: consumption-decay math + confidence scoring.

Given purchase events for a canonical ingredient, estimates the probability
it is still in the kitchen (exponential decay per category, scaled by
household size). Output is always a confidence, never an assertion.
"""
