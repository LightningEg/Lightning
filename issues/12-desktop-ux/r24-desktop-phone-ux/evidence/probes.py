import os,sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
os.environ['LIGHTNING_TODAY']='2026-11-05'
os.environ['LIGHTNING_PRICES_OFFLINE']='1'
from lightning.bootstrap import build
from lightning.demo import build_demo
from lightning.ui.routes.register import _asset_view
from lightning.core.dates import today

def facts(c):
    p=c.position.at(today()); f=c.forecaster.forecast()
    return {'what_you_own':p.what_you_own,'held_for_others':p.held_for_others,'in_your_accounts':p.in_your_accounts,'account_row_sum':sum(c.reporting.account_value(a.id,today()) for a in c.accounts.list(active_only=True)),'gameya_still_to_pay':p.gameya_still_to_pay,'free_cash':p.free_cash,'safe_to_spend':f.safe_to_spend,'parts':f.safe_to_spend_parts}

def probe(c):
    data={'before':facts(c),'assets':[]}
    reserve=next(r for r in c.reserves.list_active() if r['kind']=='EMERGENCY')
    move=c.position.at(today()).free_cash
    c.reserves.set_emergency_fund(reserve['effective_allocated']+move)
    data['refill_amount']=move;data['after_refill']=facts(c)
    c.reserves.set_emergency_fund(reserve['allocated'])
    loan=c.planning.create(kind='LOAN',name='Audit car loan',amount='2500',frequency='MONTHLY',start_date='2026-01-15',payment_count=10)
    for opening in ['0','600000']:
        a=c.account_flows.open_account('Audit Car '+opening,'OTHER_ASSET','2025-01-01',opening)
        c.accounts.save_other_asset_value(a,'2025-06-01','600000')
        c.accounts.save_other_asset_value(a,'2026-06-01','540000')
        c.accounts.save_other_asset_details(a,'car','2025-06-01','600000',str(loan))
        view=_asset_view(c,a)
        data['assets'].append({'account_id':a.id,'opening':opening,'report_value':c.reporting.account_value(a.id,today()),'panel':view})
    return data

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as td:
        c=build(Path(td)/'audit.db');build_demo(c)
        data=probe(c)
        Path(str(Path(__file__).resolve().parent / 'logic-probes.json')).write_text(json.dumps(data,default=str,indent=2))
        print(json.dumps(data,default=str,indent=2))
        c.db.close()
