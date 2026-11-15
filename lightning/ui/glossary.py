"""The in-app glossary (Settings › Glossary): Lightning's own words, each in a sentence or two a person can use.

Names come from the figures table (core/figures.py), so a term is never spelled one way here and another on a screen;
the meanings are written for people, not copied from the formulas (ai/GLOSSARY.md keeps those). Each entry says where
it is read on the screen, and has its Egyptian Arabic beside it."""
from __future__ import annotations

from dataclasses import dataclass

from lightning.core.figures import FIGURES


@dataclass(frozen=True)
class Term:
    key: str
    name: str
    name_ar: str
    meaning: str
    meaning_ar: str
    where: str = ""
    where_ar: str = ""


def _name(key: str) -> str:
    return FIGURES[key].label


# (figure key or None, English name, Arabic name, meaning, Arabic meaning, where, Arabic where)
_ROWS = (
    ("free_cash", None, "النقدية المتاحة",
     "Cash you can spend without touching your reserves and without leaving a bill unpaid.",
     "الفلوس اللي تقدر تصرفها من غير ما تلمس احتياطيك ومن غير ما تسيب فاتورة من غير دفع.",
     "Overview, Cash planning", "النظرة العامة، تخطيط النقدية"),
    ("safe_to_spend", None, "الآمن للصرف",
     "Free cash after everything already promised until your next pay: bills, what is left of your budget, goals and "
     "your emergency fund top-up. It is an estimate. If it is below zero, more is promised than you have free.",
     "النقدية المتاحة بعد كل اللي وعدت بيه لحد المرتب الجاي: الفواتير وباقي الميزانية والأهداف وتكملة صندوق الطوارئ. "
     "تقدير مش رقم نهائي. لو أقل من صفر يبقى الملتزم بيه أكتر من المتاح.",
     "Overview, Cash planning", "النظرة العامة، تخطيط النقدية"),
    ("left_in_plan", None, "المتبقي في الخطة",
     "What is left of this month's plan: planned spending minus what you have spent. Refunds reduce what you spent.",
     "اللي فاضل من خطة الشهر: المخطط ناقص اللي صرفته. الاسترداد بيقلل المصروف.",
     "Overview, Budget", "النظرة العامة، الميزانية"),
    ("savings_rate", None, "معدل الادخار",
     "The share of the money that came in that you kept. When refunds are bigger than your spending, or you spend "
     "more than twice what came in, a percentage says nothing, so Lightning says the gap in words.",
     "نسبة اللي دخل وفضل معاك. لو الاسترداد أكبر من المصروف أو صرفت أكتر من ضعف اللي دخل، النسبة ما بتقولش حاجة، "
     "فبنقولها بالكلام.",
     "Overview", "النظرة العامة"),
    ("investing_rate", None, "معدل الاستثمار",
     "The share of what you kept that you moved into investments. It is never more than 100%.",
     "نسبة اللي فضل معاك وحطيته في استثمارات. عمره ما بيعدي 100%.",
     "Overview", "النظرة العامة"),
    ("money_in", None, "الداخل",
     "Income that was recorded in the period. Moves between your own accounts and money held for others do not count.",
     "الدخل المسجل في الفترة. التحويل بين حساباتك والفلوس اللي معاك لغيرك مش بيتحسبوا.",
     "Spending, Overview", "المصروفات، النظرة العامة"),
    ("money_out", None, "الخارج",
     "Spending recorded in the period, after refunds. If refunds were bigger than spending it can read below zero.",
     "المصروف المسجل في الفترة بعد الاسترداد. لو الاسترداد أكبر من المصروف ممكن يظهر أقل من صفر.",
     "Spending, Overview", "المصروفات، النظرة العامة"),
    ("net_flow", None, "صافي الحركة",
     "What was left of the money that came in after the money that went out.",
     "اللي فضل من الداخل بعد الخارج.",
     "Overview, Spending", "النظرة العامة، المصروفات"),
    ("what_you_own", None, "ما تملكه",
     "The value of everything in your accounts that is yours: cash, investments and other things you own.",
     "قيمة كل اللي في حساباتك وهو بتاعك: النقدية والاستثمارات وأي حاجة تانية بتملكها.",
     "Overview", "النظرة العامة"),
    ("what_you_owe", None, "ما عليك",
     "Payments you are certain to make: bills already due, loans still to pay and what you owe a gam'eya.",
     "المدفوعات اللي أكيد هتدفعها: الفواتير المستحقة والقروض المتبقية وباقي الجمعية.",
     "Overview, Cash planning", "النظرة العامة، تخطيط النقدية"),
    ("bills_due", "Bills due now", "فواتير مستحقة دلوقتي",
     "Bills and subscriptions dated today or earlier that nothing has paid yet. Loan payments that are due are "
     "counted in Loans still to pay instead, so the same payment is never counted twice.",
     "فواتير واشتراكات تاريخها النهارده أو قبل ومحدش دفعها. أقساط القروض المستحقة بتتحسب في القروض المتبقية، "
     "فالقسط مش بيتعد مرتين.",
     "Cash planning", "تخطيط النقدية"),
    ("kept_apart", None, "محجوز على جنب",
     "Cash you own that is not ready to spend: cash in a brokerage, in another currency, or in an account you set apart. "
     "It stays in what you own.",
     "نقدية بتملكها بس مش جاهزة للصرف: في شركة سمسرة أو بعملة تانية أو في حساب حجزته. بتفضل جزء من ما تملكه.",
     "Overview", "النظرة العامة"),
    ("reserves", None, "الاحتياطي",
     "Cash you set aside for emergencies and for goals with a date. It stays in your accounts and in what you own, "
     "but it is not free to spend.",
     "نقدية حاطها على جنب للطوارئ وللأهداف اللي ليها ميعاد. بتفضل في حساباتك وفي ما تملكه، بس مش متاحة للصرف.",
     "Cash planning, Safety", "تخطيط النقدية، الأمان"),
    ("payments_before_next_income", None, "مستحق قبل المرتب",
     "Bills, subscriptions and loan payments that are not due yet but fall before your next income.",
     "فواتير واشتراكات وأقساط لسه ميعادها ما جاش بس هتيجي قبل الدخل الجاي.",
     "Cash planning", "تخطيط النقدية"),
    ("if_you_sold_today", None, "لو بعت النهارده",
     "An estimate of your free cash plus what your investments might fetch if you sold them now, after the sale factors "
     "you set.",
     "تقدير للنقدية المتاحة زائد اللي استثماراتك ممكن تجيبه لو بعتها دلوقتي، بعد معاملات البيع اللي حطيتها.",
     "Overview, Investments", "النظرة العامة، الاستثمارات"),
    ("held_for_others", None, "فلوس لغيرك",
     "Money and units in your accounts that belong to other people. They are never counted as yours.",
     "فلوس ووحدات في حساباتك بتاعة ناس تانية. عمرها ما بتتحسب بتاعتك.",
     "Accounts", "الحسابات"),
    ("net_worth", None, "صافي الثروة",
     "What you own after what you owe.",
     "اللي بتملكه بعد اللي عليك.",
     "Overview", "النظرة العامة"),
)

