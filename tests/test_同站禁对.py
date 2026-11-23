"""同站进出禁对（口径甲：站距零禁对）端到端验证。

覆盖：
- 异站 A→B 仍成对（行程行在、两刷卡已成对）；
- 同站 A→A：无行程行、有同站禁对旁路证、开腿已旁路、两刷卡同票已旁路；
- 同站裁决只读接口（站距零标记/命运/键/valid，两口径库态可区分）；
- 装载成对路径与同站写闸并发：不得旁路证与行程行双落；
- 行程贯验纳入同站硬不变量。

运行：.venv/bin/python -m pytest tests/test_同站禁对.py -q
（无 pytest 时：.venv/bin/python tests/test_同站禁对.py）
"""
import json
import os
import sys
import tempfile
import threading

# 独立脚本模式（无 conftest）时的引导
_测试目录 = os.path.join(tempfile.gettempdir(), "gatetwin-pytest-db")
os.makedirs(_测试目录, exist_ok=True)
os.environ.setdefault("数据目录", _测试目录)
os.environ["夹具目录"] = "/workspace/fixtures"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import 连接  # noqa: E402
from app import seed  # noqa: E402
from app.services import 装载, 同站裁决  # noqa: E402

# 显式建表（等价 startup），裸 TestClient 不触发生命周期事件
seed.初始化库()
client = TestClient(app)


def _库():
    conn = 连接()
    conn.row_factory = None
    return conn


def test_异站成对_同站禁对_硬分叉():
    r = client.post("/api/装载/夹具?名=同站禁对样例").json()
    assert r["同站禁对"] == 1, r
    assert r["成对"] == 1, r

    # 异站 s1→s2：行程行存在
    conn = _库()
    异站行 = conn.execute(
        "SELECT * FROM 行程账 WHERE 进站事件编号='s1' AND 出站事件编号='s2'"
    ).fetchone()
    assert 异站行 is not None

    # 同站 s3→s4：库中不存在任何该票行程行（两口径可区分点）
    同站行 = conn.execute(
        "SELECT * FROM 行程账 WHERE 进站事件编号='s3' AND 出站事件编号='s4'"
    ).fetchone()
    assert 同站行 is None
    assert conn.execute(
        "SELECT COUNT(*) FROM 行程账 WHERE 进站站点键=出站站点键"
    ).fetchone()[0] == 0

    # 同站禁对旁路证存在且原因钉死
    证 = conn.execute(
        "SELECT * FROM 旁路匣 WHERE 原因='同站禁对' AND 事件编号='s4'"
    ).fetchone()
    assert 证 is not None
    载荷 = json.loads(证[4])
    assert 载荷["站距零"] == 1
    assert 载荷["进站站点键"] == 载荷["出站站点键"] == "站A"

    # 开腿已关闭为已旁路
    腿 = conn.execute(
        "SELECT 状态 FROM 开腿账 WHERE 进站事件编号='s3'"
    ).fetchone()
    assert 腿[0] == "已旁路"

    # 两笔刷卡命运同票=已旁路，且不挂行程键
    for 号 in ("s3", "s4"):
        刷 = conn.execute(
            "SELECT 命运,行程键 FROM 刷卡点 WHERE 事件编号=?", (号,)
        ).fetchone()
        assert 刷[0] == "已旁路" and 刷[1] == ""

    # 异站两笔刷卡已成对并挂同键
    for 号 in ("s1", "s2"):
        刷 = conn.execute(
            "SELECT 命运,行程键 FROM 刷卡点 WHERE 事件编号=?", (号,)
        ).fetchone()
        assert 刷[0] == "已成对" and 刷[1] == 异站行[0]
    conn.close()


def test_同站裁决只读接口_事件视角():
    # 同站票
    r = client.get("/api/同站裁决?进站事件编号=s3&出站事件编号=s4").json()
    assert r["站距零标记"] == 1
    assert r["命运"] == "同站禁对"
    assert r["行程键"] == ""
    assert r["旁路键"] == "旁路-s3-s4"
    assert r["行程或旁路键"] == "旁路-s3-s4"
    assert r["valid"] == 1
    assert r["架构"] == "站距零禁对"

    # 异站票
    r = client.get("/api/同站裁决?进站事件编号=s1&出站事件编号=s2").json()
    assert r["站距零标记"] == 0
    assert r["命运"] == "已成对"
    assert r["行程键"].startswith("行-s1-s2")
    assert r["旁路键"] == ""
    assert r["valid"] == 1


