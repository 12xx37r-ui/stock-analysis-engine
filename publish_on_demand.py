"""Publish one on-demand engine result into data/latest."""
import argparse, json, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
KST=timezone(timedelta(hours=9))
def d(v): return v if isinstance(v,dict) else {}
def l(v): return v if isinstance(v,list) else []
def f(v,default=0.0):
    try: return float(v)
    except (TypeError,ValueError): return default
def load(p,default): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8'); t.replace(p)
def hs(pred,key): return f(d(pred.get(key)).get('점수'),50.0)
def row(stock):
    pred=d(stock.get('주가예측')); fin=d(stock.get('재무분석')); buff=d(fin.get('버핏평가')); val=d(stock.get('가치평가'))
    s,m,g=hs(pred,'단기1~5일'),hs(pred,'중기1~8주'),hs(pred,'장기6~18개월'); b=f(buff.get('점수')); gap=f(val.get('현재가대비')); vs=max(0,min(100,50+gap)); comp=g*.35+m*.25+s*.15+b*.15+vs*.10
    return {'전체순위':0,'종합순위':0,'기업명':str(stock.get('기업명','')),'종목코드':str(stock.get('KIS종목코드','')).zfill(6),'산업코드':str(stock.get('산업코드','none')),'배치':'on_demand','종합선별점수':round(comp,2),'단기점수':round(s,2),'중기점수':round(m,2),'장기점수':round(g,2),'버핏점수':round(b,2),'가치점수':round(vs,2),'저평가후보':gap>0 and '고평가' not in str(val.get('판단','')),'생성시각':stock.get('생성시각','')}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stock-file',required=True); ap.add_argument('--latest-root',default='data/latest'); a=ap.parse_args(); sp=Path(a.stock_file); root=Path(a.latest_root); stock=load(sp,{}); code=str(stock.get('KIS종목코드','')).zfill(6)
    if len(code)!=6 or not code.isdigit(): raise RuntimeError('종목코드 오류')
    sr=root/'stocks'; sr.mkdir(parents=True,exist_ok=True); shutil.copy2(sp,sr/f'{code}.json')
    ip=root/'index.json'; idx=load(ip,{'버전':'1.1.0','배치':[],'종합순위':[],'종목목록':[]}); rows=[d(x) for x in l(idx.get('종합순위')) if str(d(x).get('종목코드','')).zfill(6)!=code]; rows.append(row(stock)); rows.sort(key=lambda x:(f(x.get('종합선별점수')),f(x.get('장기점수')),f(x.get('버핏점수'))),reverse=True)
    for n,x in enumerate(rows,1): x['전체순위']=n; x['종합순위']=n
    idx.update({'버전':'1.1.0','생성시각':datetime.now(KST).isoformat(),'상태':'PASS','최근실행배치':'on_demand','종목수':len(rows),'종합순위':rows,'종목목록':[{'종목코드':x.get('종목코드',''),'기업명':x.get('기업명',''),'배치':x.get('배치','')} for x in rows]}); write(ip,idx)
    print('ON-DEMAND PUBLISH RESULT'); print('- 종목코드:',code); print('- 전체 최신피드 종목:',len(rows)); print('LATEST_STOCK_FILE='+str(sr/f'{code}.json')); print('LATEST_INDEX_FILE='+str(ip)); return 0
if __name__=='__main__': sys.exit(main())
