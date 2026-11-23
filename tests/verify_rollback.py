"""故障注入：同站写闸中途失败必须整体回滚，无半截账。"""
import os
import sys
import tempfile

os.environ["数据目录"] = tempfile.mkdtemp(prefix="gatetwin-fail-")
sys.path.insert(0, "/workspace/backend")

from app.db import 连接  # noqa: E402
from app import seed  # noqa: E402
from app.services import 装载  # noqa: E402

seed.初始化库()
装载.装一批({"批次编号": "b1", "事件": [
    {"事件编号": "f1", "卡号": "卡X", "站点键": "站A", "方向": "进站",
     "事件时": "2026-11-22T14:00:00Z", "处理时": "2026-11-22T14:00:01Z"}]})


def _炸(*a, **k):
    raise RuntimeError("注入写失败")


装载.同站禁对写出站 = _炸

try:
    装载.装一批({"批次编号": "b2", "事件": [
        {"事件编号": "f2", "卡号": "卡X", "站点键": "站A", "方向": "出站",
         "事件时": "2026-11-22T14:05:00Z", "处理时": "2026-11-22T14:05:01Z"}]})
    raise AssertionError("应当抛出")
except RuntimeError as e:
    assert "注入写失败" in str(e)

conn = 连接()
# 同事务回滚：f2 刷卡点不残留；f1 开腿仍在途、命运仍已开腿；无旁路证/行程/批次行
assert conn.execute("SELECT COUNT(*) FROM 刷卡点 WHERE 事件编号='f2'").fetchone()[0] == 0
assert conn.execute("SELECT 状态 FROM 开腿账 WHERE 进站事件编号='f1'").fetchone()[0] == "在途"
assert conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0] == 0
assert conn.execute("SELECT COUNT(*) FROM 行程账").fetchone()[0] == 0
assert conn.execute("SELECT COUNT(*) FROM 装载批次 WHERE 编号='b2'").fetchone()[0] == 0
assert conn.execute("SELECT 命运 FROM 刷卡点 WHERE 事件编号='f1'").fetchone()[0] == "已开腿"
conn.close()
print("故障回滚断言通过：无旁路证/行程/开腿半截账")
