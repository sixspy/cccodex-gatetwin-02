"""同站裁决只读接口。

给定进站/出站站点键（或两笔刷卡事件编号），回答同站关系硬分叉下的命运：
- 站距零（站点键相等）→ 同站禁对：不写行程、开腿关闭进旁路匣（原因=同站禁对），
  两笔刷卡命运同票=已旁路；
- 站距非零 → 装载成对路径：写行程账、两笔刷卡=已成对。

接口纯只读，不产生任何写动作。
"""

import json

from app.modules.同站进出禁对 import 架构 as 同站架构, 旁路原因, 是同站


def _载荷(文本: str) -> dict:
    try:
        return json.loads(文本 or "{}")
    except (TypeError, ValueError):
        return {}


def _裁决键(进站事件编号: str, 出站事件编号: str) -> str:
    return f"旁路-{进站事件编号}-{出站事件编号}"


def 裁决(
    conn,
    进站站: str = "",
    出站站: str = "",
    进站事件编号: str = "",
    出站事件编号: str = "",
) -> dict:
    """返回同站裁决视图。

    键：进站站 / 出站站 / 站距零标记 / 命运 / 行程或旁路键 / valid / 架构 / 说明。
    给了事件编号时，回库核对该票实际落地形态（行程行或旁路证），并以 valid 表示
    实际库态与选定架构口径是否一致。
    """
    进刷 = None
    出刷 = None
    if 进站事件编号:
        进刷 = conn.execute(
            "SELECT * FROM 刷卡点 WHERE 事件编号=?", (进站事件编号,)
        ).fetchone()
    if 出站事件编号:
        出刷 = conn.execute(
            "SELECT * FROM 刷卡点 WHERE 事件编号=?", (出站事件编号,)
        ).fetchone()

    # 站点键以显式入参优先；缺省时从刷卡点回取
    进站站 = 进站站 or (进刷["站点键"] if 进刷 else "")
    出站站 = 出站站 or (出刷["站点键"] if 出刷 else "")
    站距零 = 1 if 是同站(进站站, 出站站) else 0

    行程键 = ""
    旁路键 = ""
    实际命运 = ""
    问题 = []

    if 站距零:
        命运 = "同站禁对-已旁路"
        if 进站事件编号 and 出站事件编号:
            旁路键 = _裁决键(进站事件编号, 出站事件编号)
            证 = None
            for r in conn.execute(
                "SELECT * FROM 旁路匣 WHERE 原因=? AND 事件编号=?",
                (旁路原因, 出站事件编号),
            ):
                if _载荷(r["载荷"]).get("旁路键") == 旁路键:
                    证 = r
                    break
            # 同站口径下库中绝不允许出现该票行程行
            双落行程 = conn.execute(
                "SELECT 1 FROM 行程账 WHERE 进站事件编号=? AND 出站事件编号=?",
                (进站事件编号, 出站事件编号),
            ).fetchone()
            if 双落行程:
                问题.append("站距零却落行程行（禁对口径被违反）")
            if not 证:
                问题.append("缺同站禁对旁路证")
            else:
                实际命运 = 证["原因"]
            if 进刷 and 进刷["命运"] != "已旁路":
                问题.append("进站刷卡命运未随开腿同票旁路")
            if 出刷 and 出刷["命运"] != "已旁路":
                问题.append("出站刷卡命运未旁路")
            开腿 = conn.execute(
                "SELECT * FROM 开腿账 WHERE 进站事件编号=?", (进站事件编号,)
            ).fetchone()
            if 开腿 and 开腿["状态"] != "已旁路":
                问题.append("开腿未关闭为已旁路")
        else:
            实际命运 = 命运
    else:
        命运 = "异站成对-已成对"
        if 进站事件编号 and 出站事件编号:
            行 = conn.execute(
                "SELECT * FROM 行程账 WHERE 进站事件编号=? AND 出站事件编号=?",
                (进站事件编号, 出站事件编号),
            ).fetchone()
            if 行:
                行程键 = 行["行程键"]
                实际命运 = 行["状态"]
            else:
                问题.append("异站票缺行程行")
            for 刷, 向 in ((进刷, "进站"), (出刷, "出站")):
                if 刷 is None:
                    问题.append(f"缺{向}刷卡点")
                elif 刷["命运"] != "已成对":
                    问题.append(f"{向}刷卡命运非已成对")
                elif 行 and 刷["行程键"] != 行["行程键"]:
                    问题.append(f"{向}刷卡行程键不一致")
        else:
            实际命运 = 命运

    return {
        "架构": 同站架构,
        "进站站": 进站站,
        "出站站": 出站站,
        "站距零标记": 站距零,
        "命运": 实际命运 or 命运,
        "预期命运": 命运,
        "行程键": 行程键,
        "旁路键": 旁路键,
        "行程或旁路键": 行程键 or 旁路键,
        "valid": 1 if not 问题 else 0,
        "说明": "；".join(问题) if 问题 else "同站裁决口径自洽",
    }
