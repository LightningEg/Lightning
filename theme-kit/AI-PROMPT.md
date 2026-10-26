# Brief for an AI theme creator

Complete the fields below, then give this prompt and the kit to the AI.

```text
Create a Lightning theme for PC and phone using the existing theme creator kit.

Name: [theme name]
Mode: [Dark | Light | Both]
Mood and references: [description, images or links]
Ground preference: [specify OLED black if required]

Read theme-kit/README.md, guideline/themes.md, the relevant sections of
guideline/app.html and guideline/phone.html, and
lightning/ui/static/cosmetics/slots.json before designing.
Start from theme-kit/theme.template.json, or from the closer reference
theme (cotton.json, light; papyrus.json, dark). If a
required brief field is unfilled, ask for it rather than assuming a mode
or aesthetic.

A theme is every element in the README's inventory times three layers:
paint (palette keys), material (finish, grain, edge light, depth, artwork)
and motion. State every layer of every element; choose materials and
motions only from the README's recipe library, with one continuous motion
at most. Aim for a material, not a recolour: decide what the theme is made
of (paper, lacquer, linen, foil) and let every element follow it.

Each manifest represents one palette. For Both, deliver separate complete
dark and light manifests with distinct IDs. They are selected explicitly;
do not invent automatic mode switching or a JSON mode property.
Keep status test-preview and priceCoins null.

Preserve layout, typography, spacing, financial colours, number formatting
and app behaviour. Follow the element inventory; do not introduce theme
HTML, scripts, remote assets or arbitrary CSS. If the theme needs a
recipe the library lacks, describe it for the maintainers instead.

Meet WCAG AA: body text, labels and numbers (including chip text) at least
4.5:1; meaningful control borders, chip indicators and focus rings at least
3:1 against adjacent backgrounds. Keep primary text on ground at least 7:1.
Measure actual financial colours and interactive states on their surfaces.

In Arabic, mirror layout and text while keeping complete amounts LTR,
for example EGP 14,250.00. Preserve existing bdi/dir=ltr isolation, locale
digits, signs, separators, precision and currency labels. Do not reverse
amount strings or change formatting. The example shows direction only.

Capture Overview, Transactions, Budget, Investments, Accounts and Settings
on BOTH PC and phone, in English and Arabic/RTL, for EACH requested mode.
Use the README's screen/state roster and viewport sizes. Include transaction
pills, positive/negative/decimal amounts, an open transaction dialog or
phone sheet, and control focus, disabled, error, menu and empty states.
Compare default and new theme geometry with the same dummy data.
Workbench images alone do not satisfy real-screen acceptance.

Validate each manifest with tools/build_themes.py --validate, integrate
reviewed previews as the README describes, generate the theme assets and
run tools/build_themes.py --check. Verify swapping preserves scroll,
unsaved forms and dialogs, and reload restores the choice.

Return the completed brief, manifest(s), generated files, labelled
screenshots, contrast/check results and asset licence/credits. State any
unavailable native-device checks or remaining gaps; do not claim them passed.
```
