"""Egyptian Arabic for the phone's reading screens (3AN4, 3AN7, 3AN9, 3AN12): Overview, Budget, Spending, Cash
planning, Recurring, Reserves and Financial health. Keys are the exact English strings; `i18n.py` merges this map into
`ARABIC_UI`. Voice: guideline/brand-voice.md (short, calm, concrete)."""

PHONE_READING = {
    # 3AN4: Needs you names the next bill
    '{name} {amt} today': '{name} {amt} النهارده',
    '{name} {amt} tomorrow': '{name} {amt} بكرة',
    '{name} {amt} in {n} days': '{name} {amt} بعد {n} يوم',
    '{name} {amt}, 1 day late': '{name} {amt}، متأخر يوم',
    '{name} {amt}, {n} days late': '{name} {amt}، متأخر {n} يوم',
    '1 payment due soon': 'دفعة مستحقة قريب',
    '{n} payments due soon': '{n} دفعات مستحقة قريب',
    'Tomorrow': 'بكرة',
}
