import sys,os;sys.path.insert(0,'src');os.environ['MOCK']='1'
import pandas as pd,numpy as np
import data_source as ds, indicators as ind, backtest as bt, adjust as adj
# 1) RSI: so với cài đặt Wilder viết tay
c=pd.Series(np.cumsum(np.random.default_rng(1).normal(0,1,300))+100)
d=c.diff().values;g=np.where(d>0,d,0);l=np.where(d<0,-d,0)
ag=g[1:15].mean();al=l[1:15].mean();ref=[None]*15
for i in range(15,300):
    ag=(ag*13+g[i])/14;al=(al*13+l[i])/14
mine=ind.rsi(c).iloc[-1];wild=100-100/(1+ag/al)
print('RSI code',round(mine,3),'Wilder chuẩn',round(wild,3))
assert abs(mine-wild)<0.5
# 2) Phát hành thêm 10:5 giá 10.000 + thưởng 10:2, giá trước 30.000
df=pd.DataFrame({'time':pd.bdate_range('2026-01-01',periods=6),'open':[30000]*6,'high':[30500]*6,'low':[29500]*6,
 'close':[30000,30000,30000,20600,20800,21000],'volume':[1000]*6})
a=adj.CorporateAction('2026-01-06',rights_ratio=0.5,rights_price=10000,bonus_ratio=0.2)
k=adj.adjustment_factor(30000,a);print('Hệ số k',round(k,4),'giá tham chiếu',30000*k)
print('Phiên đáng ngờ trước điều chỉnh:',len(adj.suspicious_gaps(df)))
fixed=adj.adjust_prices(df,[a]);print(fixed[['time','close','volume']].to_string(index=False))
print('Phiên đáng ngờ sau điều chỉnh:',len(adj.suspicious_gaps(fixed)))
# 3) pipeline 1 mã
h=ds.get_history('FPT');x=ind.compute(h);print(ind.snapshot(x))
r=bt.run(x);print({k:(v['count'],v['win_rate']) for k,v in r.items()})
