import json, os, time, urllib.parse, urllib.request
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
MACRO={"000001.SS":"上证指数","^HSI":"恒生指数","^IXIC":"纳斯达克","^GSPC":"标普500","DX-Y.NYB":"美元指数","GC=F":"黄金期货","CL=F":"WTI原油","^VIX":"恐慌指数"}
SECTORS={"SMH":"半导体","XLK":"科技","BOTZ":"人工智能","ROBO":"机器人","ICLN":"清洁能源","TAN":"太阳能","XLF":"金融","XBI":"生物科技","XLV":"医疗","XLY":"消费","XLI":"工业","XLB":"材料","XLE":"能源","XLU":"公用事业","XLRE":"房地产"}
SECTOR_GROUPS={"global":("全球行业","ETF代理",SECTORS),"cn":("A股行业","交易所ETF代理",{"512480.SS":"半导体","515000.SS":"科技","159995.SZ":"芯片","512660.SS":"军工","512170.SS":"医疗","512010.SS":"医药","512800.SS":"银行","512070.SS":"证券保险","515030.SS":"新能源车","515790.SS":"光伏","159869.SZ":"游戏","516160.SS":"新能源","512400.SS":"有色金属","159928.SZ":"消费","512200.SS":"房地产"}),"hk":("港股行业","代表股代理",{"0700.HK":"互联网","9988.HK":"电商","3690.HK":"本地生活","1810.HK":"消费电子","1211.HK":"新能源汽车","9866.HK":"新势力汽车","1299.HK":"保险","0939.HK":"银行","0883.HK":"油气","0857.HK":"石油","1177.HK":"医药","2269.HK":"生物科技","0388.HK":"交易所","1109.HK":"地产","0005.HK":"综合金融"})}
LINKS={"SMH":("半导体/CPO","寒武纪、中际旭创、新易盛"),"BOTZ":("机器人/AI","机器人、工业自动化、算力"),"TAN":("光伏","光伏设备、逆变器、硅料"),"XBI":("创新药","创新药、CXO、医疗服务"),"XLE":("油气能源","石油开采、油服、煤化工")}
MOVERS={"NVDA":("英伟达","AI算力、CPO、液冷"),"META":("Meta","虚拟现实、AI应用"),"TSLA":("特斯拉","新能源汽车、机器人"),"TSM":("台积电","半导体及元件"),"MU":("美光科技","存储芯片"),"SMCI":("超微电脑","服务器、液冷"),"PLTR":("Palantir","数据要素、AI软件"),"GOOGL":("谷歌","云计算、AI应用"),"AMZN":("亚马逊","跨境电商、云计算"),"AAPL":("苹果","消费电子、果链")}
CACHE={}
def fetch_symbol(symbol):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?interval=5m&range=5d";req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MarketRadarDemo/1.0"})
    with urllib.request.urlopen(req,timeout=8) as response:result=json.load(response)["chart"]["result"][0]
    meta=result["meta"];raw=result.get("indicators",{}).get("quote",[{}])[0].get("close",[]);timestamps=result.get("timestamp",[]);points=[(t,v) for t,v in zip(timestamps,raw) if v is not None];values=[v for _,v in points];price=meta.get("regularMarketPrice") or (values[-1] if values else None);previous=meta.get("chartPreviousClose") or meta.get("previousClose");change=((price/previous)-1)*100 if price and previous else 0
    def period_change(seconds):
        if not points:return 0
        latest_t,latest_v=points[-1];target=latest_t-seconds;older=min(points,key=lambda p:abs(p[0]-target))[1]
        return ((latest_v/older)-1)*100 if older else 0
    return {"symbol":symbol,"price":price,"change":change,"change5m":period_change(300),"change5d":period_change(5*86400),"chart":values[-180:],"marketTime":meta.get("regularMarketTime") or (points[-1][0] if points else int(time.time()))}
def fetch_with_retry(symbol):
    error=None
    for attempt in range(3):
        try:return fetch_symbol(symbol)
        except Exception as exc:
            error=exc;time.sleep(.8*(attempt+1))
    raise error
def tencent_code(symbol):
    if symbol.endswith('.SS'):return 'sh'+symbol.split('.')[0]
    if symbol.endswith('.SZ'):return 'sz'+symbol.split('.')[0]
    if symbol.endswith('.HK'):return 'hk'+symbol.split('.')[0].zfill(5)
    if symbol.startswith('^') or '=' in symbol:return None
    return 'us'+symbol.replace('-','.')
