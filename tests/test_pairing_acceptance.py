"""The acceptance runner never opens existing data or invents physical evidence."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.pairing_acceptance import run


def test_acceptance_refuses_nonempty_folder_without_touching_it(tmp_path):
    marker = tmp_path/'keep.txt'
    marker.write_text('existing data')
    with pytest.raises(ValueError,match='empty'):
        run(tmp_path)
    assert list(tmp_path.iterdir()) == [marker]
    assert marker.read_text() == 'existing data'


def test_acceptance_requires_dummy_acknowledgment(tmp_path):
    tool = Path(__file__).parents[1]/'tools/pairing_acceptance.py'
    result = subprocess.run([sys.executable,str(tool),'--root',str(tmp_path/'untouched')],capture_output=True,text=True)
    assert result.returncode == 2 and '--dummy is required' in result.stderr
    assert not (tmp_path/'untouched').exists()


def test_acceptance_process_fault_matrix_and_loopback_network(tmp_path):
    report = run(tmp_path/'new-dummy')
    assert report['dummy_data'] is True
    assert all(item['result'] == 'passed' for item in report['cases']), json.dumps(report['cases'],indent=2)
    assert sum(item['evidence']=='automated-process-kill' for item in report['cases']) == 5
    assert sum(item['evidence']=='automated-loopback' for item in report['cases']) == 3
    assert report['physical'] and all(item['result']=='unrun' for item in report['physical'])
    serialized = json.dumps(report)
    assert 'PRIVATE KEY' not in serialized and 'pairing acceptance dummy password' not in serialized
    assert 'device_id' not in serialized and 'session_token' not in serialized
