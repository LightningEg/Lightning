# Lightning brand and design guidelines

This is the authoritative map of the shared design system. Open the HTML
documents in a browser; use their document titles for the current shared version
(3.34 at this map's introduction). Voice and themes carry their own dated revisions.

| Surface / concern | English authority | Arabic companion |
| --- | --- | --- |
| A · PC app | [app.html](app.html) | [app-ar.html](app-ar.html) |
| B · Main website | [website.html](website.html) | [website-ar.html](website-ar.html) |
| C · Phone app | [phone.html](phone.html) | [phone-ar.html](phone-ar.html) |
| D · For Geeks website | [coders.html](coders.html) | No separate Arabic Part D |
| Writing and tone | [Brand voice](brand-voice.md) | Arabic rules included |
| Theme parts and delivery | [Themes](themes.md) | Shared technical contract |

Part C overrides Part A on a phone. English documents govern except Arabic
typography and wording in Part B Arabic (B04/B10). Follow Arabic-specific rules
when producing Arabic screens; do not invent a separate layout or style system.

## Assets and templates

- [Reference logos and banners](../assets/logos/README.md) preserve source assets;
  they do not replace runtime assets automatically.
- [Theme creator kit](https://github.com/LightningEg/Lightning/tree/main/theme-kit)
  contains the brief, AI prompt, manifest template, preview and acceptance roster.
- [Template catalogue](../templates/README.md) covers reports and feedback.

## Maintenance

The app and website mirror this entire directory. Edit both in the same session,
open a PR in each, and compare every Markdown and HTML file, including Arabic,
voice, themes and this map. With sibling checkouts run the app's
`python -m pytest tests/test_docs_structure.py -q`; the mirror comparison requires
both repositories and reports a skip if the sibling checkout is absent.

For targeted reading from the app root, `python tools/guideline.py` lists sections
and `python tools/guideline.py A12` prints one. From the website root use
`python ../Lightning/tools/guideline.py --dir guideline B05` with the app beside it.