def fetch_tencent(symbol):
    code=tencent_code(symbol)
    if not code:raise ValueError('unsupported symbol')
    url=f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,10,qfq"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MarketRadarDemo/1.0"})
    with urllib.request.urlopen(req,timeout=10) as response:obj=json.load(response)["data"][code]
    qt=obj.get("qt",{}).get(code);rows=obj.get("qfqday") or obj.get("day") or []
    if not qt:raise ValueError('empty quote')
    price=float(qt[3]);previous=float(qt[4]);change=float(qt[32]);market_text=qt[30]
    try:
        clean=''.join(ch for ch in market_text if ch.isdigit());fmt='%Y%m%d%H%M%S';market_time=int(time.mktime(time.strptime(clean[:14],fmt)))
    except Exception:market_time=int(time.time())
    change5d=change
    if len(rows)>=6:
        older=float(rows[-6][2]);change5d=((price/older)-1)*100 if older else change
    change5m=0
    try:
        minute_url=f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
        with urllib.request.urlopen(urllib.request.Request(minute_url,headers={"User-Agent":"Mozilla/5.0 MarketRadarDemo/1.0"}),timeout=8) as response:minute=json.load(response)["data"][code]["data"]["data"]
        if len(minute)>=6:
            latest=float(minute[-1].split()[1]);older=float(minute[-6].split()[1]);change5m=((latest/older)-1)*100 if older else 0
    except Exception:pass
    return {"symbol":symbol,"price":price,"change":change,"change5m":change5m,"change5d":change5d,"marketTime":market_time,"source":"腾讯行情公开接口"}
def market_payload(scope="global"):
    scope=scope if scope in SECTOR_GROUPS else "global";label,proxy,sectors_map=SECTOR_GROUPS[scope];cached=CACHE.get(scope)
    if cached and time.time()-cached["at"]<12:return {**cached["data"],"stale":False}
    symbols=list(MACRO)+list(sectors_map)+list(MOVERS);data={};failures=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch_with_retry,s):s for s in symbols}
        for future in as_completed(futures):
            try:data[futures[future]]=future.result()
            except Exception:failures+=1
    if scope in ("cn","hk"):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(fetch_tencent,s):s for s in sectors_map}
            for future in as_completed(futures):
                symbol=futures[future]
                try:
                    primary=future.result();primary["chart"]=data.get(symbol,{}).get("chart",[]);data[symbol]=primary
                except Exception:pass
    macro=[{"name":name,"symbol":s,"price":f"{data[s]['price']:,.2f}","change":data[s]["change"],"changeText":f"{data[s]['change']:+.2f}%"} for s,name in MACRO.items() if s in data]
    sectors=[{"name":name,"symbol":s,"change":data[s]["change"],"change1d":data[s]["change"],"change5m":data[s]["change5m"],"change5d":data[s]["change5d"],"source":data[s].get("source","Yahoo Finance公共报价"),"changeText":f"{data[s]['change']:+.2f}%"} for s,name in sectors_map.items() if s in data]
    linkage=[{"usName":SECTORS[s],"usSymbol":s,"usChange":data[s]["change"],"cnTheme":theme,"targets":targets,"strength":f"{min(99,round(55+abs(data[s]['change'])*12))}%"} for s,(theme,targets) in LINKS.items() if s in data]
    movers=sorted([{"name":name,"symbol":s,"price":data[s]["price"],"change":data[s]["change"],"cnTheme":theme,"reason":f"日内涨跌幅达到 {abs(data[s]['change']):.2f}%，系统识别为价格异动；具体驱动仍需结合公司公告和权威新闻核验。"} for s,(name,theme) in MOVERS.items() if s in data],key=lambda x:abs(x["change"]),reverse=True)[:6]
    market_times=[data[s].get("marketTime",0) for s in sectors_map if s in data];sources=sorted(set(s.get("source","Yahoo Finance公共报价") for s in sectors));payload={"macro":macro,"sectors":sectors,"sectorScope":scope,"sectorLabel":label,"sectorProxyType":proxy,"feedSources":sources,"linkage":linkage,"movers":movers,"chart":data.get("^IXIC",{}).get("chart",[]),"completeness":round((len(data)/len(symbols))*100,1),"asOf":max(market_times,default=int(time.time()))*1000,"generatedAt":int(time.time()*1000),"feedType":"多源公开参考行情","stale":False}
    if macro:CACHE[scope]={"at":time.time(),"data":payload};return payload
    if cached:return {**cached["data"],"stale":True}
    return payload
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/market'):
            try:scope=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("scope",["global"])[0];body=json.dumps(market_payload(scope),ensure_ascii=False).encode();status=200
            except Exception as exc:body=json.dumps({"error":str(exc)}).encode();status=503
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        super().do_GET()
if __name__=='__main__':os.chdir(os.path.dirname(os.path.abspath(__file__)));ThreadingHTTPServer(('127.0.0.1',4173),Handler).serve_forever()

