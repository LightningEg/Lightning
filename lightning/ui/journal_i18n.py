"""Egyptian Arabic strings for the native journal screens.

The normal app owns its translation maps. This small wrapper adds native-journal
copy and falls back to the shared translator without mutating those maps.
"""
import re
from lightning.ui.i18n import translate as _translate


EN = {
    "This signed journal backup opens as a separate review copy. Pair a fresh device to recover saved edits.": "This signed journal backup opens as a separate review copy. Pair a fresh device to recover saved edits.",
    "Create a separate review copy from this backup.": "Create a separate review copy from this backup.",
    "Action": "Action", "Account": "Account", "From account": "From account",
    "To account": "To account", "Category": "Category", "Investment": "Investment",
    "Transaction": "Transaction", "Amount": "Amount", "Date": "Date", "Price": "Price",
    "Quantity": "Quantity", "Fee": "Fee", "Payee": "Payee", "Name": "Name",
    "Details": "Details", "Currency": "Currency", "Account type": "Account type",
    "Institution": "Institution", "Payday": "Payday", "Target": "Target",
    "Selected account": "Selected account",
    "Selected category": "Selected category", "Selected investment": "Selected investment",
    "Selected transaction": "Selected transaction", "{count} selected": "{count} selected",
    "Details provided": "Details provided", "Open account": "Open account",
    "Edit account": "Edit account", "Activate account": "Activate account",
    "Deactivate account": "Deactivate account", "Record transaction": "Record transaction",
    "Record expense": "Record expense", "Record income": "Record income",
    "Record transfer": "Record transfer", "Exchange currency": "Exchange currency",
    "Buy investment": "Buy investment", "Sell investment": "Sell investment",
    "Record investment income": "Record investment income", "Set investment price": "Set investment price",
    "Create investment": "Create investment", "Update investment": "Update investment",
    "Create planned item": "Create planned item", "Edit planned item": "Edit planned item",
    "Pay planned item": "Pay planned item", "Create installment purchase": "Create installment purchase",
    "Record early payment": "Record early payment", "Save budget": "Save budget",
    "Move budget": "Move budget", "Record account reconciliation": "Record account reconciliation",
    "Import bank statement": "Import bank statement", "Confirm bank import": "Confirm bank import",
    "Assign bank account": "Assign bank account", "Review a service action": "Review a service action",
    "Add category": "Add category", "Edit category": "Edit category", "Archive category": "Archive category",
    "Add payee": "Add payee", "Edit payee": "Edit payee", "Create reserve": "Create reserve",
    "Update reserve": "Update reserve", "Allocate reserve": "Allocate reserve", "Complete reserve": "Complete reserve",
    "Create claim": "Create reimbursement claim", "Link receipt": "Link receipt", "Unlink receipt": "Unlink receipt",
    "Save rule": "Save rule", "Apply rule": "Apply rule", "Delete rule": "Delete rule",
    "Set up salary": "Set up salary", "Apply activity review": "Apply activity review",
    "Record deposit purchase": "Record deposit purchase", "Edit deposit terms": "Edit deposit terms",
    "Redeem deposit": "Redeem deposit", "Record gameya installment": "Record gameya installment",
    "Add physical item": "Add physical item", "Record item value": "Record item value",
    "Record item trade": "Record item trade", "Set target": "Set investment target",
    "Set budget carryover": "Set budget carryover", "Apply budget fill": "Apply budget fill",
    "Set currency": "Set profile currency", "Set exchange rate": "Set exchange rate",
    "Update account settings": "Update account settings", "Reconcile account": "Reconcile account",
    "Match bill payment": "Match bill payment", "Dismiss bank message": "Dismiss bank message",
    "Waiting for the home": "Waiting for the home", "The home needs to review this action": "The home needs to review this action",
    "The home could not apply this action": "The home could not apply this action",
    "Applied on the home": "Applied on the home", "The home kept the confirmed value": "The home kept the confirmed value",
    "An earlier action was not taken": "An earlier action was not taken",
    "Pending": "Waiting for the home", "Needs review": "Needs review", "Confirmed": "Confirmed",
    "Not taken": "Not taken", "Yes": "Yes", "No": "No",
}

