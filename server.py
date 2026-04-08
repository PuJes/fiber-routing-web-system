import os
import sys
import json
import urllib.request
import urllib.parse
import math
import re
from flask import Flask, request, jsonify

# ==========================================
# 核心逻辑 A：坐标系纠偏模块 (GCJ-02 -> WGS-84)
# ==========================================
def transformlat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transformlng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def gcj02_to_wgs84(lng, lat):
    dlat = transformlat(lng - 105.0, lat - 35.0)
    dlng = transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    mglat = lat + dlat
    mglng = lng + dlng
    return [lng * 2 - mglng, lat * 2 - mglat]

# ==========================================
# 核心逻辑 B：路网引擎初始化 (单例模式)
# ==========================================
os.chdir('/Users/jesspu/Downloads/前勘脚本打包')
sys.path.append('/Users/jesspu/Downloads/前勘脚本打包')

import demo_v4
# 全局挂载引擎，避免 API 每次请求都重新加载（加速 100 倍）
print("⏳ 正在初始化全局路网数据库...")
G_ENGINE = demo_v4.GeoSpatialEngine("7级AOI（末端网格）0204.csv", "合规的FAP设施点0202.csv")
R_ENGINE = demo_v4.FiberRoutingEngine(["中继段-1.CSV", "中继段-2.CSV"], ["传输网元查询-2026-02-10-1770716023730_1.csv", "传输网元查询-2026-02-10-1770716023730_2.csv"])
print("✅ 路网数据库已就绪。")

app = Flask(__name__, static_folder='/Users/jesspu/.openclaw/workspace/codes/fiber-routing-web/static', static_url_path='')

@app.route('/')
def index():
    return app.send_static_file('index.html')

# ==========================================
# 核心逻辑 C：地址解析 (带详细地址回显)
# ==========================================
@app.route('/api/geocode', methods=['POST'])
def geocode():
    address = request.json.get('address')
    # 使用 Nominatim 获取详细结构化地址 (WGS84)
    url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(address) + "&format=json&limit=1&addressdetails=1"
    req = urllib.request.Request(url, headers={'User-Agent': 'FiberRoutingPRO/5.3'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data:
                # 提取显示名称和坐标
                return jsonify({
                    "lon": float(data[0]['lon']),
                    "lat": float(data[0]['lat']),
                    "display_name": data[0]['display_name'], # 详细地址回显
                    "source": "WGS84"
                })
            else:
                return jsonify({"error": "未能在地图库中定位到该地址，请尝试更精确的名称"}), 404
    except Exception as e:
        return jsonify({"error": f"地图接口连接异常: {str(e)}"}), 500

# ==========================================
# 核心逻辑 D：研报生成模块
# ==========================================
def generate_markdown_report(data):
    md = f"## 📝 勘查全局概述\n\n"
    md += f"- **目标坐标**：`{data['query_coordinates']['lon']}, {data['query_coordinates']['lat']}`\n"
    aois = data.get('matched_aoi_geofence', [])
    md += f"- **命中网格**：`{' | '.join(aois) if aois else '未命中特定园区'}`\n"
    
    cands = data.get('fap_to_equipment_candidates', [])
    md += f"- **发现 FAP 点**：{len(cands)} 个候选接入点。\n\n---\n\n"
    
    for i, cand in enumerate(cands):
        md += f"## 🏆 方案 {i+1}：接入 {cand['fap_name']}\n"
        md += f"> 起步距离: {cand['distance_to_query_point_meters']}m | FAP 位置: {cand['fap_physical_location']}\n\n"
        
        def render_plans(plans, title_prefix):
            res = ""
            if isinstance(plans, list):
                for j, p in enumerate(plans):
                    res += f"### {title_prefix}-{j+1}\n"
                    res += f"- **详情**：{p['jumps']}跳 | {p['distance_meters']}米 | 终点: {p['found_at_node']}\n"
                    res += "  - **📡 目标设备清单**：\n"
                    res += "    | 网元名称 | 生命周期状态 |\n    | :--- | :--- |\n"
                    for eq in p.get('equipments_found', []):
                        res += f"    | `{eq.get('网元名称','')}` | {eq.get('生命周期状态','')} |\n"
                    res += "\n"
            return res

        md += render_plans(cand.get('equipment_routing_plans', []), "🌟 子方案A (最近)")
        md += render_plans(cand.get('transmission_room_routing_plans', []), "🛡️ 子方案B (可靠)")
        md += "---\n\n"
    return md

@app.route('/api/plan', methods=['POST'])
def plan():
    try:
        data = request.json
        lon = float(data['lon'])
        lat = float(data['lat'])
        
        # 判断来源，若是高德点击(GCJ-02)，则执行纠偏
        is_wgs84 = data.get('is_wgs84', False)
        if not is_wgs84:
            lon, lat = gcj02_to_wgs84(lon, lat)
            
        net_type = data.get('type', 'PTN')
        # 调用全局常驻引擎（极致响应）
        raw_result = demo_v4.find_fap_to_equipment_route(G_ENGINE, R_ENGINE, lon, lat, net_type)
        markdown_report = generate_markdown_report(raw_result)
        
        return jsonify({
            "raw_json": raw_result,
            "markdown": markdown_report
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
