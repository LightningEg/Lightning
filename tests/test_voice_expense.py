"""Exercise the same local parser the phone loads, including code-switched input."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_voice_phrases():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the phone parser")
    cases = []
    for words, expected in [
        ("١٥٠", "150"), ("ميه وخمسين", "150"), ("one hundred and fifty", "150"),
        ("٢٥٫٧٥", "25.75"), ("اربعين", "40"), ("twenty-five", "25"),
        ("٢٠ جنيه ونص", "20.50"), ("اتنين وعشرين", "22"), ("ميتين", "200"), ("ten", "10"),
    ]:
        for phrase, day in [
            (f"{words} بنزين", "2026-03-01"), (f"fuel yesterday {words}", "2026-02-28"),
            (f"دفعت {words} بنزين امبارح", "2026-02-28"), (f"today fuel {words}", "2026-03-01"),
        ]:
            cases.append([phrase, expected, day])
    cases.extend([
        ["دفعت ٢٠٠ وخدت ٥٠ باقي بنزين", "", "2026-03-01"],
        ["fuel ميه و واحد", "101", "2026-03-01"],
        ["fuel one thousand two hundred and ten", "1210", "2026-03-01"],
        ["fuel 150 2026-02-20", "150", "2026-02-20"],
        ["fuel 150 2026-02-31", "150", ""],
        ["fuel 150 dollars", "", "2026-03-01"],
        ["fuel خمسين وربع", "", "2026-03-01"],
        ["yesterday fuel", "", "2026-02-28"],
        ["fuel 20 last Friday", "20", ""],
        ["50 dollars fuel", "", "2026-03-01"],
    ])
    script = """
    require('./lightning/ui/static/voice-expense.js');
    const assert = require('node:assert/strict');
    const context = {categories:[{value:'1',label:'Fuel'}],payees:[],today:'2026-03-01'};
    for (const [phrase,amount,date] of JSON.parse(process.argv[1])) {
      const draft = lightningVoiceParse(phrase,context);
      assert.deepEqual([draft.amount,draft.date,draft.category],[amount,date,'1'],phrase);
    }
    const byName = {...context, categories: [...context.categories, {value:'2',label:'Groceries'}],
        payees:[{label:'Carrefour',aliases:['Market 42'],history:['1','2'],category:'1'}]};
    const ambiguous = lightningVoiceParse('150 at Market 42',byName);
    assert.equal(ambiguous.payee,'Carrefour');
    assert.equal(ambiguous.amount,'150');
    assert.equal(ambiguous.category,'');
    assert.deepEqual(ambiguous.choices.map(o=>o.value),['1','2']);
    assert.equal(lightningVoiceParse('150 كارفور بقالة',byName).category,'2');
    assert.equal(lightningVoiceParse('fuel 10 and groceries 20',byName).multipleAmounts,true);
    assert.equal(lightningVoiceParse('15 fossilfuel',byName).category,'');
    """
    subprocess.run([node, "-e", script, json.dumps(cases)], cwd=Path(__file__).resolve().parents[1], check=True)
