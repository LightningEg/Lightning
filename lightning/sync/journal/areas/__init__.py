"""Journal areas: each module lists its synchronized tables and its commands.

Add an area by writing its module and naming it here. A service action that
writes any table outside every enabled area's TABLES is refused by the home.
"""
from . import automation, cash, currency, deposits, history, household, imports, investments, master, people, physical, plans, rules, settings, sms, workflows

AREAS = (cash, currency, master, people, plans, settings, investments, deposits, physical, imports, household, rules,
         sms, automation, history, workflows)
