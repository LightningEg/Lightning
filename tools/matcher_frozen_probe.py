"""Standalone native-module smoke test used in the focused packaged dependency check."""
from rapidfuzz.fuzz import ratio

assert ratio('Talabt', 'Talabat') > 90
assert ratio('أحمد', 'احمد') == 75
assert ratio('Groceres', 'Groceries') > 90
print('Frozen matcher passed')
