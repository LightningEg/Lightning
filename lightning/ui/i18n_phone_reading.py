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
    'Paid for this month': 'اتدفعت للشهر ده',
    '{amt} still due this month': 'باقي {amt} مستحقة الشهر ده',
    'Last payments': 'آخر المدفوعات',
    'Nothing spent here yet this month.': 'لسه ماصرفتش هنا الشهر ده.',
    'Save limit': 'احفظ الحد',
    'New month: {amt} over {n} days': 'شهر جديد: {amt} على {n} يوم',
    # 3AN12: Cash planning's forecast, months ahead and what is promised open as sheets
    'Next {n} months': 'الـ {n} شهور الجاية',
    '{name}, then the forecast': '{name}، وبعدها التوقع',
    'Lowest {amt} in {month}': 'أقل رصيد {amt} في {month}',
    'Past month ends, then estimates': 'نهايات الشهور اللي فاتت، وبعدها تقديرات',
    'In {a} · out {b}': 'داخل {a} · خارج {b}',
    'income is an average': 'الدخل متوسط',
    # 3AN12: Recurring, list first
    '{n} active': '{n} شغال',
    'Next {date}': 'الجاي {date}',
    '{n} due': '{n} مستحق',
    'Stopped': 'اللي وقف',
    'Review changed recurring amount': 'راجع مبلغ متكرر اتغير',
    'Review {name} amount': 'راجع مبلغ {name}',
    'The matched payment on {date} was {paid}, while future payments are planned at {planned}.': 'الدفعة المطابقة يوم {date} كانت {paid}، والدفعات الجاية متخططة بـ {planned}.',
    '{n} months · usually around day {day}': '{n} شهور · غالبًا حوالي يوم {day}',
    'Subscriptions come to {amt} a year.': 'الاشتراكات بتبلغ {amt} في السنة.',
    # 3AN12: Overview's rows that open sheets, Spending's lead and "More analysis"
    '{name} at the end of each month': '{name} في آخر كل شهر',
    '{n} of {m} months kept money': '{n} من {m} شهور وفّرت فيها',
    'Most spent, {sa}': 'أكتر صرف، {sa}',
    'Most on {sa}': 'أكتر صرف يوم {sa}',
    'Usual {amt}': 'المعتاد {amt}',
    '1 payment': 'دفعة واحدة',
    'More analysis': 'تحليل أكتر',
    'Days, months, money in and out': 'أيام وشهور وفلوس داخلة وخارجة',
}
