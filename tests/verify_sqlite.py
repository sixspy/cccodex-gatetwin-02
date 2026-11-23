"""纯 sqlite 层验证（不依赖 fastapi）：同站禁对全链路 + 并发双落。"""
import json
import os
import sys
import tempfile
import threading

os.environ["数据目录"] = tempfile.mkdtemp(prefix="gatetwin-sql-")
sys.path.insert(0, "/workspace/backend")

from app.db import 连接
from app import seed
from app.services import 装载, 贯验, 同站裁决

seed.初始化库()

# 1) 同站夹具：异站成对 + 同站禁对
报告 = 装载.装一批(json.loads(open("/workspace/fixtures/同站禁对样例.json", encoding="utf-8").read()))
assert 报告["成对"] == 1 and 报告["同站禁对"] == 1, 报告

conn = 连接()
assert conn.execute("SELECT COUNT(*) FROM 行程账 WHERE 进站事件编号='s1' AND 出站事件编号='s2'").fetchone()[0] == 1
assert conn.execute("SELECT COUNT(*) FROM 行程账 WHERE 进站事件编号='s3' AND 出站事件编号='s4'").fetchone()[0] == 0
assert conn.execute("SELECT COUNT(*) FROM 行程账 WHERE 进站站点键=出站站点键").fetchone()[0] == 0
证 = conn.execute("SELECT * FROM 旁路匣 WHERE 原因='同站禁对' AND 事件编号='s4'").fetchone()
assert 证, "缺同站禁对旁路证"
载荷 = json.loads(证["载荷"])
assert 载荷["站距零"] == 1 and 载荷["架构"] == "站距零禁对"
assert conn.execute("SELECT 状态 FROM 开腿账 WHERE 进站事件编号='s3'").fetchone()[0] == "已旁路"
for 号 in ("s3", "s4"):
    命运, 键 = conn.execute("SELECT 命运,行程键 FROM 刷卡点 WHERE 事件编号=?", (号,)).fetchone()
    assert 命运 == "已旁路" and 键 == ""
for 号 in ("s1", "s2"):
    命运, 键 = conn.execute("SELECT 命运,行程键 FROM 刷卡点 WHERE 事件编号=?", (号,)).fetchone()
    assert 命运 == "已成对" and 键.startswith("行-s1-s2")
print("1) 硬分叉：异站成对 / 同站无行程有旁路 / 同票命运 OK")

# 2) 裁决接口（只读）
v = 同站裁决.裁决(conn, 进站事件编号="s3", 出站事件编号="s4")
assert v["站距零标记"] == 1 and v["valid"] == 1 and v["命运"] == "同站禁对"
assert v["行程或旁路键"] == "旁路-s3-s4" and v["行程键"] == ""
v2 = 同站裁决.裁决(conn, 进站事件编号="s1", 出站事件编号="s2")
assert v2["站距零标记"] == 0 and v2["valid"] == 1 and v2["行程键"].startswith("行-")
v3 = 同站裁决.裁决(conn, 进站站="站A", 出站站="站A")
assert v3["站距零标记"] == 1 and v3["预期命运"] == "同站禁对-已旁路"
print("2) 同站裁决只读接口 OK：", json.dumps(v, ensure_ascii=False))

# 3) 并发：同站出站多连接同时装载，不得旁路证+行程双落
装载.装一批({"批次编号": "b0", "事件": [
    {"事件编号": "c1", "卡号": "卡91", "站点键": "站A", "方向": "进站",
     "事件时": "2026-11-22T13:00:00Z", "处理时": "2026-11-22T13:00:01Z"}]})
批 = {"批次编号": "bx", "事件": [
    {"事件编号": "c2", "卡号": "卡91", "站点键": "站A", "方向": "出站",
     "事件时": "2026-11-22T13:10:00Z", "处理时": "2026-11-22T13:10:02Z"}]}
errs = []
def work():
    try:
        装载.装一批(批)
    except Exception as e:
        errs.append(str(e))
ts = [threading.Thread(target=work) for _ in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
行 = conn.execute("SELECT COUNT(*) FROM 行程账 WHERE 进站事件编号='c1' AND 出站事件编号='c2'").fetchone()[0]
旁 = conn.execute("SELECT COUNT(*) FROM 旁路匣 WHERE 原因='同站禁对' AND 事件编号='c2'").fetchone()[0]
刷 = conn.execute("SELECT COUNT(*) FROM 刷卡点 WHERE 事件编号='c2'").fetchone()[0]
assert 行 == 0, "同站票出现行程行"
assert 旁 <= 1 and 刷 == 1, (行, 旁, 刷)
assert not (行 and 旁), "旁路证与行程双落"
print(f"3) 并发不双落 OK：行程={行} 旁路证={旁} 出站刷卡={刷} 败者回滚={len(errs)}")

# 4) 贯验自洽
g = 贯验.跑贯验()
assert g["是否通过"], g["说明"]
print("4) 行程贯验通过：", g["说明"])

# 5) 幂等：同站旁路路径重放（新批次、同事件号）不重复落证
重放 = dict(批); 重放["批次编号"] = "bx-重放"
装载.装一批(重放)
旁2 = conn.execute("SELECT COUNT(*) FROM 旁路匣 WHERE 原因='同站禁对' AND 事件编号='c2'").fetchone()[0]
assert 旁2 == 旁, (旁, 旁2)
print("5) 同站旁路幂等 OK")

# 6) 站规口径已钉到禁对（含迁移）
assert conn.execute("SELECT 值 FROM 站规 WHERE 键='同站进出'").fetchone()[0] == "禁对-站距零"
assert conn.execute("SELECT 值 FROM 站规 WHERE 键='同站裁决架构'").fetchone()[0] == "站距零禁对"
print("6) 站规口径 OK")
conn.close()
print("\n全部 sqlite 层断言通过")
