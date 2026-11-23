import json

from app.db import 连接
from app.seed import 此刻
from app.modules.同站进出禁对 import 旁路原因, 是同站


def _载荷(文本: str) -> dict:
    try:
        return json.loads(文本 or "{}")
    except Exception:
        return {}


def 跑贯验() -> dict:
    """行程账与刷卡点互证：每笔已成对行程对应两笔已成对刷卡；旁路/开腿命运自洽。

    同站（站距零禁对）硬不变量：
    - 行程账不得出现进站站==出站站的行程行；
    - 同站禁对旁路票不得同时存在行程行（禁止旁路证+行程双落）；
    - 同站禁对票两笔刷卡命运同票=已旁路、开腿=已旁路。
    """
    conn = 连接()
    try:
        问题 = []
        刷卡数 = conn.execute("SELECT COUNT(*) FROM 刷卡点").fetchone()[0]
        行程 = conn.execute("SELECT * FROM 行程账 WHERE 状态='已成对'").fetchall()
        开腿数 = conn.execute("SELECT COUNT(*) FROM 开腿账 WHERE 状态='在途'").fetchone()[0]
        旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

        for t in 行程:
            进 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["进站事件编号"],)
            ).fetchone()
            出 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["出站事件编号"],)
            ).fetchone()
            if not 进 or not 出:
                问题.append(f"行程{t['行程键']}缺刷卡点")
                continue
            if 是同站(t["进站站点键"], t["出站站点键"]):
                问题.append(f"行程{t['行程键']}站距零却写行程（违反同站禁对）")
            if 进["命运"] != "已成对" or 出["命运"] != "已成对":
                问题.append(f"行程{t['行程键']}刷卡命运非已成对")
            if 进["行程键"] != t["行程键"] or 出["行程键"] != t["行程键"]:
                问题.append(f"行程{t['行程键']}刷卡行程键不一致")
            if 进["卡号"] != t["卡号"] or 出["卡号"] != t["卡号"]:
                问题.append(f"行程{t['行程键']}卡号不一致")
            if 进["方向"] != "进站" or 出["方向"] != "出站":
                问题.append(f"行程{t['行程键']}方向不配对")

        # 同站禁对旁路逐票回证：禁双落、命运同票、开腿已关闭
        同站旁路 = conn.execute(
            "SELECT * FROM 旁路匣 WHERE 原因=?", (旁路原因,)
        ).fetchall()
        for b in 同站旁路:
            载荷 = _载荷(b["载荷"])
            进号 = 载荷.get("进站事件编号", "")
            双落 = conn.execute(
                "SELECT 1 FROM 行程账 WHERE 进站事件编号=? AND 出站事件编号=?",
                (进号, b["事件编号"]),
            ).fetchone()
            if 双落:
                问题.append(f"旁路{b['编号']}同站票旁路证与行程行双落")
            for 号 in (进号, b["事件编号"]):
                刷 = conn.execute(
                    "SELECT * FROM 刷卡点 WHERE 事件编号=?", (号,)
                ).fetchone()
                if 刷 is None:
                    问题.append(f"旁路{b['编号']}缺刷卡点{号}")
                elif 刷["命运"] != "已旁路":
                    问题.append(f"旁路{b['编号']}刷卡{号}命运未同票旁路")
            腿 = conn.execute(
                "SELECT * FROM 开腿账 WHERE 进站事件编号=?", (进号,)
            ).fetchone()
            if 腿 is not None and 腿["状态"] != "已旁路":
                问题.append(f"旁路{b['编号']}开腿未关闭为已旁路")

        成对刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已成对'"
        ).fetchone()[0]
        if 成对刷 != len(行程) * 2:
            问题.append(f"已成对刷卡{成对刷} ≠ 行程{len(行程)}×2")

        开腿刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已开腿'"
        ).fetchone()[0]
        if 开腿刷 != 开腿数:
            问题.append(f"已开腿刷卡{开腿刷} ≠ 在途开腿{开腿数}")

        通过 = 1 if not 问题 else 0
        说明 = "行程账与刷卡点互证通过" if 通过 else "；".join(问题)[:800]
        conn.execute(
            """INSERT INTO 行程贯验(时刻,刷卡数,行程数,开腿数,旁路数,是否通过,说明)
               VALUES (?,?,?,?,?,?,?)""",
            (此刻(), 刷卡数, len(行程), 开腿数, 旁路数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "刷卡数": 刷卡数,
            "行程数": len(行程),
            "开腿数": 开腿数,
            "旁路数": 旁路数,
            "说明": 说明,
            "问题": 问题,
        }
    finally:
        conn.close()
