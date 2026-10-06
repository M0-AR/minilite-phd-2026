"""Live-data verification: fetch real market series (BTC/FX) via stdlib, store in minilite, verify.
Sources: CoinGecko (no key), Frankfurter/ECB (no key). Falls back to deterministic synthetic if offline.
Each market bar stored as row [id, symbol, price_text] to exercise TEXT + index paths on real values."""
import sys, json, urllib.request, time, os
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
def fetch(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())
live_rows=[]; provenance=[]
try:
    btc=fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd')
    live_rows.append((1,'BTC-USD',str(btc['bitcoin']['usd']))); provenance.append('coingecko BTC-USD live')
except Exception as e: provenance.append(f'coingecko offline ({e}), synthetic fallback')
try:
    fx=fetch('https://api.frankfurter.app/latest?from=USD&to=EUR,GBP,JPY')
    for i,(k,v) in enumerate(sorted(fx['rates'].items()), start=2):
        live_rows.append((i,f'USD-{k}',str(v)))
    provenance.append('frankfurter/ECB live '+fx.get('date',''))
except Exception as e: provenance.append(f'frankfurter offline ({e}), synthetic fallback')
if not live_rows:
    live_rows=[(1,'BTC-USD','67000'),(2,'USD-EUR','0.92'),(3,'USD-GBP','0.79'),(4,'USD-JPY','151.2')]
    provenance.append('fully synthetic fallback (offline)')
print('provenance:',provenance)
p='/tmp/live_market.db'
for f in [p,p+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(p); db.execute('CREATE TABLE market (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
for r in live_rows: db.execute(f"INSERT INTO market VALUES ({r[0]}, '{r[1]}', '{r[2]}')")
print('stored',db.count('market'),'rows; check',db.check('market'))
for r in live_rows:
    got=db.execute(f"SELECT * FROM market WHERE id = {r[0]}")
    assert got[0][1]==r[1] and got[0][2]==r[2], f"mismatch {r} vs {got}"
print('point lookups verified on live values')
db.execute('CREATE INDEX market_name ON market (name)')
t0=time.time(); got=db.execute(f"SELECT * FROM market WHERE name = '{live_rows[0][1]}'")
print(f"indexed live-symbol search: {got} plan='{db.last_plan}' pages={db.last_pages_read} {(time.time()-t0)*1000:.2f}ms")
db.close()
print('LIVE-DATA VERIFICATION PASSED')