def test_同站裁决_纯站点视角():
    r = client.get("/api/同站裁决?进站站=站A&出站站=站A").json()
    assert r["站距零标记"] == 1 and r["valid"] == 1
    assert r["预期命运"] == "同站禁对-已旁路"
    r = client.get("/api/同站裁决?进站站=站A&出站站=站B").json()
    assert r["站距零标记"] == 0 and r["valid"] == 1

    bad = client.get("/api/同站裁决")
    assert bad.status_code == 400


def test_并发装载_不得旁路证与行程双落():
    """两条连接并发处理同一同站票的不同装载批次，串行化后只允许一种落地形态。"""
    基线票 = {
        "批次编号": "批-并发基",
        "事件": [
            {"事件编号": "c1", "卡号": "卡91", "站点键": "站A", "方向": "进站",
             "事件时": "2026-11-22T13:00:00Z", "处理时": "2026-11-22T13:00:01Z"},
        ],
    }
    装载.装一批(基线票)

    出站批 = {
        "批次编号": "批-并发出",
        "事件": [
            {"事件编号": "c2", "卡号": "卡91", "站点键": "站A", "方向": "出站",
             "事件时": "2026-11-22T13:10:00Z", "处理时": "2026-11-22T13:10:02Z"},
        ],
    }
    错 = []

    def _worker(i):
        # 每线程独立批次号（避开批次编号唯一约束），同事件号 c2 才是真正的竞争点
        票 = {
            "批次编号": f"批-并发出-{i}",
            "事件": [
                {"事件编号": "c2", "卡号": "卡91", "站点键": "站A", "方向": "出站",
                 "事件时": "2026-11-22T13:10:00Z", "处理时": "2026-11-22T13:10:02Z"},
            ],
        }
        try:
            装载.装一批(票)
        except Exception as e:  # 锁竞争败者：报错即整体回滚，不允许落半截账
            错.append(e)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 串行化下：得锁者落同站禁对旁路；后到者遇事件幂等跳过，或锁忙回滚——均不得写行程
    conn = _库()
    行程数 = conn.execute(
        "SELECT COUNT(*) FROM 行程账 WHERE 进站事件编号='c1' AND 出站事件编号='c2'"
    ).fetchone()[0]
    旁路数 = conn.execute(
        "SELECT COUNT(*) FROM 旁路匣 WHERE 原因='同站禁对' AND 事件编号='c2'"
    ).fetchone()[0]
    c2 = conn.execute(
        "SELECT COUNT(*) FROM 刷卡点 WHERE 事件编号='c2'"
    ).fetchone()[0]
    腿态 = conn.execute(
        "SELECT 状态 FROM 开腿账 WHERE 进站事件编号='c1'"
    ).fetchone()[0]
    conn.close()

    # 同站票硬不变量：行程行恒 0；出站事件只入流一次；旁路证恰一张；无双落
    assert 行程数 == 0, "同站票出现行程行"
    assert c2 == 1, "出站事件被重复入流"
    assert 旁路数 == 1, f"旁路证数={旁路数}"
    assert 腿态 == "已旁路"
    # 锁忙报错只允许是 busy/locked 类（事务已回滚，无半截账）
    assert all("locked" in str(e).lower() or "busy" in str(e).lower() for e in 错), 错


def test_贯验纳入同站不变量():
    r = client.post("/api/贯验").json()
    assert r["是否通过"] is True, r["说明"]


if __name__ == "__main__":
    test_异站成对_同站禁对_硬分叉()
    test_同站裁决只读接口_事件视角()
    test_同站裁决_纯站点视角()
    test_并发装载_不得旁路证与行程双落()
    test_贯验纳入同站不变量()
    print("all same-station tests passed")