AR = {
    "Pairing was interrupted. Resume to check its saved state.": "الربط اتقطع. كمّل عشان نراجع الحالة المحفوظة.",
    "Resume pairing": "كمّل الربط",
    "On your other device, select this device from Nearby devices.": "على الجهاز التاني، اختار الجهاز ده من الأجهزة القريبة.",
    "Select this number on your other device, then approve here.": "اختار الرقم ده على الجهاز التاني، وبعدها وافق هنا.",
    "Waiting for the other device to enter the profile password.": "مستنيين الجهاز التاني يدخل كلمة سر الملف.",
    "Approve this device": "وافق على الجهاز ده",
    "Select the number shown on the other device.": "اختار الرقم اللي ظاهر على الجهاز التاني.",
    "The number did not match. Stop pairing on the home, then cancel here and start again.": "الرقم مش مطابق. أوقف الربط على الجهاز الأساسي، وبعدها الغيه هنا وابدأ تاني.",
    "Searching automatically. Open pairing on your other device and use the same Wi-Fi.": "بندوّر تلقائي. افتح الربط على الجهاز التاني واستخدم نفس شبكة الواي فاي.",
    "Cancel this pairing": "إلغاء الربط ده",

    "This signed journal backup opens as a separate review copy. Pair a fresh device to recover saved edits.": "النسخة الاحتياطية الموقّعة دي بتتفتح كنسخة منفصلة للمراجعة. اربط جهاز جديد عشان تسترجع التعديلات المحفوظة.",
    "Create a separate review copy from this backup.": "اعمل نسخة منفصلة للمراجعة من النسخة الاحتياطية دي.",
    "Action": "الإجراء", "Account": "الحساب", "From account": "من حساب",
    "To account": "إلى حساب", "Category": "الفئة", "Investment": "الاستثمار",
    "Transaction": "المعاملة", "Amount": "المبلغ", "Date": "التاريخ", "Price": "السعر",
    "Quantity": "الكمية", "Fee": "الرسوم", "Payee": "الجهة", "Name": "الاسم",
    "Details": "التفاصيل", "Currency": "العملة", "Account type": "نوع الحساب",
    "Institution": "البنك", "Payday": "يوم القبض", "Target": "الهدف",
    "Selected account": "حساب محدد",
    "Selected category": "فئة محددة", "Selected investment": "استثمار محدد",
    "Selected transaction": "معاملة محددة", "{count} selected": "تم اختيار {count}",
    "Details provided": "تم إدخال التفاصيل", "Open account": "فتح حساب",
    "Edit account": "تعديل حساب", "Activate account": "تفعيل حساب",
    "Deactivate account": "إيقاف حساب", "Record transaction": "تسجيل معاملة",
    "Record expense": "تسجيل مصروف", "Record income": "تسجيل دخل",
    "Record transfer": "تسجيل تحويل", "Exchange currency": "تبديل عملة",
    "Buy investment": "شراء استثمار", "Sell investment": "بيع استثمار",
    "Record investment income": "تسجيل عائد استثمار", "Set investment price": "تسجيل سعر استثمار",
    "Create investment": "إضافة استثمار", "Update investment": "تعديل استثمار",
    "Create planned item": "إضافة بند مخطط", "Edit planned item": "تعديل بند مخطط",
    "Pay planned item": "سداد بند مخطط", "Create installment purchase": "إضافة شراء بالتقسيط",
    "Record early payment": "تسجيل سداد مبكر", "Save budget": "حفظ الميزانية",
    "Move budget": "نقل مبلغ في الميزانية", "Record account reconciliation": "تسجيل مطابقة الحساب",
    "Import bank statement": "استيراد كشف حساب", "Confirm bank import": "تأكيد استيراد كشف الحساب",
    "Assign bank account": "ربط الرسالة بحساب بنكي", "Review a service action": "مراجعة إجراء",
    "Add category": "إضافة فئة", "Edit category": "تعديل فئة", "Archive category": "أرشفة فئة",
    "Add payee": "إضافة جهة", "Edit payee": "تعديل جهة", "Create reserve": "إضافة هدف ادخار",
    "Update reserve": "تعديل هدف ادخار", "Allocate reserve": "تخصيص مبلغ للهدف", "Complete reserve": "إنهاء هدف الادخار",
    "Create claim": "إضافة مطالبة استرداد", "Link receipt": "ربط إيصال", "Unlink receipt": "فك ربط الإيصال",
    "Save rule": "حفظ قاعدة", "Apply rule": "تطبيق قاعدة", "Delete rule": "حذف قاعدة",
    "Set up salary": "إعداد الراتب", "Apply activity review": "تطبيق تصنيف المعاملة",
    "Record deposit purchase": "تسجيل شراء شهادة", "Edit deposit terms": "تعديل شروط الشهادة",
    "Redeem deposit": "استرداد الشهادة", "Record gameya installment": "تسجيل قسط الجمعية",
    "Add physical item": "إضافة مقتنى", "Record item value": "تسجيل قيمة المقتنى",
    "Record item trade": "تسجيل بيع أو شراء مقتنى", "Set target": "تحديد هدف الاستثمار",
    "Set budget carryover": "تعديل ترحيل الميزانية", "Apply budget fill": "تطبيق تعبئة الميزانية",
    "Set currency": "تغيير عملة الملف", "Set exchange rate": "تسجيل سعر الصرف",
    "Update account settings": "تعديل إعدادات الحساب", "Reconcile account": "مطابقة الحساب",
    "Match bill payment": "ربط دفعة بفاتورة", "Dismiss bank message": "تجاهل رسالة البنك",
    "Waiting for the home": "مستنيين الجهاز الأساسي", "The home needs to review this action": "الجهاز الأساسي محتاج يراجع الإجراء",
    "The home could not apply this action": "الجهاز الأساسي ماقدرش يطبق الإجراء",
    "Applied on the home": "اتطبق على الجهاز الأساسي", "The home kept the confirmed value": "الجهاز الأساسي احتفظ بالقيمة الحالية",
    "An earlier action was not taken": "الإجراء السابق ما اتنفذش",
    "Pending": "مستنيين الجهاز الأساسي", "Needs review": "محتاج مراجعة", "Confirmed": "اتأكد",
    "Not taken": "ما اتنفذش", "Yes": "نعم", "No": "لا",
}

