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
        self.manifest = json.loads((builder.SOURCE / 'nile.json').read_text())

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

    def test_rejects_script_colour_layout_and_unapproved_recipe(self):
        for part, key, value in [('palette', 'text', 'url(https://example.com)'),
                                 ('cards', 'width', '100px'),
                                 ('ground', 'texture', 'remote-svg'),
                                 ('cards', 'finish', 'url(x)'),
                                 ('hero', 'sheen', 'spin'),
                                 ('controls', 'finish', 'accent')]:
            with self.subTest(part=part, key=key):
                self.setUp()
                self.manifest['parts'][part][key] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_a_delivered_theme_states_every_layer_of_every_element(self):
        contract = json.loads((builder.SOURCE / 'slots.json').read_text())
        for slot, key in [('cards', 'grain'), ('ground', 'equip'), ('tabs', 'chosen')]:
            with self.subTest(slot=slot, key=key):
                self.setUp()
                del self.manifest['parts'][slot][key]
                with self.assertRaisesRegex(ValueError, f'{slot} needs {key}'):
                    self.validate()
        self.setUp()
        del self.manifest['parts']['progress']
        with self.assertRaises(ValueError):
            self.validate()
        # the creator template is complete: every element, every layer
        template = json.loads((ROOT / 'theme-kit/theme.template.json').read_text())
        for slot, spec in contract['slots'].items():
            self.assertEqual(set(template['parts'][slot]), set(builder.slot_keys(spec)), slot)

    def test_one_continuous_motion_at_most(self):
        self.manifest['parts']['header']['thread'] = 'security-thread'
        self.validate()
        self.manifest['parts']['hero']['sheen'] = 'edge-glint'
        with self.assertRaisesRegex(ValueError, 'One continuous motion'):
            self.validate()
        # hover, press, enter and equip answer the user, so they ride along freely
        self.setUp()
        self.manifest['parts']['hero']['sheen'] = 'edge-glint'
        self.manifest['parts']['cards']['hover'] = 'light'
        self.manifest['parts']['controls']['press'] = 'sheen'
        self.manifest['parts']['overlays']['enter'] = 'rise'
        self.manifest['parts']['ground']['equip'] = 'unveil'
        self.validate()

    def test_contrast_is_checked_at_the_material_worst_point(self):
        # the dimmest quiet text that passes on every flat surface ...
        for level in range(0x60, 0x100):
            self.manifest['parts']['palette']['muted'] = f'#{level:02X}{level:02X}{level:02X}'
            try:
                self.validate()
                break
            except ValueError:
                continue
        # ... fails once the cards wear lacquer and fibre grain
        self.manifest['parts']['cards'].update(finish='lacquer', grain='fibre')
        with self.assertRaisesRegex(ValueError, '4.5:1'):
            self.validate()

    def test_registry_carries_materials_and_every_recipe_is_drawn(self):
        registry = json.loads((builder.STATIC / 'themes.generated.json').read_text())
        css = (builder.STATIC / 'theme-materials.css').read_text()
        contract = json.loads((builder.SOURCE / 'slots.json').read_text())
        nile = next(t for t in registry if t['id'] == 'papyrus')
        self.assertNotEqual(nile['materials']['ground-texture'], 'none')
        self.assertNotIn('materials', next(t for t in registry if t['id'] == 'lightning-default'))
        neutral = {'none', 'flat', 'hairline', 'bar', 'dim', 'whisper', 'subtle', 'rich'}
        for slot, spec in contract['slots'].items():
            for key, values in builder.slot_keys(spec).items():
                if values is None or slot == 'brand':
                    continue
                attribute = 'data-m-' + slot + '-' + builder.re.sub(r'([A-Z])', r'-\1', key).lower()
                for value in set(values) - neutral:
                    if (slot, key) in {('ground', 'texture'), ('ground', 'artwork'), ('hero', 'artwork'), ('ground', 'equip')}:
                        continue  # drawn per theme by the compiler; equip by theme-runtime.js (.theme-unveil)
                    self.assertTrue(f'{attribute}="{value}"' in css, f'{slot}.{key}={value} has no recipe')
        self.assertIn("'unveil'", (builder.STATIC / 'theme-runtime.js').read_text())
        self.assertIn('.theme-unveil', css)
        self.assertLessEqual(set(contract['slots']['ground']['material']['texture']) - {'none'}, set(builder.TEXTURES))
        self.assertLessEqual(set(contract['slots']['cards']['material']['grain']) - {'none'}, set(builder.TEXTURES))
        self.assertEqual(set(contract['slots']['hero']['material']['artwork']) - {'none'}, set(builder.ARTWORK))
        self.assertEqual(set(contract['slots']['ground']['material']['textureStrength']), set(builder.STRENGTH))

    def test_material_layer_keeps_the_motion_rules(self):
        css = (builder.STATIC / 'theme-materials.css').read_text()
        # continuous motions are slow; each animation stops under reduced motion; no requests; nothing per number
        for name, seconds in builder.re.findall(r'animation: (m-[a-z]+) ([0-9.]+)s', css):
            if name in ('m-thread', 'm-glint', 'm-drift'):
                self.assertGreaterEqual(float(seconds), 8, name)
        reduced = css[css.index('@media (prefers-reduced-motion: reduce)'):]
        for selector in ('ground-ambient', 'header-thread', 'hero-sheen', 'overlays-enter', 'cards-hover', 'controls-press', 'theme-unveil'):
            self.assertIn(selector, reduced)
        self.assertNotRegex(css, r'url\((?!"data:)')
        # geometry is never a material: no padding, margins, fonts, radii, border widths, gaps or line heights
        self.assertNotRegex(css, r'[;{\s](padding|margin|font|border-radius|border-width|gap|line-height|min-height)[a-z-]*\s*:(?!\s*inherit)')
        for shell in ['base.html', 'phone/base.html']:
            source = (ROOT / 'lightning/ui/templates' / shell).read_text()
            self.assertLess(source.index('/static/theme-surfaces.css'), source.index('/static/theme-materials.css'))

    def test_rejects_unreadable_card_and_button(self):
        for part, key, value in [('cards', 'surface', 'text'), ('controls', 'label', 'accent')]:
            with self.subTest(part=part):
                self.setUp()
                self.manifest['parts'][part][key] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_each_paid_theme_fills_exactly_its_tier(self):
        """themes.md section 7: recolour, then texture, then animation; the store's tier for each id (8L migration)."""
        contract = json.loads((builder.SOURCE / 'slots.json').read_text())
        neutral = {'none', 'flat', 'hairline', 'bar', 'dim', 'subtle'}
        for theme, tier in {'nile': 'palette', 'cotton': 'texture', 'papyrus': 'motion'}.items():
            parts = json.loads((builder.SOURCE / f'{theme}.json').read_text())['parts']
            material = {f'{s}.{k}': parts[s][k] for s, spec in contract['slots'].items() if s != 'brand'
                        for k in spec.get('material', {}) if parts[s][k] not in neutral}
            running = [n for n in contract['limits']['continuous'] if parts[n.split('.')[0]][n.split('.')[1]] != 'none']
            with self.subTest(theme=theme):
                if tier == 'palette':
                    self.assertEqual(material, {}, 'a palette is colour only')
                    self.assertTrue(all(v == 'none' for s, spec in contract['slots'].items() for k in spec.get('motion', {}) for v in [parts[s][k]]))
                else:
                    self.assertTrue(material, 'a textured or animated theme has a material')
                self.assertEqual(len(running), 1 if tier == 'motion' else 0, 'only the animated tier runs a motion')

    def test_money_is_not_recoloured(self):
        self.manifest['parts']['cards']['border'] = 'accent'
        manifest, parts = self.validate()
        css = builder.compile_theme(manifest, parts, json.loads((builder.SOURCE / 'slots.json').read_text()))
        self.assertIn('--theme-card-border: #E6B450', css)
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
    assert first.post('/settings/theme', data={'theme': 'royal-obsidian-gold'}).status_code == 204
    # A fresh client has no browser storage; the server restores before head scripts.
    second = TestClient(create_app(c))
    source = second.get('/settings').text
    assert '<meta name="lightning-theme" content="royal-obsidian-gold">' in source
    assert second.post('/settings/theme', data={'theme': 'not-bundled'}).status_code == 400
    assert c.settings.get('appearance_theme') == 'royal-obsidian-gold'
    assert second.post('/settings/theme', data={'theme': 'lightning-default'}).status_code == 204
    assert c.settings.get('appearance_theme') == 'lightning-default'


if __name__ == '__main__':
    unittest.main()
