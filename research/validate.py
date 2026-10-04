import pandas as pd, numpy as np
d=pd.read_csv('Dataset_NQ_1min_2022_2025.csv')
d.columns=['ts','open','high','low','close','volume','vwap_rth','vwap_eth']
d['ts']=pd.to_datetime(d.ts,format='%m/%d/%Y %H:%M')
print(d.dtypes); print('rows',len(d),'NaN',d.isna().sum().sum(),'dup ts',d.ts.duplicated().sum())
bad=(d.high<d[['open','close']].max(1))|(d.low>d[['open','close']].min(1))|(d.high<d.low)
print('OHLC inconsistent',bad.sum()); print('vol<=0',(d.volume<=0).sum())
print('tick grid violations',((d[['open','high','low','close']]*4)%1!=0).sum().sum())
t=d.ts.dt.strftime('%H:%M')
# where does Vwap_RTH become nonzero each day
nz=d[d.vwap_rth!=0]; print('first nonzero RTH vwap times:',nz.groupby(nz.ts.dt.date).ts.min().dt.strftime('%H:%M').value_counts().head())
print('last nonzero RTH vwap times:',nz.groupby(nz.ts.dt.date).ts.max().dt.strftime('%H:%M').value_counts().head())
# first bar per ETH session
gap=d.ts.diff().dt.total_seconds()/60
starts=d[gap>30]; print('session start times:',starts.ts.dt.strftime('%H:%M').value_counts().head())
ends=d[gap.shift(-1)>30]; print('session end times:',ends.ts.dt.strftime('%H:%M').value_counts().head())
# RTH bar coverage
rth=d[(t>='09:30')&(t<='16:00')]; c=rth.groupby(rth.ts.dt.date).size()
print('RTH days',len(c)); print(c.describe()); print('short days',c[c<380].to_dict())
# verify RTH vwap: hlc3 anchored where?
day=d[d.ts.dt.date==pd.Timestamp('2024-03-05').date()].copy()
r=day[(day.ts.dt.strftime('%H:%M')>='09:30')]
for src in ['hlc3','close','ohlc4']:
  for start in ['09:30','09:31']:
    x=r[r.ts.dt.strftime('%H:%M')>=start].copy()
    s=(x.high+x.low+x.close)/3 if src=='hlc3' else (x.close if src=='close' else (x.open+x.high+x.low+x.close)/4)
    v=(s*x.volume).cumsum()/x.volume.cumsum()
    print(src,start,'max abs diff first 60',(v-x.vwap_rth).head(60).abs().max())
print(r.head(4)[['ts','open','high','low','close','volume','vwap_rth']])
# large gaps within sessions
inner=gap[(gap>1)&(gap<=30)]; print('intra-session gaps >1min:',len(inner), inner.value_counts().head())
