"""r31: 18 dummy bank and wallet messages through the SMS reader. Run from the repo root:
python issues/7-planning-import-and-search/r31-logging-entries/evidence/sms_battery.py"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lightning.sms_imports import is_offer, looks_like_money, parse_sms, prefill  # noqa: E402

R = datetime(2026, 11, 9, 14, 0)
TESTS = [
    ("NBE Arabic card purchase (known pattern)", "تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 1234 عند CARREFOUR MAADI يوم 06/11/26 الساعه 11:13 المتاح 3792.36EGP", "NBE"),
    ("CIB English debit card", "Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26 at 21:15. Available balance EGP 10,200.50", "CIB"),
    ("CIB English credit card", "Your credit card ending 5678 was used for EGP 1,250.00 at AMAZON.EG on 08/11 20:01. Available limit EGP 38,750.00", "CIB"),
    ("QNB English purchase", "QNB ALAHLI: Purchase transaction of EGP 320.00 on card **4321 at SEOUDI MARKET on 07/11/2026 18:40. Avl bal EGP 5,100.00", "QNBALAHLI"),
    ("Banque Misr Arabic ATM", "بنك مصر: تم سحب مبلغ 2000 جم من حسابكم رقم 9876 من ماكينة ATM بتاريخ 05/11/2026. الرصيد المتاح 8500 جم", "BanqueMisr"),
    ("Dollar purchase", "Your card ending 1234 was charged USD 12.99 at NETFLIX.COM on 03/11/26", "CIB"),
    ("Refund", "تم استرداد مبلغ 450.00 جم إلى بطاقتكم رقم 1234 من NOON يوم 04/11/26", "NBE"),
    ("Vodafone Cash payment", "تم دفع 150 جنيه من محفظتك فودافون كاش الى التاجر Koshary El Tahrir. رصيدك الحالي 3000 جنيه", "VF-Cash"),
    ("Vodafone Cash received", "تم استلام مبلغ 500 جنيه من رقم 01001234567 على محفظتك. رصيدك 3500 جنيه", "VF-Cash"),
    ("InstaPay out, CIB (known pattern)", "تم تنفيذ تحويل لحظي بمبلغ 2000.00 جم من حسابك المنتهي بـ ****1234 برقم مرجعي ab12 بتاريخ 01-11-2026 11:05", "CIB"),
    ("Fawry bill", "تم سداد فاتورة كهرباء بمبلغ 620.50 جم من حسابكم رقم 1234 عن طريق فوري يوم 02/11/26", "NBE"),
    ("Bank fee", "تم خصم 25.00 جم مصاريف ادارية من حسابكم رقم 1234 بتاريخ 01/11/2026", "NBE"),
    ("One-time code", "رمز التحقق الخاص بك هو 123456 لعملية شراء بمبلغ 500 جم", "CIB"),
    ("Declined", "تم رفض عملية شراء بمبلغ 900 جم على بطاقتكم رقم 1234 لعدم كفاية الرصيد", "NBE"),
    ("Telda English", "You spent EGP 85.00 at Costa Coffee using your Telda card. Balance: EGP 1,215.00", "Telda"),
    ("valU instalment", "تم خصم قسط بقيمة 1,100 جنيه من حسابك لدى فاليو. القسط القادم 01/12/2026", "valU"),
    ("Salary, CIB (known pattern)", "عميلنا العزيز لقد تم تحويل مبلغ EGP19,584.66 على حسابكم لدينا من جهة العمل", "CIB"),
    ("Arabic digits and decimal mark", "تم خصم ١٤٧٫٨٧ جم من بطاقة الخصم المباشر رقم ١٢٣٤ عند كارفور يوم ٠٦/١١/٢٦", "NBE"),
]
for name, text, sender in TESTS:
    t = parse_sms(text, sender=sender, received=R)
    if t:
        print(f"READ  {name}: {t.kind} {t.amount} ending={t.ending} when={t.when} place={t.place!r} sure={t.sure}")
    else:
        print(f"NONE  {name}: kept_for_you={looks_like_money(text)} offer={is_offer(text)} prefill={prefill(text)}")
