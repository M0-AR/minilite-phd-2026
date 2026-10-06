# Experiments — what to run, what it proves
- `bench_point.py [N]` — load N, point/range/scan pages+ms, build index, re-measure. Paper: N=20000/100000/1000000.
- `sqlite_compare.py` — same 10k rows in minilite vs stdlib sqlite3, EXPLAIN parity + size.
- `hidden_patterns.py` — sequential vs random fill-factor + fanout law.
- `live_data_verify.py` — CoinGecko BTC + Frankfurter FX into minilite, provenance + indexed lookup.
