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
    # 3AN7: Budget in order of need, a category's sheet
    'Over its limit by {amt}': 'عدّيت الحد بـ {amt}',
    'Ahead of pace: {n}% spent, {m}% of the month gone': 'أسرع من المعدل: صرفت {n}% وعدّى {m}% من الشهر',
    'On pace: {n}% spent, {m}% of the month gone': 'على المعدل: صرفت {n}% وعدّى {m}% من الشهر',
    'Last payments': 'آخر المدفوعات',
    'Nothing spent here yet this month.': 'لسه ماصرفتش هنا الشهر ده.',
    'Save limit': 'احفظ الحد',
    'New month: {amt} over {n} days': 'شهر جديد: {amt} على {n} يوم',
}