# Words that are not a reported figure (no row in the figures table).
_PLAIN = (
    ("Needs you", "محتاجك",
     "The short list of things that want a decision today: a late bill, salary that has not come, a forecast that runs "
     "short. Each row says what to do.",
     "قايمة قصيرة بالحاجات اللي محتاجة قرار النهارده: فاتورة متأخرة أو مرتب ما جاش أو توقع إن النقدية هتنقص.",
     "Overview", "النظرة العامة"),
    ("Payday", "يوم المرتب",
     "The day your salary usually arrives. Lightning plans from it: what is safe to spend runs until the next one.",
     "اليوم اللي مرتبك بيجي فيه عادةً. Lightning بيخطط منه: الآمن للصرف بيمتد لحد اللي بعده.",
     "Cash planning", "تخطيط النقدية"),
    ("Emergency fund", "صندوق الطوارئ",
     "Money set aside to cover months of your spending if income stops. It is a reserve, so it is not part of free cash.",
     "فلوس محجوزة تغطي شهور من مصروفاتك لو الدخل وقف. ده احتياطي، فمش جزء من النقدية المتاحة.",
     "Safety", "الأمان"),
    ("Plan", "الخطة",
     "What you intend: budgets, bills, loans and goals. A plan moves no money; only a recorded transaction does.",
     "اللي ناوي عليه: الميزانيات والفواتير والقروض والأهداف. الخطة ما بتحركش فلوس، المعاملة المسجلة بس هي اللي بتحرك.",
     "Budget, Cash planning", "الميزانية، تخطيط النقدية"),
    ("Gam'eya", "الجمعية",
     "A savings circle with friends or coworkers. Each instalment and your payout are moves of money, never income "
     "or spending.",
     "دايرة ادخار مع أصحاب أو زمايل. كل قسط وقبضك تحويلات فلوس، مش دخل ولا مصروف.",
     "Cash planning", "تخطيط النقدية"),
)


def glossary_terms() -> list[Term]:
    """Every term in the order a person meets them: figures first, then the plain words."""
    out = [Term(key, name or _name(key), ar, meaning, meaning_ar, where, where_ar)
           for key, name, ar, meaning, meaning_ar, where, where_ar in _ROWS]
    out.extend(Term(name.casefold().replace(" ", "_").replace("'", ""), name, ar, meaning, meaning_ar, where, where_ar)
               for name, ar, meaning, meaning_ar, where, where_ar in _PLAIN)
    return out
