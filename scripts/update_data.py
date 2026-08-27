import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
target=os.path.join(root,"data")
os.makedirs(target,exist_ok=True)
for scope in ("cn","hk","global"):
    payload=server.market_payload(scope)
    if not payload.get("sectors"):
        raise RuntimeError(f"{scope} 行情为空，停止覆盖")
    with open(os.path.join(target,f"{scope}.json"),"w",encoding="utf-8") as f:
        json.dump(payload,f,ensure_ascii=False,separators=(",",":"))

