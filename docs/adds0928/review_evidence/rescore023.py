import pandas as pd, json, warnings
warnings.filterwarnings("ignore")
from policybench.analysis import weighted_hit_rate_scores_by_model
S='paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/'
r=pd.read_csv(S+'reference_outputs.csv')
ex={(x['scenario_id'],x['variable']) for x in json.load(open(S+'reference_exclusions.json'))['exclusions']}
gt=r[[ (a,b) not in ex for a,b in zip(r.scenario_id,r.variable)]].copy()
p=pd.read_csv(S+'predictions.csv.gz', low_memory=False)
def score(g):
    s=weighted_hit_rate_scores_by_model(g,p,{},country='us').set_index('model')['weighted_exact']*100
    return s
base=score(gt)
d=json.load(open('results/local/adds0928-v3/data-board45.json'))
ms=d['countries']['us'].get('modelStats')
pub={m['model']:m for m in ms} if isinstance(ms,list) else ms
k=next(iter(pub.values()))
print('modelStats keys', list(k.keys())[:20])
key=[c for c in k if 'exact' in c.lower()]
print(key)
mask=(gt.scenario_id=='scenario_023')&(gt.variable=='head_medicaid_eligible')
excl=score(gt[~mask])
g0=gt.copy(); g0.loc[mask,'value']=0.0
zero=score(g0)
out=pd.DataFrame({'base':base,'excl023':excl,'ref0':zero})
if key:
    out['published']=pd.Series({m:v[key[0]] for m,v in pub.items()})
out['rank_base']=out.base.rank(ascending=False,method='min')
out['rank_excl']=out.excl023.rank(ascending=False,method='min')
out['rank_ref0']=out.ref0.rank(ascending=False,method='min')
pd.set_option('display.width',200)
print(out.sort_values('base',ascending=False).round(3).to_string())
print('delta excl range', (out.excl023-out.base).min(), (out.excl023-out.base).max())
