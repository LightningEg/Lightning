# Portable search dependency

`rapidfuzz-3.14.3-py3-none-any.whl` is upstream RapidFuzz's Python implementation for Android, which has no upstream native wheel. Windows and Linux use the same version's upstream native wheels. No financial code differs between platforms.

- Source: https://pypi.org/project/RapidFuzz/3.14.3/
- Source archive SHA-256: `2491937177868bc4b1e469087601d53f925e8d270ccc21e07404b4b5814b7b5f`
- Wheel SHA-256: `8e300f5974c411be699fd53f775fffbe94204a012a3091e23e1a300c2fc8ebad`
- Builder: scikit-build-core 1.1.2; Python 3.12; upstream source unchanged.
- Command: `SOURCE_DATE_EPOCH=1700000000 RAPIDFUZZ_BUILD_EXTENSION=0 python -m pip wheel rapidfuzz-3.14.3 --no-deps -Cwheel.cmake=false`.
- MIT license and copyright notices are inside the wheel.

The Android lock uses an immutable repository commit URL and the wheel's hash. Its content and the native/Python ranking equivalence are checked by `tests/test_search_packaging.py`. This file is a dependency build input, not an application release.

The source commit is retained by `third-party/rapidfuzz-3.14.3-portable`, so the immutable Android URL remains reachable after squash merges. This vendor tag publishes no app release.
