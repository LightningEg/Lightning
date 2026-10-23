"""Reproduce Audit 4 on disposable dummy ledgers; never opens profile data.

Run from any directory: python /path/to/Lightning/reports/audit-4/reproduce.py
The displayed balances document observed defects, not desired regression expectations.
Requires the app dependencies and httpx, but does not need pytest, SQLCipher or a server.
"""
import os, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from decimal import Decimal as D
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['LIGHTNING_PRICES_OFFLINE']='1'
os.environ['LIGHTNING_TODAY']='2026-10-23'
from lightning.bootstrap import build
from lightning.core.errors import LightningError
from lightning.core.ledger import PostingLine, Effect
from lightning.core.refs import DocType

def case(name, f):
 with TemporaryDirectory() as d:
  c=build(Path(d)/'dummy.db')
  a=c.account_flows.open_account('Bank A','BANK','2026-09-01','100')
  b=c.account_flows.open_account('Bank B','BANK','2026-09-01','0')
  food=c.categories.get_by_code('EXP.PERSONAL.FOOD').id
  salary=c.categories.get_by_code('EXP.WORK.SALARY').id
  try: print(name, f(c,a,b,food,salary))
  except Exception as e: raise RuntimeError(f'Probe failed unexpectedly: {name}') from e
  finally: c.db.close()

def balance(c,a): return c.reporting.account_balance(a.id,'2026-10-23')

def moved_income(c,a,b,food,salary):
 t=c.transactions.record_inflow('2026-09-02',a.id,'100',salary)
 c.transactions.record_outflow('2026-09-03',a.id,'150',food)
 c.transactions.update_money(t.id,'2026-09-02',b.id,'100',salary)
 return {'old_account':str(balance(c,a)),'new_account':str(balance(c,b))}
case('move funding income to another account', moved_income)

def deleted_income(c,a,b,food,salary):
 t=c.transactions.record_inflow('2026-09-02',a.id,'100',salary)
 c.transactions.record_outflow('2026-09-03',a.id,'150',food)
 c.transactions.delete_many([t.id])
 return {'balance':str(balance(c,a))}
case('delete funding income', deleted_income)

def restored_expense(c,a,b,food,salary):
 t=c.transactions.record_outflow('2026-09-02',a.id,'80',food)
 c.transactions.void(t.id)
 c.transactions.record_outflow('2026-09-03',a.id,'70',food)
 c.transactions.restore(t.id)
 return {'balance':str(balance(c,a))}
case('restore expense after spending released cash', restored_expense)

def brokerage_restore(c,a,b,food,salary):
 broker=c.account_flows.open_account('Broker','BROKERAGE','2026-09-01','100')
 asset=c.assets.create_investment('Test share','STOCK','TEST')
 t=c.investments.buy('2026-09-02',broker.id,asset.id,'1','80')
 c.transactions.void(t.id)
 c.investments.buy('2026-09-03',broker.id,asset.id,'1','70')
 c.transactions.restore(t.id)
 return {'broker_cash':str(balance(c,broker)), 'units':str(c.investments.holding(broker.id,asset.id,'2026-10-23'))}
case('restore brokerage purchase without funding', brokerage_restore)

def currency_mismatch(c,a,b,food,salary):
 cash=c.assets.cash_asset('USD')
 t=c.transactions.post(DocType.IN,'2026-09-02',[PostingLine.cash(a.id,cash.id,D(10),Effect.INFLOW,salary,fx_rate=D(50))])
 return {'account_currency':a.currency, 'asset_currency':cash.currency, 'balance':str(balance(c,a)), 'value':str(c.reporting.account_value(a.id,'2026-09-02'))}
case('generic posting USD cash into EGP bank', currency_mismatch)

