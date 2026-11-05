"""What a bank's description says (IT-7AC): the payee inside "POS PURCHASE CARREFOUR MAADI 4321XXXX", whether it is
cash taken at an ATM, and a first category for a name seen for the first time. Pure functions, no database; the
statement review shows every result as a suggestion the person confirms or changes."""
from __future__ import annotations

import re

from lightning.bank_import_rows import header_key

# What banks put before the payee: card purchases, transfers, bill payments, cash. Longest first, so "POS PURCHASE"
# goes before "POS". Arabic as Egyptian banks print it.
_PREFIXES = sorted((
    "pos purchase", "pos", "purchase", "card purchase", "debit card purchase", "credit card purchase", "e commerce",
    "ecommerce", "ecom", "online purchase", "instapay trf to", "instapay trf from", "instapay transfer to",
    "instapay transfer from", "instapay", "ipn transfer", "ipn", "trf to", "trf from", "inward trf", "outward trf",
    "inward transfer", "outward transfer", "transfer to", "transfer from", "fawry", "fawry payment", "bill payment",
    "atm withdrawal", "atm cash withdrawal", "cash withdrawal", "مشتريات نقاط البيع", "مشتريات", "شراء", "تحويل وارد",
    "تحويل صادر", "تحويل الي", "تحويل من", "سحب نقدي", "فوري", "دفع فاتوره",
), key=len, reverse=True)
_CITIES = {"cairo", "giza", "alexandria", "alex", "maadi", "nasr city", "heliopolis", "zamalek", "dokki", "mohandessin",
           "new cairo", "6th october", "october", "sheikh zayed", "tagamoa", "eg", "egy", "القاهره", "الجيزه",
           "الاسكندريه"}
_CARD_OR_NUMBER = re.compile(r"(?:\b[0-9]*[xX*]{3,}[0-9]*\b|\b\d{4,}\b|\b0\d{2}x+\w*\b)")
_CASH = re.compile(r"\batm\b|cash withdrawal|سحب نقدي|صراف", re.IGNORECASE)
# E-wallets are accounts too, but not the cash an ATM gives you.
_WALLET_BRANDS = ("vodafone", "etisalat", "orange", "we pay", "fawry", "instapay", "valu", "meeza", "فودافون", "اتصالات")

# A first category by what the name says, by category code; only for a name with no history of its own.
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EXP.PERSONAL.FOOD", ("carrefour", "spinneys", "seoudi", "metro market", "kazyon", "oscar", "gourmet", "hyperone",
                           "lulu", "kheir zaman", "fathalla", "supermarket", "hypermarket", "كارفور", "سعودي", "سوبر ماركت",
                           "خير زمان")),
    ("EXP.PERSONAL.DINING", ("talabat", "elmenus", "mcdonald", "mcdonalds", "kfc", "starbucks", "cilantro", "costa",
                             "pizza", "koshary", "cafe", "restaurant", "طلبات", "مطعم", "كشري")),
    ("EXP.PERSONAL.TRANSPORT", ("uber", "careem", "didi", "indrive", "swvl", "total energies", "totalenergies", "mobil",
                                "chillout", "wataniya", "emarat misr", "fuel", "petrol", "gas station", "بنزين", "وقود")),
    ("EXP.PERSONAL.UTILITIES", ("we internet", "telecom egypt", "vodafone bill", "orange bill", "etisalat bill",
                                "electricity", "water company", "natural gas", "petrotrade", "كهرباء", "مياه", "غاز")),
    ("EXP.PERSONAL.HEALTH", ("pharmacy", "el ezaby", "ezaby", "seif pharmacy", "hospital", "clinic", "alfa lab",
                             "al borg", "صيدليه", "مستشفي", "معمل")),
    ("EXP.PERSONAL.SHOPPING", ("amazon", "noon", "jumia", "ikea", "zara", "decathlon", "defacto", "lc waikiki")),
    ("EXP.PERSONAL.ENTERTAINMENT", ("netflix", "spotify", "shahid", "osn", "watch it", "anghami", "cinema", "vox")),
)
_INCOME_KEYWORDS = (("EXP.WORK.SALARY", ("salary", "payroll", "مرتب", "راتب")),
                    ("EXP.INVEST.INTEREST", ("interest", "credit interest", "فوائد", "عائد")))


def _has_words(text_key: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text_key} "


def clean_name(text: str) -> str:
    """The payee in a bank's description: bank wording, card masks, long numbers and a trailing city taken away.
    "POS PURCHASE CARREFOUR MAADI 4321XXXX" is "Carrefour". Text that would come out empty is kept as written."""
    original = " ".join((text or "").split())
    if is_cash_withdrawal(original):
        return "ATM"  # where the cash went is a transfer to your cash, suggested on its own
    working = _CARD_OR_NUMBER.sub(" ", original)
    working = re.sub(r"[\-–:|/#]+", " ", working)
    words = working.split()
    changed = True
    while changed and words:
        changed = False
        key = header_key(" ".join(words))
        for prefix in _PREFIXES:
            if key == prefix or key.startswith(prefix + " "):
                words = words[len(prefix.split()):]
                changed = True
                break
    while words:  # a trailing city or country, one or two words
        two, one = header_key(" ".join(words[-2:])), header_key(words[-1])
        if len(words) > 2 and two in _CITIES:
            words = words[:-2]
        elif len(words) > 1 and one in _CITIES:
            words = words[:-1]
        else:
            break
    name = " ".join(words).strip()
    if not name or not any(ch.isalpha() for ch in name):
        return original
    if name.isascii() and name.upper() == name:  # CARREFOUR is Carrefour; NBE, CIB, WE and KFC stay as they are
        name = " ".join(word if len(word) <= 3 else word.capitalize() for word in name.split())
    return name


def is_cash_withdrawal(text: str) -> bool:
    return bool(_CASH.search(text or ""))


def is_wallet(name: str) -> bool:
    key = header_key(name)
    return any(_has_words(key, header_key(brand)) or header_key(brand) in key for brand in _WALLET_BRANDS)


def guess_category_code(text: str, money_in: bool) -> str | None:
    """A category code the name points to, or None. Money in is only salary or interest; everything else is spending."""
    key = header_key(text)
    for code, words in (_INCOME_KEYWORDS if money_in else _KEYWORDS):
        if any(_has_words(key, header_key(word)) for word in words):
            return code
    return None


def saved_name_inside(text: str, names: list[str]) -> str | None:
    """The longest saved name found as whole words inside the description ("Carrefour" in "Carrefour Maadi")."""
    key = header_key(text)
    found = [name for name in names if len(header_key(name)) >= 4 and _has_words(key, header_key(name))]
    return max(found, key=lambda name: len(header_key(name))) if found else None
