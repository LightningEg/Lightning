"""Build contract checks, also runnable through unittest."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_themes', ROOT / 'tools/build_themes.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ThemeBuildTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((builder.SOURCE / 'nile-nocturne.json').read_text())

    def validate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'theme.json'
            path.write_text(json.dumps(self.manifest))
            return builder.load(path)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the runtime contract checks')
    def test_runtime_contract(self):
        result = subprocess.run(['node', '--test', str(ROOT / 'tests/theme-runtime.test.cjs')],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_files_and_creator_template(self):
        builder.build(check=True)
        builder.load(ROOT / 'theme-kit/theme.template.json')

    def test_rejects_script_colour_layout_and_unapproved_pattern(self):
        for part, key, value in [('palette', 'text', 'url(https://example.com)'),
                                 ('cards', 'width', '100px'),
                                 ('decoration', 'pattern', 'remote-svg')]:
            with self.subTest(part=part):
                self.setUp()
                self.manifest['parts'][part][key] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_decoration_takes_only_approved_patterns_and_motions(self):
        self.manifest['parts']['decoration'] = {'pattern': 'papyrus-guilloche', 'motion': 'security-thread'}
        self.validate()
        for key, value in [('pattern', 'url(x)'), ('motion', 'spin'), ('motion', 'papyrus-guilloche')]:
            with self.subTest(key=key, value=value):
                self.setUp()
                self.manifest['parts']['decoration'] = {'pattern': 'none', 'motion': 'none', key: value}
                with self.assertRaises(ValueError):
                    self.validate()

    def test_registry_names_decoration_and_every_one_is_drawn(self):
        registry = json.loads((builder.STATIC / 'themes.generated.json').read_text())
        decor = (builder.STATIC / 'theme-decor.css').read_text()
        contract = json.loads((builder.SOURCE / 'slots.json').read_text())['slots']['decoration']
        papyrus = next(t for t in registry if t['id'] == 'nile-papyrus-guilloche')
        self.assertEqual((papyrus['pattern'], papyrus['motion']), ('papyrus-guilloche', 'security-thread'))
        self.assertNotIn('pattern', next(t for t in registry if t['id'] == 'nile-nocturne'))
        for name in contract['patterns'][1:]:
            self.assertIn(f'[data-texture="{name}"]', decor)
        for name in contract['motions'][1:]:
            self.assertIn(f'[data-motion="{name}"]', decor)

    def test_decoration_layer_keeps_the_motion_rules(self):
        decor = (builder.STATIC / 'theme-decor.css').read_text()
        # one motion per theme, slow, stopped by reduced motion; no requests; the brand watermark (::after) untouched
        self.assertEqual(decor.count('animation:') - decor.count('animation: none'), 1)
        self.assertIn('12s linear infinite', decor)
        self.assertIn('@media (prefers-reduced-motion: reduce)', decor)
        self.assertNotRegex(decor, r'url\((?!"data:)')
        self.assertNotIn('lead-card', decor)  # never inside a card; the Lead card keeps the brand watermark
        self.assertNotIn('transition', decor)
        for shell in ['base.html', 'phone/base.html']:
            source = (ROOT / 'lightning/ui/templates' / shell).read_text()
            self.assertLess(source.index('/static/theme-surfaces.css'), source.index('/static/theme-decor.css'))

    def test_rejects_unreadable_card_and_button(self):
        for part, key, value in [('cards', 'surface', 'text'), ('controls', 'label', 'accent')]:
            with self.subTest(part=part):
                self.setUp()
                self.manifest['parts'][part][key] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_partial_parts_inherit_but_money_is_not_recoloured(self):
        self.manifest['parts'] = {'cards': {'border': 'accent'}}
        manifest, parts = self.validate()
        css = builder.compile_theme(manifest, parts)
        self.assertIn('--theme-card-border: #0B6DD6', css)
        for token in ['--positive:', '--rose:', '--azure:', '--chart-equity:', '--pos:', '--neg:']:
            self.assertNotIn(token, css)
        # the theme's own money colours are offered as tint sources only, under their own names
        self.assertIn('--theme-income: ', css)
        self.assertIn('--theme-expense: ', css)

    def test_both_shells_boot_before_layout_styles(self):
        for shell in ['base.html', 'phone/base.html']:
            source = (ROOT / 'lightning/ui/templates' / shell).read_text()
            self.assertLess(source.index('partials/theme_head.html'), source.index('/static/style'))
            self.assertLess(source.index('/static/style'), source.index('/static/themes.generated.css'))


def test_profile_preference_survives_new_app_and_rejects_unknown_theme(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    first = TestClient(create_app(c))
    assert first.post('/settings/theme', data={'theme': 'nile-nocturne'}).status_code == 204
    # A fresh client has no browser storage; the server restores before head scripts.
    second = TestClient(create_app(c))
    source = second.get('/settings').text
    assert '<meta name="lightning-theme" content="nile-nocturne">' in source
    assert second.post('/settings/theme', data={'theme': 'not-bundled'}).status_code == 400
    assert c.settings.get('appearance_theme') == 'nile-nocturne'
    assert second.post('/settings/theme', data={'theme': 'lightning-default'}).status_code == 204
    assert c.settings.get('appearance_theme') == 'lightning-default'


if __name__ == '__main__':
    unittest.main()
