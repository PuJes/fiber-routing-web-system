import os
import sys
import json
import urllib.request
import urllib.parse
import math
import re
from flask import Flask, request, jsonify

# GCJ-02 to WGS84 Conversion logic
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

# Important: Run within the backend script directory so CSV loading works
os.chdir('/Users/jesspu/Downloads/前勘脚本打包')
sys.path.append('/Users/jesspu/Downloads/前勘脚本打包')

print("⏳ 正在挂载空间引擎和路网引擎到内存，请稍候...（约需5秒）")
import demo_v4
geo_engine = demo_v4.GeoSpatialEngine("7级AOI（末端网格）0204.csv", "合规的FAP设施点0202.csv")
route_engine = demo_v4.FiberRoutingEngine(["中继段-1.CSV", "中继段-2.CSV"], ["传输网元查询-2026-02-10-1770716023730_1.csv", "传输网元查询-2026-02-10-1770716023730_2.csv"])
print("✅ 底层算法库和空间数据库加载完成！Web 服务启动。")

app = Flask(__name__, static_folder='/Users/jesspu/.openclaw/workspace/codes/fiber-routing-web/static', static_url_path='')

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/geocode', methods=['POST'])
def geocode():
    address = request.json.get('address')
    url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(address) + "&format=json&limit=1"
    req = urllib.request.Request(url, headers={'User-Agent': 'FiberRoutingApp/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data:
                return jsonify({"lon": float(data[0]['lon']), "lat": float(data[0]['lat']), "name": data[0]['display_name']})
            else:
                return jsonify({"error": "未找到地址"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generate_markdown_report(data):
    md = f"## 📝 1. 勘查全局概述\n\n"
    lon, lat = data['query_coordinates']['lon'], data['query_coordinates']['lat']
    md += f"- **目标坐标**：`{lon}, {lat}`\n"
    aois = data.get('matched_aoi_geofence', [])
    if aois:
        md += f"- **命中网格**：`{' | '.join(aois)}`\n"
    else:
        md += f"- **命中网格**：未命中专属园区网格，将按开放区域核算。\n"
    
    cands = data.get('fap_to_equipment_candidates', [])
    md += f"- **周边 FAP 资源**：系统在周边找到了 **{len(cands)} 个**候选接入点。\n\n---\n\n"
    
    for i, cand in enumerate(cands):
        md += f"## 🏆 方案 {i+1}：接入 {cand['fap_name']}\n"
        md += f"- **起步光交距离**：{cand['distance_to_query_point_meters']} 米\n"
        md += f"- **光交详细位置**：{cand['fap_physical_location']}\n\n"
        
        # 报告中简要列出子方案信息
        md += "### 🛰️ 候选路由方案列表\n\n"
        
        def render_plan_summary(p, label_prefix):
            res = f"- **{label_prefix}**：{p['jumps']}跳, {p['distance_meters']}米, 终点: {p['found_at_node']}\n"
            res += "  - **📡 目标设备**：\n"
            res += "    | 网元名称 | 生命周期状态 |\n    | :--- | :--- |\n"
            for eq in p.get('equipments_found', []):
                res += f"    | `{eq.get('网元名称','')}` | {eq.get('生命周期状态','')} |\n"
            res += "\n"
            return res

        plans_a = cand.get('equipment_routing_plans', [])
        if isinstance(plans_a, dict) and 'error' in plans_a: plans_a = []
        for j, p in enumerate(plans_a):
            md += render_plan_summary(p, f"🌟 子方案 A-{j+1} (最近接入)")
            
        plans_b = cand.get('transmission_room_routing_plans', [])
        if isinstance(plans_b, dict) and 'error' in plans_b: plans_b = []
        for j, p in enumerate(plans_b):
            md += render_plan_summary(p, f"🛡️ 子方案 B-{j+1} (传输机房)")
            
        md += "\n> 请查看下方交互式拓扑图了解全路径详情及各段资源分布。\n\n"
        md += "---\n\n"
    return md

@app.route('/api/plan', methods=['POST'])
def plan():
    try:
        data = request.json
        lon = float(data['lon'])
        lat = float(data['lat'])
        is_gcj02 = data.get('is_gcj02', False)
        
        if is_gcj02:
            lon, lat = gcj02_to_wgs84(lon, lat)
            
        net_type = data.get('type', 'PTN')
        
        import importlib
        importlib.reload(demo_v4)
        # 重新初始化引擎（因为 demo_v4 代码变了）
        g_engine = demo_v4.GeoSpatialEngine("7级AOI（末端网格）0204.csv", "合规的FAP设施点0202.csv")
        r_engine = demo_v4.FiberRoutingEngine(["中继段-1.CSV", "中继段-2.CSV"], ["传输网元查询-2026-02-10-1770716023730_1.csv", "传输网元查询-2026-02-10-1770716023730_2.csv"])
        
        raw_result = demo_v4.find_fap_to_equipment_route(g_engine, r_engine, lon, lat, net_type)
        markdown_report = generate_markdown_report(raw_result)
        
        return jsonify({
            "raw_json": raw_result,
            "markdown": markdown_report
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
