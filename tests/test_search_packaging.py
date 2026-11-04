"""RapidFuzz is shipped on each platform; Android's portable build agrees with native ranking."""
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / 'packaging/third-party/rapidfuzz-3.14.3-py3-none-any.whl'


def test_android_wheel_has_verified_portable_contents_and_license():
    assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == '8e300f5974c411be699fd53f775fffbe94204a012a3091e23e1a300c2fc8ebad'
    with zipfile.ZipFile(WHEEL) as wheel:
        assert all(not p.startswith('/') and '..' not in p.split('/') and not p.endswith(('.so', '.pyd')) for p in wheel.namelist())
        assert any('LICENSE' in p for p in wheel.namelist())
        assert 'Root-Is-Purelib: true' in wheel.read('rapidfuzz-3.14.3.dist-info/WHEEL').decode()


def test_native_and_android_python_scores_agree():
    import json
    cases = [('Talabt', 'Talabat'), ('Groceres', 'Groceries'), ('أحمد', 'احمد'), ('CIB', 'CB'), ('aa', 'ab'), ('', '')]
    script = 'import sys,json;sys.path.insert(0,sys.argv[1]);from rapidfuzz.fuzz import ratio;print(json.dumps([ratio(*p) for p in json.loads(sys.argv[2])]))'
    result = subprocess.run([sys.executable, '-I', '-c', script, str(WHEEL), json.dumps(cases)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [ratio(*pair) for pair in cases]


def test_desktop_and_android_locks_pin_the_shared_matcher():
    for platform in ('win', 'linux'):
        assert 'rapidfuzz==3.14.3' in (ROOT / f'requirements/desktop-probe-{platform}.lock').read_text()
    assert 'rapidfuzz-3.14.3-py3-none-any.whl' in (ROOT / 'requirements/android.lock').read_text()
