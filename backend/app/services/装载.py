import json
from app.db import 连接
from app.seed import 此刻
from app.modules.同站进出禁对 import 是同站, 同站禁对写出站
from app.services import 时间, 配对


def 装一批(体: dict) -> dict:
    """装载刷卡点：同卡进站开腿、出站成对；同站禁对/缺腿超时/孤儿旁路。

    口径（全局唯一：站距零禁对）：
    - 进站：同卡若已有在途开腿 → 旧腿旁路(重复进站)并开新腿
    - 出站：匹配同卡在途开腿
      · 进站站点键==出站站点键（站距零）→ 同站禁对：不写行程，开腿关闭进旁路匣，
        两笔刷卡同票已旁路（同站写闸与开腿关闭同一事务同成败）
      · 异站 → 写行程账；无开腿 → 出站孤儿旁路
    - 批次末：按本批最大事件时扫缺腿超时
    """
    批次编号 = 体.get("批次编号") or f"批-{此刻().replace(':', '').replace('-', '')}"
    事件列表 = 体.get("事件") or []
    conn = 连接()
    try:
        # 立即拿写锁：同站写闸/成对写闸跨连接并发时串行化，杜绝旁路证与行程行双落。
        conn.execute("BEGIN IMMEDIATE")
        报告 = {
            "批次编号": 批次编号,
            "入流": 0,
            "开腿": 0,
            "成对": 0,
            "旁路": 0,
            "同站禁对": 0,
            "超时旁路": 0,
            "明细": [],
        }
        站 = {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
        最大行程秒 = int(站.get("最大行程秒", "7200"))
        水位 = None

        for ev in 事件列表:
            事件编号 = ev["事件编号"]
            卡号 = ev["卡号"]
            站点键 = ev["站点键"]
            方向 = ev["方向"]
            事件时 = ev["事件时"]
            处理时 = ev.get("处理时") or 此刻()

            if 水位 is None or 时间.解析(事件时) > 时间.解析(水位):
                水位 = 事件时

            if conn.execute("SELECT 1 FROM 刷卡点 WHERE 事件编号=?", (事件编号,)).fetchone():
                报告["明细"].append({"事件编号": 事件编号, "命运": "幂等跳过"})
                continue

            站行 = conn.execute("SELECT * FROM 站点 WHERE 站点键=?", (站点键,)).fetchone()
            if not 站行:
                conn.execute(
                    "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
                    ("未知站点", 卡号, 事件编号, json.dumps(ev, ensure_ascii=False), 处理时),
                )
                conn.execute(
                    """INSERT INTO 刷卡点(事件编号,卡号,站点键,方向,事件时,处理时,命运,行程键,批次编号)
                       VALUES (?,?,?,?,?,?, '已旁路', '', ?)""",
                    (事件编号, 卡号, 站点键, 方向, 事件时, 处理时, 批次编号),
                )
                报告["旁路"] += 1
                报告["入流"] += 1
                报告["明细"].append({"事件编号": 事件编号, "命运": "旁路-未知站"})
                continue

            if 方向 not in ("进站", "出站"):
                conn.execute(
                    "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
                    ("方向非法", 卡号, 事件编号, json.dumps(ev, ensure_ascii=False), 处理时),
                )
                conn.execute(
                    """INSERT INTO 刷卡点(事件编号,卡号,站点键,方向,事件时,处理时,命运,行程键,批次编号)
                       VALUES (?,?,?,?,?,?, '已旁路', '', ?)""",
                    (事件编号, 卡号, 站点键, 方向, 事件时, 处理时, 批次编号),
                )
                报告["旁路"] += 1
                报告["入流"] += 1
                报告["明细"].append({"事件编号": 事件编号, "命运": "旁路-方向非法"})
                continue

            conn.execute(
                """INSERT INTO 刷卡点(事件编号,卡号,站点键,方向,事件时,处理时,命运,行程键,批次编号)
                   VALUES (?,?,?,?,?,?, '已入流', '', ?)""",
                (事件编号, 卡号, 站点键, 方向, 事件时, 处理时, 批次编号),
            )
            报告["入流"] += 1

            if 方向 == "进站":
                旧 = conn.execute(
                    "SELECT * FROM 开腿账 WHERE 卡号=? AND 状态='在途'", (卡号,)
                ).fetchone()
                if 旧:
                    conn.execute(
                        "UPDATE 开腿账 SET 状态='已旁路', 更新处理时=? WHERE 开腿键=?",
                        (处理时, 旧["开腿键"]),
                    )
                    conn.execute(
                        "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
                        ("已旁路", 旧["进站事件编号"]),
                    )
                    conn.execute(
                        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
                        (
                            "重复进站",
                            卡号,
                            旧["进站事件编号"],
                            json.dumps(
                                {"旧开腿": 旧["开腿键"], "新进站": 事件编号},
                                ensure_ascii=False,
                            ),
                            处理时,
                        ),
                    )
                    报告["旁路"] += 1
                    报告["明细"].append(
                        {"事件编号": 旧["进站事件编号"], "命运": "旁路-重复进站"}
                    )

                开腿键 = f"腿-{事件编号}"
                conn.execute(
                    """INSERT INTO 开腿账(开腿键,卡号,进站事件编号,进站站点键,进站事件时,状态,更新处理时)
                       VALUES (?,?,?,?,?,'在途',?)""",
                    (开腿键, 卡号, 事件编号, 站点键, 事件时, 处理时),
                )
                conn.execute(
                    "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
                    ("已开腿", 事件编号),
                )
                报告["开腿"] += 1
                报告["明细"].append({"事件编号": 事件编号, "命运": "已开腿", "开腿键": 开腿键})
            else:
                开腿 = conn.execute(
                    "SELECT * FROM 开腿账 WHERE 卡号=? AND 状态='在途' ORDER BY 进站事件时 ASC LIMIT 1",
                    (卡号,),
                ).fetchone()
                if not 开腿:
                    conn.execute(
                        "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
                        ("已旁路", 事件编号),
                    )
                    conn.execute(
                        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
                        (
                            "出站孤儿",
                            卡号,
                            事件编号,
                            json.dumps(ev, ensure_ascii=False),
                            处理时,
                        ),
                    )
                    报告["旁路"] += 1
                    报告["明细"].append({"事件编号": 事件编号, "命运": "旁路-出站孤儿"})
                    continue

                if 是同站(开腿["进站站点键"], 站点键):
                    # 硬分叉：站距零只走禁对旁路，禁止写行程；与开腿关闭同事务同成败。
                    旁路键 = 同站禁对写出站(conn, 开腿, 事件编号, 站点键, 处理时)
                    报告["同站禁对"] += 1
                    报告["旁路"] += 1
                    报告["明细"].append(
                        {
                            "事件编号": 事件编号,
                            "命运": "旁路-同站禁对",
                            "旁路键": 旁路键,
                        }
                    )
                    continue

                行程键 = 配对.成对写出站(
                    conn, 开腿, 事件编号, 站点键, 事件时, 处理时
                )
                报告["成对"] += 1
                报告["明细"].append(
                    {"事件编号": 事件编号, "命运": "已成对", "行程键": 行程键}
                )

        if 水位:
            报告["超时旁路"] = 配对.扫缺腿超时(conn, 最大行程秒, 水位, 此刻())
            报告["旁路"] += 报告["超时旁路"]

        conn.execute(
            "INSERT INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
            (批次编号, 此刻(), json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
        return 报告
    except Exception:
        # 同站写闸/成对写闸任一笔失败：整体回滚，禁止旁路证与半截账残留
        conn.rollback()
        raise
    finally:
        conn.close()
