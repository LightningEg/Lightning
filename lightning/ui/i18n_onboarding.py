"""Egyptian Arabic for the phone's first launch (IV-11N): Welcome, How Lightning works, setup steps 3 to 6 and Home's
first day. Keys are the exact English strings; `i18n.py` merges this map into `ARABIC_UI`. Voice: guideline/brand-voice.md
(short, calm, concrete); the same words as the rest of the app (كلمة المرور, المتاح للصرف, صافي ثروتك)."""

ONBOARDING = {
    # Welcome
    'See how Lightning works': 'شوف لايتننج بيشتغل إزاي',
    'Already have a profile?': 'عندك ملف بالفعل؟',
    # How Lightning works
    'How Lightning works': 'لايتننج بيشتغل إزاي',
    'A bank message': 'رسالة من البنك',
    'Lightning logs it for you': 'لايتننج بيسجّلها لك',
    'Example': 'مثال',
    'How do I record my money?': 'أسجّل فلوسي إزاي؟',
    'Your bank texts you after every card payment. Lightning reads the message and logs the payment for you.':
        'البنك بيبعتلك رسالة بعد كل دفعة بالكارت. لايتننج بيقرا الرسالة ويسجّل الدفعة لوحده.',
    'Logged today': 'اتسجّل النهارده',
    'Two from bank messages, one typed in two taps.': 'اتنين من رسايل البنك، وواحدة كتبتها في لمستين.',
    'Only messages from banks like CIB and NBE are read, never from people. Next: where your money went.':
        'بيقرا رسايل البنوك بس، زي CIB والأهلي، وعمره ما يقرا رسايل الناس. اللي جاي: فلوسك راحت فين.',
    'Koshary at lunch': 'كشري على الغدا',
    'Groceries': 'البقالة',
    'Transport': 'المواصلات',
    'Added by you': 'إنت اللي ضفته',
    'Where did my money go?': 'فلوسي راحت فين؟',
    'Every payment lands in a category, so the month sorts itself.': 'كل دفعة بتقع في فئة، فالشهر بيترتّب لوحده.',
    '{amt} less than last month.': 'أقل من الشهر اللي فات بـ {amt}.',
    'Lightning suggests a budget from what you actually spend. Next: what you can spend today.':
        'لايتننج بيقترح ميزانية من صرفك الحقيقي. اللي جاي: تقدر تصرف كام النهارده.',
    'What can I spend today?': 'أقدر أصرف كام النهارده؟',
    'Your bills, your budget and your savings are set aside first. What is left is safe.':
        'فواتيرك وميزانيتك وادخارك بيتحجزوا الأول. اللي فاضل تصرفه وإنت مطمّن.',
    'Spend up to this today and every plan still holds until payday.': 'اصرف لحد المبلغ ده النهارده، وكل خططك ماشية لحد يوم القبض.',
    'Free cash is what is left after money that already has a job, like a bill due or cash held for family. Next: everything you own.':
        'النقدية المتاحة هي اللي فاضل بعد الفلوس اللي ليها شغلانة، زي فاتورة مستحقة أو فلوس شايلها للعيلة. اللي جاي: كل اللي تملكه.',
    'Already planned for': 'محجوز بالفعل',
    'Savings still planned': 'ادخار لسه في الخطة',
    'What do I have?': 'أنا عندي كام؟',
    'Net worth is what you would keep if you paid everything you owe today.': 'صافي ثروتك هو اللي هيفضل معاك لو دفعت كل اللي عليك النهارده.',
    '{amt} more than at the start of the month.': 'أكتر من أول الشهر بـ {amt}.',
    'Not money to spend: it grows as you pay debts and save. Your profile starts empty and fills as you go.':
        'دي مش فلوس للصرف: بتكبر كل ما تسدّد ديونك وتدّخر. ملفك بيبدأ فاضي ويتملي وإنت ماشي.',
    'You owe': 'عليك',
    'Cash and bank accounts': 'الكاش وحسابات البنك',
    'Certificates and gold': 'الشهادات والدهب',
    "Car loan and gam'eya": 'قرض العربية والجمعية',
    # Setup steps 3 to 6
    'Your first account': 'أول حساب ليك',
    'Start with the account you use most, usually the one your salary lands in. Add the others whenever you like.':
        'ابدأ بالحساب اللي بتستخدمه أكتر، غالبًا اللي مرتبك بينزل فيه. ضيف الباقي وقت ما تحب.',
    'Current or savings, like CIB or NBE': 'جاري أو توفير، زي CIB أو الأهلي',
    'Mobile wallet': 'محفظة موبايل',
    'Like Vodafone Cash or InstaPay': 'زي فودافون كاش أو إنستاباي',
    'Bank or wallet': 'البنك أو المحفظة',
    'Type and pick, like CIB': 'اكتب واختار، زي CIB',
    'Like Salary account': 'زي حساب المرتب',
    'Balance today': 'الرصيد النهارده',
    'As your bank app shows it now. Without it, what you can spend starts at zero.':
        'زي ما ظاهر في تطبيق البنك دلوقتي. من غيره، المتاح للصرف هيبدأ من صفر.',
    'Skip for now': 'تخطّى دلوقتي',
    'Explore a sample instead': 'جرّب مثال بدل كده',
    'Your salary': 'مرتبك',
    'Lightning plans until your next payday, so it needs the day and about how much. You still record the salary when it arrives.':
        'لايتننج بيخطط لحد يوم القبض الجاي، فمحتاج اليوم وحوالي كام. وبرضه بتسجّل المرتب لما ينزل.',
    'Your income is already set up. Edit it in Plan › Recurring.': 'دخلك متسجّل بالفعل. عدّله من الخطة › المتكرر.',
    'About how much arrives each month?': 'حوالي كام بينزل كل شهر؟',
    'Like 30,000': 'زي 30,000',
    'Day it arrives': 'يوم ما بينزل',
    '1 to 31': 'من 1 لـ 31',
    'If it moves a little each month, pick the usual day.': 'لو بيتحرك شوية كل شهر، اختار اليوم المعتاد.',
    'It lands in': 'بينزل في',
    'Cash, in hand': 'كاش في إيدك',
    'Saved with your cash wallet, next': 'هيتحفظ مع محفظة الكاش، في الخطوة الجاية',
    'Save salary': 'احفظ المرتب',
    'Enter the salary as a number, like 30,000.': 'اكتب المرتب رقم، زي 30,000.',
    'I have no fixed salary': 'معنديش مرتب ثابت',
    'Your cash wallet': 'محفظة الكاش',
    'This account is your real wallet: the notes and coins you carry. It does not mean logging every small purchase.':
        'الحساب ده هو محفظتك الحقيقية: الفلوس الورق والفكة اللي معاك. ومش معناه إنك تسجّل كل حاجة صغيرة بتشتريها.',
    'One week with your wallet': 'أسبوع مع محفظتك',
    'Saturday': 'السبت',
    'You have 2,000 in your wallet. That is the balance you type above.': 'معاك 2,000 في المحفظة. ده الرصيد اللي بتكتبه فوق.',
    'During the week': 'طول الأسبوع',
    'Tea, a microbus, a snack. You pay and move on: nothing to log.': 'شاي، ميكروباص، حاجة تاكلها. بتدفع وتكمّل: مفيش حاجة تتسجّل.',
    'Friday': 'الجمعة',
    'Count your wallet: 1,500 left. Log the missing 500 as one expense in a general category, like Other personal. One minute, and your wallet matches.':
        'عِدّ محفظتك: فاضل 1,500. سجّل الـ 500 الناقصين مصروف واحد في فئة عامة، زي أخرى (شخصي). دقيقة واحدة، ومحفظتك مظبوطة.',
    'Want to follow one kind of spending?': 'عايز تتابع نوع صرف معيّن؟',
    'If you want to see what transport costs you, log each ride in Transportation as it happens. Everything else stays in the one weekly sum.':
        'لو عايز تعرف المواصلات بتكلّفك كام، سجّل كل مشوار في المواصلات وقتها. وكل الباقي يفضل في المبلغ الأسبوعي الواحد.',
    'Cash from an ATM moves here by itself once bank messages are on.': 'الكاش اللي بتسحبه من الماكينة بيتنقل هنا لوحده لما رسايل البنك تشتغل.',
    '{name} is ready.': '{name} جاهز.',
    'Your cash wallet is ready.': 'محفظة الكاش جاهزة.',
    'Cash in your wallet now': 'الكاش اللي معاك دلوقتي',
    'Add my cash wallet': 'ضيف محفظة الكاش',
    'I never use cash': 'أنا مش بستخدم كاش خالص',
    'Your salary arrives in cash, so it needs this wallet.': 'مرتبك بينزل كاش، فمحتاج المحفظة دي.',
    'Make this phone quick': 'خلّي الموبايل أسرع',
    'Two helpers, both optional. You can change either later in Settings.': 'مساعدين اتنين، الاتنين اختياري. تقدر تغيّر أي واحد بعدين من الإعدادات.',
    'Bank messages log themselves': 'رسايل البنك تتسجّل لوحدها',
    'On. Card payments from your bank messages save themselves.': 'شغّال. دفعات الكارت من رسايل البنك بتتحفظ لوحدها.',
    'On this device, paste a bank message from Add › From SMS instead.': 'على الجهاز ده، الصق رسالة البنك من أضف › من رسائل البنك.',
    'Unlock with your fingerprint': 'افتح ببصمتك',
    'Open Lightning with a touch instead of typing your password. Type your password once to turn it on.':
        'افتح لايتننج بلمسة بدل ما تكتب كلمة المرور. اكتبها مرة واحدة علشان تشغّل البصمة.',
    'Finish setup': 'خلّص التجهيز',
    # Home's first day after setup
    'Your regular bills': 'فواتيرك الثابتة',
    'Rent, internet, phone: what comes every month': 'الإيجار، النت، الموبايل: اللي بييجي كل شهر',
    'I have no regular bills': 'معنديش فواتير ثابتة',
    'Two steps, about a minute': 'خطوتين، حوالي دقيقة',
    '{n} steps, about a minute': '{n} خطوات، حوالي دقيقة',
}
