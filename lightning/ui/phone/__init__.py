"""The phone's own presentation layer (IV-3AY4): a router mounted only for the phone app, screens that ask the services
for exactly what they show, and templates under ``templates/phone/`` only. It never imports ``lightning.ui.routes``
(an import-linter contract), so a PC route change cannot reach the phone. Slots move here one at a time (3AY6 to
3AY10); URLs this package does not own still reach the old routes until 3AY11 removes them."""
