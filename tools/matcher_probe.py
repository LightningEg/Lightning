"""Use a subset of existing platform hashes to isolate matcher/freezer validation.

The full desktop dependency probe separately owns WebView and profile dependencies.
"""
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def lock(platform):
    names = {'rapidfuzz', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph',
             'packaging', 'setuptools', 'pefile', 'pywin32-ctypes'}
    blocks = re.split(r'(?m)(?=^[a-zA-Z0-9][a-zA-Z0-9_.-]*==)',
                      (ROOT / f'requirements/desktop-probe-{platform}.lock').read_text())
    selected = [b for b in blocks if b.split('==')[0] in names]
    assert any(b.startswith('rapidfuzz==3.14.3') for b in selected)
    print(''.join(selected))


def check():
    from rapidfuzz.fuzz import ratio
    wheel = ROOT / 'packaging/third-party/rapidfuzz-3.14.3-py3-none-any.whl'
    cases = [('Talabt', 'Talabat'), ('Groceres', 'Groceries'), ('أحمد', 'احمد'), ('CIB', 'CB'), ('aa', 'ab'), ('', '')]
    script = 'import sys,json;sys.path.insert(0,sys.argv[1]);from rapidfuzz.fuzz import ratio;print(json.dumps([ratio(*p) for p in json.loads(sys.argv[2])]))'
    result = subprocess.run([sys.executable, '-I', '-c', script, str(wheel), json.dumps(cases)],
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [ratio(*pair) for pair in cases]
    print('Native and portable matcher agree')


if __name__ == '__main__':
    if sys.argv[1] == 'lock':
        lock(sys.argv[2])
    else:
        check()