COMMAND_NAMES = {
    "accounts.open": "Open account",
    "account_flows.update_account": "Edit account",
    "account_flows.deactivate": "Deactivate account",
    "account_flows.reactivate": "Activate account",
    "transactions.record_in_account": "Record transaction",
    "transactions.update_in_account": "Record transaction",
    "transactions.record_outflow": "Record expense",
    "transactions.record_inflow": "Record income",
    "transactions.record_transfer": "Record transfer",
    "transactions.record_conversion": "Exchange currency",
    "investments.buy": "Buy investment", "investments.buy_total": "Buy investment",
    "investments.buy_converting": "Buy investment", "investments.sell": "Sell investment",
    "investments.sell_total": "Sell investment", "investments.dividend": "Record investment income",
    "assets.set_price": "Set investment price", "assets.set_prices": "Set investment price",
    "assets.create_investment": "Create investment", "assets.update_investment": "Update investment",
    "planning.create_purchase": "Create installment purchase",
    "planning.record_early_payment": "Record early payment",
    "planning.create": "Create planned item", "planning.update": "Edit planned item",
    "planning.record_payment": "Pay planned item", "planning.mark_paid": "Pay planned item",
    "budgets.set_budget": "Save budget", "budgets.move_room": "Move budget",
    "reconciliation.close": "Record account reconciliation",
    "bank_imports.stage": "Import bank statement", "bank_imports.confirm": "Confirm bank import",
    "bank_imports.stage_chunked": "Import bank statement", "bank_imports.confirm_packed": "Confirm bank import",
    "sms_imports.assign": "Assign bank account",
    "activity_review.apply": "Apply activity review", "salary_setup.set_up_salary": "Set up salary",
    "categories.create": "Add category", "categories.update": "Edit category",
    "categories.delete_or_archive": "Archive category", "counterparties.ensure_person": "Add payee",
    "counterparties.rename": "Edit payee", "reserves.create": "Create reserve",
    "reserves.update": "Update reserve", "reserves.allocate": "Allocate reserve",
    "reserves.complete": "Complete reserve", "reimbursements.create_claim": "Create claim",
    "reimbursements.link_receipt": "Link receipt", "reimbursements.unlink_receipt": "Unlink receipt",
    "rules.save": "Save rule", "rules.apply_past": "Apply rule", "rules.delete": "Delete rule",
    "deposits.purchase": "Record deposit purchase", "deposits.save": "Edit deposit terms",
    "deposits.update_certificate": "Edit deposit terms", "deposits.redeem": "Redeem deposit",
    "physical.create": "Add physical item", "physical.record_valuation": "Record item value",
    "physical.record_trade_details": "Record item trade", "investments.set_target": "Set target",
    "budgets.set": "Save budget", "budgets.set_budget": "Save budget",
    "budgets.set_carryover": "Set budget carryover", "budgets.apply_fill": "Apply budget fill",
    "currencies.register": "Set currency", "fx.save": "Set exchange rate",
    "reconciliation.close": "Reconcile account", "planning.match_payments": "Match bill payment",
    "sms_imports.dismiss": "Dismiss bank message",
}

FIELD_NAMES = {
    "account_id": "Account", "from_account_id": "From account", "to_account_id": "To account",
    "cash_account_id": "From account", "destination_account_id": "To account",
    "funding_account_id": "From account", "other_account_id": "To account",
    "category_id": "Category", "asset_id": "Investment", "reference_asset_id": "Investment",
    "transaction_id": "Transaction", "txn_id": "Transaction", "amount": "Amount",
    "date": "Date", "date_value": "Date", "day": "Date", "price": "Price",
    "quantity": "Quantity", "fees": "Fee", "fee": "Fee", "name": "Name",
    "counterparty": "Payee", "counterparty_id": "Payee", "notes": "Details",
    "currency": "Currency", "account_type": "Account type", "institution": "Institution",
    "payday": "Payday", "target": "Target", "opening_balance": "Amount",
    "opening_date": "Date", "start_date": "Date", "due_date": "Date",
}


def action_name(command: str) -> str:
    return COMMAND_NAMES.get(command, command.rsplit(".", 1)[-1].replace("_", " ").capitalize())


def translate_journal(value, locale="en", **values):
    text = str(value)
    if locale == "ar":
        selected = re.fullmatch(r"(\d+) selected", text)
        if selected:
            return f"تم اختيار {selected.group(1)}"
    if locale == "ar" and text in AR:
        text = AR[text]
    elif text in EN:
        text = EN[text]
    if values:
        try:
            text = text.format(**values)
        except (KeyError, ValueError):
            pass
    return text if text != str(value) or locale == "en" else _translate(value, locale, **values)
