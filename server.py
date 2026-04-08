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
# 核心逻辑 B：路网引擎初始化 (跨平台自适应)
# ==========================================
# 获取当前程序实际运行的目录（打包后为临时目录，开发时为代码目录）
if getattr(sys, 'frozen', False):
    current_runtime_dir = sys._MEIPASS
else:
    current_runtime_dir = os.path.dirname(os.path.abspath(__file__))

# 优先查找特定的本地绝对路径，如果不存在（比如在别人的 Windows 上），则切换到当前程序所在的目录
data_root = '/Users/jesspu/Downloads/前勘脚本打包'
if not os.path.exists(data_root):
    data_root = current_runtime_dir

os.chdir(data_root)
sys.path.append(data_root)

import demo_v4
# 全局挂载引擎
print(f"⏳ 正在初始化全局路网数据库 (数据路径: {data_root})...")
G_ENGINE = demo_v4.GeoSpatialEngine("7级AOI（末端网格）0204.csv", "合规的FAP设施点0202.csv")
R_ENGINE = demo_v4.FiberRoutingEngine(["中继段-1.CSV", "中继段-2.CSV"], ["传输网元查询-2026-02-10-1770716023730_1.csv", "传输网元查询-2026-02-10-1770716023730_2.csv"])
print("✅ 路网数据库已就绪。")

# 兼容打包后的静态资源路径
static_folder = os.path.join(current_runtime_dir, 'static')
app = Flask(__name__, static_folder=static_folder, static_url_path='')

@app.route('/')
def index():
    return app.send_static_file('index.html')

# ==========================================
# 核心逻辑 C：地址解析 (高德官方 API 引擎)
# ==========================================
AMAP_KEY = "5903c4fb3c71de0a925bed908ba5d8c1"

@app.route('/api/geocode', methods=['POST'])
def geocode():
    address = request.json.get('address')
    search_query = address
    if not any(city in address for city in ["深圳", "东莞", "惠州"]):
        search_query = "深圳市" + address
        
    params = {
        'key': AMAP_KEY,
        'address': search_query,
        'city': '深莞惠'
    }
    url = f"https://restapi.amap.com/v3/geocode/geo?{urllib.parse.urlencode(params)}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data['status'] == '1' and data['geocodes']:
                loc = data['geocodes'][0]['location'].split(',')
                lon_gcj, lat_gcj = float(loc[0]), float(loc[1])
                lon_wgs, lat_wgs = gcj02_to_wgs84(lon_gcj, lat_gcj)
                return jsonify({
                    "lon": lon_wgs,
                    "lat": lat_wgs,
                    "display_name": data['geocodes'][0]['formatted_address'],
                    "source": "AMap-GCJ02-To-WGS84"
                })
            else:
                return jsonify({"error": "高德地图未找到该地址"}), 404
    except Exception as e:
        return jsonify({"error": f"高德接口异常: {str(e)}"}), 500

# ==========================================
# 核心逻辑 D：研报生成模块
# ==========================================
def generate_markdown_report(data):
    SEP = "---"
    md = f"## 📝 1. 勘查全局概述\n\n"
    md += f"- **目标坐标**：`{data['query_coordinates']['lon']}, {data['query_coordinates']['lat']}`\n"
    aois = data.get('matched_aoi_geofence', [])
    md += f"- **命中网格**：`{' | '.join(aois) if aois else '未命中特定园区'}`\n"
    cands = data.get('fap_to_equipment_candidates', [])
    md += f"- **发现 FAP 点**：{len(cands)} 个候选接入点。\n\n{SEP}\n\n"
    
    for i, cand in enumerate(cands):
        md += f"### 🚀 [方案 {i+1} 详情：{cand['fap_name']}]\n"
        md += f"- **FAP 物理位置**：{cand['fap_physical_location']}\n"
        md += f"- **起步距离**：{cand['distance_to_query_point_meters']}米\n\n"
        
        def render_plans(plans, title_label):
            res = ""
            if isinstance(plans, list):
                for j, p in enumerate(plans):
                    res += f"\n#### {title_label}-{j+1}\n\n"
                    res += f"- **链路详情**：{p['jumps']}跳 | {p['distance_meters']}米 | 终点: {p['found_at_node']}\n\n"
                    res += "**📡 目标设备清单**：\n\n"
                    res += "| 网元名称 | 生命周期状态 |\n"
                    res += "| :--- | :--- |\n"
                    for eq in p.get('equipments_found', []):
                        n_clean = str(eq.get('网元名称','')).replace('\n', ' ').strip()
                        s_clean = str(eq.get('生命周期状态','')).replace('\n', ' ').strip()
                        res += f"| {n_clean} | {s_clean} |\n"
                    res += "\n"
            return res

        md += render_plans(cand.get('equipment_routing_plans', []), "🌟 子方案A (最近接入)")
        md += render_plans(cand.get('transmission_room_routing_plans', []), "🛡️ 子方案B (高可靠传输)")
        
        if i < len(cands) - 1:
            md += f"\n{SEP}\n\n"
            
    return md

@app.route('/api/plan', methods=['POST'])
def plan():
    try:
        data = request.json
        lon, lat = float(data['lon']), float(data['lat'])
        if not data.get('is_wgs84', False):
            lon, lat = gcj02_to_wgs84(lon, lat)
            
        net_type = data.get('type', 'PTN')
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