def double_create(c,a,b,food,salary):
 for _ in range(2): c.transactions.record_outflow('2026-09-02',a.id,'10',food,notes='same submit')
 return {'balance':str(balance(c,a)), 'expense_count':c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'")}
case('repeat identical expense', double_create)

def rounding(c,a,b,food,salary):
 cash=c.assets.cash_asset('EGP')
 line=PostingLine.cash(a.id,cash.id,D('0.01'),Effect.INFLOW,salary,fx_rate=D('0.5'))
 t=c.transactions.post(DocType.IN,'2026-09-02',[line])
 return {'native':str(t.lines[0].amount),'base':str(t.lines[0].amount_base),'fx':str(t.lines[0].fx_rate)}
case('generic posting bad EGP base rate', rounding)

def owner_edit(c,a,b,food,salary):
 broker=c.account_flows.open_account('Broker','BROKERAGE','2026-09-01','200')
 other=c.counterparties.create('Other owner')
 c.transactions.record_inflow('2026-09-01',broker.id,'200',salary,owner_id=other)
 asset=c.assets.create_investment('Test share','STOCK','TEST')
 t=c.investments.buy('2026-09-02',broker.id,asset.id,'1','50',owner_id=other)
 c.investments.buy('2026-09-02',broker.id,asset.id,'1','50')
 c.investments.sell('2026-09-03',broker.id,asset.id,'1','50',owner_id=other)
 c.investments.update(t.id,account_id=broker.id,asset_id=asset.id,quantity='1',price='50',owner_id=None)
 return {'other_owner_units':str(c.investments.holding_for_owner(broker.id,asset.id,'2026-10-23',other)),
         'my_units':str(c.investments.holding_for_owner(broker.id,asset.id,'2026-10-23'))}
case('reassign a purchase that funds another owners sale',owner_edit)

def unfunded_conversion(c,a,b,food,salary):
 broker=c.account_flows.open_account('Broker','BROKERAGE','2026-09-01','0')
 c.currencies.register('USD')
 usd=c.account_flows.open_account('Dollars','BANK','2026-09-01','0',currency='USD')
 c.transactions.record_conversion('2026-09-02',broker.id,usd.id,'500','10')
 return {'broker_cash':str(balance(c,broker)), 'received':str(balance(c,usd))}
case('convert unfunded brokerage cash',unfunded_conversion)

def failed_converting_buy(c,a,b,food,salary):
 broker=c.account_flows.open_account('Broker','BROKERAGE','2026-09-01','0')
 asset=c.assets.create_investment('US share','STOCK','USTEST',currency='USD',mic='XNAS')
 before=c.db.scalar('SELECT COUNT(*) FROM accounts')
 try: c.investments.buy_converting('2026-09-02',broker.id,asset.id,'0','10','500')
 except LightningError as e: failure=type(e).__name__
 return {'failure':failure,'accounts_before':before,'accounts_after':c.db.scalar('SELECT COUNT(*) FROM accounts')}
case('failed converting buy leaves an empty pocket',failed_converting_buy)

def price_decimals(c,a,b,food,salary):
 ident=c.planning.create_purchase(name='Device',price='100.001',fee='0',months='2',first_date='2026-09-02',account_id=a.id)
 item=c.planning.get(ident)
 return {'principal':str(item.principal),'terms':[dict(x) for x in c.db.all('SELECT * FROM installment_purchases')]}
case('purchase loan accepts sub-cent price',price_decimals)


def opening_reduction(c,a,b,food,salary):
 c.transactions.record_outflow('2026-09-02',a.id,'80',food)
 c.account_flows.update_account(a.id,a.name,'BANK',a.opening_date,'10')
 return {'balance':str(balance(c,a))}
case('reduce opening balance below later spending', opening_reduction)


def http_double_submit(c,a,b,food,salary):
 import asyncio
 import httpx
 from lightning.ui.web import create_app
 async def run():
  form=dict(date='2026-09-02', amount='-10', category_choice=str(food),
            counterparty='', notes='same browser submit')
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(c)),
                              base_url='http://testserver') as client:
   return [(await client.post(f'/accounts/{a.id}/register',data=form)).status_code for _ in range(2)]
 statuses=asyncio.run(run())
 return {'http_statuses':statuses,'balance':str(balance(c,a)),
         'expense_count':c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'")}
case('same HTTP register form twice', http_double_submit)


def unpayable_instalment(c,a,b,food,salary):
 from datetime import date
 ident=c.planning.create_purchase(name='Device',price='100.001',fee='0',months=2,
                                  first_date='2026-09-02',account_id=a.id)
 c.planning.update(ident,kind='LOAN',name='Device',amount='50.01',frequency='MONTHLY',
                   payment_count=2,start_date='2026-09-02',account_id=a.id,
                   category_id=food,principal='100.001')
 payments=c.planning.payments(c.planning.get(ident),'2026-10-23',date(2026,10,23))
 last=payments[-1]
 try:
  c.planning.record_payment(ident,last.due_date,'2026-10-23',last.amount,a.id)
 except LightningError as e:
  return {'instalments':[str(p.amount) for p in payments], 'payment_error':str(e)}
 raise AssertionError('Expected sub-cent final payment to be refused at the audited commit')
case('loan generates a final instalment it refuses to post',unpayable_instalment)


def healthy_demo():
 from datetime import date
 from lightning.demo import build_demo
 with TemporaryDirectory() as d:
  c=build(Path(d)/'demo.db')
  try:
   build_demo(c,date(2026,10,23))
   checks=c.integrity.checks('2026-10-23')
   assert all(x.status=='PASS' for x in checks), checks
   unbalanced=c.db.all("SELECT transaction_id FROM ledger_entries WHERE effect='INTERNAL' "
                       "GROUP BY transaction_id HAVING SUM(amount_base_e6)<>0")
   assert not unbalanced
   assert not c.db.all('PRAGMA foreign_key_check')
   assert c.db.scalar('PRAGMA integrity_check')=='ok'
   print('healthy demo', {'integrity_checks_passed':len(checks), 'posted_transactions':
         c.db.scalar("SELECT COUNT(*) FROM transactions WHERE status='POSTED'"),
         'unbalanced_internal_movements':len(unbalanced), 'sqlite_integrity':'ok'})
  finally:
   c.db.close()
healthy_demo()


def valid_controls(c,a,b,food,salary):
 from lightning.core.errors import ValidationError
 before=balance(c,a)
 for amount in ('0','-1','1.001','101','NaN','1000000000000'):
  try:
   c.transactions.record_outflow('2026-09-02',a.id,amount,food)
  except ValidationError:
   pass
  else:
   raise AssertionError(f'Bad input accepted: {amount}')
 assert balance(c,a)==before
 c.transactions.record_transfer('2026-09-02',a.id,b.id,'20')
 assert balance(c,a)+balance(c,b)==before
 txn=c.transactions.record_outflow('2026-09-03',a.id,'10',food)
 assert balance(c,a)==D('70')
 c.transactions.void(txn.id)
 assert balance(c,a)==D('80')
 c.transactions.restore(txn.id)
 assert balance(c,a)==D('70')
 try:
  with c.db.transaction():
   c.transactions.record_outflow('2026-09-04',a.id,'5',food)
   raise RuntimeError('simulated workflow failure')
 except RuntimeError:
  pass
 assert balance(c,a)==D('70')
 return {'bad_inputs_refused':6,'transfer_conserves_cash':True,
         'ordinary_void_restore':True,'nested_workflow_rollback':True}
case('healthy write controls',valid_controls)
