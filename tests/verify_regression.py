"""回归：原有四套夹具在同站禁对架构下行为不变。"""
import json
import os
import sys
import tempfile

os.environ["数据目录"] = tempfile.mkdtemp(prefix="gatetwin-reg-")
sys.path.insert(0, "/workspace/backend")

from app.db import 连接
from app import seed
from app.services import 装载, 贯验

seed.初始化库()
conn = 连接()

r1 = 装载.装一批(json.loads(open("/workspace/fixtures/成对样例.json", encoding="utf-8").read()))
assert r1["成对"] == 2 and r1["同站禁对"] == 0 and r1["旁路"] == 0, r1
assert conn.execute("SELECT COUNT(*) FROM 行程账").fetchone()[0] == 2

r2 = 装载.装一批(json.loads(open("/workspace/fixtures/出站孤儿样例.json", encoding="utf-8").read()))
assert r2["旁路"] == 1 and r2["成对"] == 0
assert conn.execute("SELECT COUNT(*) FROM 旁路匣 WHERE 原因='出站孤儿'").fetchone()[0] == 1

r3 = 装载.装一批(json.loads(open("/workspace/fixtures/重复进站样例.json", encoding="utf-8").read()))
# r1 进站被旁路、r2 新腿、r3 与 r2 异站 B→C 成对
assert r3["旁路"] == 1 and r3["成对"] == 1, r3
assert conn.execute("SELECT COUNT(*) FROM 旁路匣 WHERE 原因='重复进站'").fetchone()[0] == 1

r4 = 装载.装一批(json.loads(open("/workspace/fixtures/缺腿超时样例.json", encoding="utf-8").read()))
# t1 水位超时旁路；t2→t3 站C→站A 异站成对
assert r4["超时旁路"] == 1 and r4["成对"] == 1, r4
assert conn.execute("SELECT COUNT(*) FROM 旁路匣 WHERE 原因='缺腿超时'").fetchone()[0] == 1

g = 贯验.跑贯验()
assert g["是否通过"], g["说明"]
print("原有夹具回归全绿；贯验：", g["说明"])
print("行程数", g["行程数"], "旁路数", g["旁路数"], "开腿数", g["开腿数"])
conn.close()
