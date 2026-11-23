import React, { useState } from "react";
import { 取 } from "../api.js";

export default function 同站裁决() {
  const [进站事件编号, 设进号] = useState("");
  const [出站事件编号, 设出号] = useState("");
  const [进站站, 设进站] = useState("");
  const [出站站, 设出站] = useState("");
  const [果, 设果] = useState(null);
  const [讯, 设讯] = useState("");

  const 裁 = async () => {
    const 参 = new URLSearchParams();
    if (进站事件编号 && 出站事件编号) {
      参.set("进站事件编号", 进站事件编号);
      参.set("出站事件编号", 出站事件编号);
    } else {
      参.set("进站站", 进站站);
      参.set("出站站", 出站站);
    }
    try {
      设果(await 取(`/同站裁决?${参.toString()}`));
      设讯("");
    } catch (e) {
      设果(null);
      设讯(String(e.message || e));
    }
  };

  return (
    <div>
      <h1 className="题">同站裁决</h1>
      <p className="述">
        只读接口。全局架构=<strong>站距零禁对</strong>：进站站=出站站（站距零）不写行程，
        开腿关闭进旁路匣、两笔刷卡同票已旁路；异站则装载成对写行程。
      </p>
      <div className="行">
        <label>进站事件编号<input value={进站事件编号} onChange={(e) => 设进号(e.target.value)} /></label>
        <label>出站事件编号<input value={出站事件编号} onChange={(e) => 设出号(e.target.value)} /></label>
      </div>
      <div className="行">
        <label>进站站键<input value={进站站} onChange={(e) => 设进站(e.target.value)} placeholder="站A" /></label>
        <label>出站站键<input value={出站站} onChange={(e) => 设出站(e.target.value)} placeholder="站A" /></label>
      </div>
      <div className="行"><button onClick={裁}>裁决</button></div>
      {讯 && <p className="讯">{讯}</p>}
      {果 && (
        <table>
          <thead><tr><th>字段</th><th>值</th></tr></thead>
          <tbody>
            <tr><td>架构</td><td>{果.架构}</td></tr>
            <tr><td>进站站 → 出站站</td><td>{果.进站站} → {果.出站站}</td></tr>
            <tr><td>站距零标记</td><td>{果.站距零标记}</td></tr>
            <tr><td>命运</td><td>{果.命运}</td></tr>
            <tr><td>行程或旁路键</td><td>{果.行程或旁路键 || "—"}</td></tr>
            <tr><td>valid</td><td><span className={`徽章 ${果.valid ? "通" : "败"}`}>{果.valid ? "自洽" : "撕裂"}</span></td></tr>
            <tr><td>说明</td><td>{果.说明}</td></tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
