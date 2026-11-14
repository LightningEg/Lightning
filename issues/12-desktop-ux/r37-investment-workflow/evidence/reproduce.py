"""Run from repo root: python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py
Disposable database; fixed 2026-11-14 date; offline prices; observed vs expected printed.
"""
import os,sys,json,tempfile
from pathlib import Path
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0,str(ROOT))
os.environ['LIGHTNING_TODAY']='2026-11-14'; os.environ['LIGHTNING_PRICES_OFFLINE']='1'
from lightning.bootstrap import build
from lightning.ui.web import create_app
from lightning.workflows.investment_entry import FIELDS,record
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
from decimal import Decimal as D
with tempfile.TemporaryDirectory() as tmp:
 c=build(Path(tmp)/'audit.db'); client=TestClient(create_app(c),follow_redirects=False)
 bank=c.account_flows.open_account('Audit bank','BANK','2026-01-01','1000000')
 broker=c.account_flows.open_account('Audit broker','BROKERAGE','2026-01-01','10000',currency='EGP')
 from lightning.database.currencies import CurrencyRegistry
 CurrencyRegistry(c.db).register('USD')
 c.fx.save('USD','2026-11-01','50')
 usd=c.account_flows.open_account('Audit dollar broker','BROKERAGE','2026-11-01','10000',currency='USD')
 asset=c.assets.create_investment('Audit US stock','STOCK','AUDT',mic='XNAS',currency='USD')
 html=client.get(f'/investments/new?kind=buy&account={usd.id}&asset={asset.id}').text
 print('USD FORM LABELS',BeautifulSoup(html,'html.parser').get_text(' ',strip=True)[-3200:])
 r=client.post('/investments/new?kind=buy',data={'date':'2026-11-02','account_id':usd.id,'asset_id':asset.id,'quantity':'10','total':'100','fees':'0'})
 print('USD BUY',r.status_code,'USD cash after amount labelled EGP=100',c.reporting.account_balance(usd.id,'2026-11-02'))
 pos=c.investments.portfolio('2026-11-02',usd.id).open[0]
 from lightning.investments.views import purchase_returns
 print('USD LOT RETURNS',purchase_returns(pos,'2026-11-02'))
 print('USD holding cost EGP',pos.cost_basis,'expected if EGP label followed',100)
 fund=c.assets.create_investment('Audit fund','FUND.MONEY_MARKET','AUDF')
 c.investments.buy('2026-11-01',broker.id,fund.id,'100','10')
 v=dict.fromkeys(FIELDS,''); v.update({'date':'2026-11-02','instrument_key':f'asset:{fund.id}','trade_action':'sell','total':'100','unit_price':'10','fees':'10','fees_included':'1','is_others':False})
 txn=record(c,broker,v)
 print('SELL BY NET AMOUNT',[(str(l.quantity),str(l.amount_base)) for l in txn.lines],'expected units -11, cash +100 for 10/unit and fee 10')
 cdacc=c.account_flows.open_account('Audit CD','DEPOSIT','2026-01-01','0',institution='Audit')
 cert,_=c.deposits.purchase(cdacc.id,'Audit certificate','2026-01-01','2026-07-01','2027-01-01','1000','12','SIMPLE','MONTHLY','MONTHLY',bank.id,bank.id)
 cdasset=cert.terms.asset_id
 for kind in ['buy','sell','dividend']:
  form=client.get(f'/investments/new?kind={kind}&account={cdacc.id}&asset={cdasset}').text
  soup=BeautifulSoup(form,'html.parser'); sel=soup.select_one('[name=account_id]')
  print('CD action',kind,'account selectable',bool(sel.select(f'option[value="{cdacc.id}"]')))
  r=client.post(f'/investments/new?kind={kind}',data={'date':'2026-11-02','account_id':cdacc.id,'asset_id':cdasset,'quantity':'1','total':'1000','amount':'10','fees':'0','cash_account_id':bank.id})
  print('CD POST',kind,r.status_code,BeautifulSoup(r.text,'html.parser').select_one('.error'))
 second=c.account_flows.open_account('Second broker','BROKERAGE','2026-01-01','10000')
 c.investments.buy('2026-11-03',second.id,fund.id,'50','10')
 before=[(p.account_id,str(p.quantity),str(p.value)) for p in c.investments.portfolio('2026-11-04').open if p.asset_id==fund.id]
 r=client.post('/investments/prices',data={'date':'2026-11-04',f'value_{fund.id}':'1500'})
 after=[(p.account_id,str(p.quantity),str(p.value)) for p in c.investments.portfolio('2026-11-04').open if p.asset_id==fund.id]
 print('MULTI-BROKER TOTAL PRICE',before,'entered 1500',r.status_code,after)
 gold=c.account_flows.open_account('Audit gold','PHYSICAL_ASSET','2026-01-01','0')
 ref=next(a for a in c.assets.investments() if a.code.startswith('REF:') and a.purity==D(1))
 c.assets.set_price(ref.id,'2026-11-01','5000')
 item=c.physical_items.create(gold.id,'Audit ring','Jewelry','10',24,ref.id)
 c.investments.add_holding(gold.id,item,'1','45000','2026-11-01')
 before=c.reporting.value_of(item,D(1),'2026-11-04').value
 r=client.post('/investments/prices',data={'date':'2026-11-04',f'value_{item}':'60000'})
 print('GOLD GENERAL PRICE',before,'entered 60000',r.status_code,'after',c.reporting.value_of(item,D(1),'2026-11-04').value)
 # Explicit certificate price entry must not override contractual principal.
 r=client.post('/investments/prices',data={'date':'2026-11-04',f'value_{cdasset}':'2000'})
 print('CD TOTAL PRICE',r.status_code,'valuer',c.reporting.value_of(cdasset,D(1),'2026-11-04').value,'portfolio',[(str(p.value),str(p.cost_basis)) for p in c.investments.portfolio('2026-11-04',cdacc.id).open])
 # Form boundary checks, with the same valid fixture and no ledger changes on rejection.
 base={'date':'2026-11-02','account_id':broker.id,'asset_id':fund.id,'quantity':'1','total':'10','fees':'0'}
 for field,value in [('quantity',''),('quantity','0'),('quantity','-1'),('quantity','abc'),('quantity','1.1234567'),('total','0'),('total','-10'),('total','abc'),('total','10.001'),('total','999999999999999999999999'),('quantity','999999999999999999999999'),('account_id',bank.id),('date','wrong'),('date','2027-01-01'),('account_id','999999'),('asset_id','999999')]:
  n=c.db.one('SELECT COUNT(*) AS n FROM transactions')['n']
  r=client.post('/investments/new?kind=buy',data=base|{field:value})
  delta=c.db.one('SELECT COUNT(*) AS n FROM transactions')['n']-n
  print('VALIDATION',field,repr(value),r.status_code,'new transactions',delta)
 form=BeautifulSoup(client.get('/investments/new?kind=buy').text,'html.parser')
 token=form.select_one('[name=submission]')['value']
 n=c.db.one('SELECT COUNT(*) AS n FROM transactions')['n']
 statuses=[client.post('/investments/new?kind=buy',data=base|{'submission':token}).status_code for _ in range(2)]
 print('DUPLICATE',statuses,'new transactions',c.db.one('SELECT COUNT(*) AS n FROM transactions')['n']-n)
 unbalanced=c.db.all("SELECT transaction_id,SUM(amount_base_e6) AS n FROM ledger_entries WHERE effect='INTERNAL' GROUP BY transaction_id HAVING SUM(amount_base_e6)<>0")
 print('UNBALANCED INTERNAL TRANSACTIONS',len(unbalanced))
 c.db.close()
