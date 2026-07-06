"""Orders missing ingredients: product search, size/price match, cart ops,
checkout. Respects the ₹1000 cart cap and COD-only constraint; never
silent-swaps on stockout; always confirms address before checkout.
"""
