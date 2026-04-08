import os
import sys
import json
import urllib.request
import urllib.parse
import math
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
    # Using Nominatim for MVP. (WGS84 natively)
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
    
    # 图标和样式配置
    ROOM_ICON = "🏠"
    FAP_ICON = "🔌"
    
    for i, cand in enumerate(cands):
        md += f"## 🏆 方案 {i+1}：接入 {cand['fap_name']}\n"
        md += f"- **起步光交距离**：{cand['distance_to_query_point_meters']} 米\n"
        md += f"- **光交详细位置**：{cand['fap_physical_location']}\n\n"
        
        # 绝对最近
        plan_a = cand.get('equipment_routing_plan')
        if plan_a and plan_a.get('status') == 'success':
            md += f"### 🌟 [子方案 A：绝对最近接入]\n"
            md += f"- **跳数**：{plan_a['jumps']} 跳\n- **总距离**：{plan_a['distance_meters']} 米\n- **终点机房**：{plan_a['found_at_node']}\n\n"
            
            md += "```mermaid\ngraph LR\n"
            md += "    %% 全局样式定义\n"
            md += "    classDef default fill:#f9f9f9,stroke:#333,stroke-width:1px;\n"
            md += "    classDef fap fill:#e1f5fe,stroke:#01579b,stroke-width:2px;\n"
            md += "    classDef room fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;\n"
            md += "    linkStyle default stroke:#2ecc71,stroke-width:2px,color:#27ae60;\n\n"

            if plan_a['jumps'] == 0:
                md += f"    START((\"{FAP_ICON} 起点光交\")) -- 距离:0m\\n跳数:0跳 --> END(((\"{ROOM_ICON} 同机房直连\")))\n"
                md += "    class START fap;\n    class END room;\n"
            else:
                nodes = [plan_a['routing'].split('-(')[0]]
                for detail in plan_a.get('path_details', []):
                    nodes.append(detail['终端设施'] or detail['终端机房'] or "未知节点")
                
                for idx, detail in enumerate(plan_a.get('path_details', [])):
                    n1 = nodes[idx]
                    n2 = nodes[idx+1]
                    
                    # 彻底移除所有可能引起语法错误的符号
                    def clean_name(s):
                        import re
                        # 只保留中文、字母、数字
                        return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', str(s))
                    
                    n1_clean = clean_name(n1)
                    n2_clean = clean_name(n2)
                    
                    free = detail.get('空闲数量', '0')
                    total = detail.get('中继纤芯数量', '0')
                    dist = detail.get('长度', '0')
                    
                    md += f"    N{idx}A[\"{FAP_ICON if idx==0 else ROOM_ICON} {n1_clean}\"] -- {free}core_{dist}m --> N{idx+1}A[\"{ROOM_ICON} {n2_clean}\"]\n"
                    if idx == 0: md += f"    class N{idx}A fap;\n"
                    else: md += f"    class N{idx}A room;\n"
                    md += f"    class N{idx+1}A room;\n"
            md += "```\n\n"
            
            md += "**📡 目标设备清单：**\n\n| 设备名称 | 生命周期状态 |\n| :--- | :--- |\n"
            for eq in plan_a.get('equipments_found', []):
                md += f"| `{eq.get('网元名称','')}` | {eq.get('生命周期状态','')} |\n"
            md += "\n"
            
        # 传输机房
        plan_b = cand.get('transmission_room_routing_plan')
        if plan_b and plan_b.get('status') == 'success':
            md += f"### 🛡️ [子方案 B：高可靠传输机房接入]\n"
            md += f"- **跳数**：{plan_b['jumps']} 跳\n- **总距离**：{plan_b['distance_meters']} 米\n- **终点机房**：{plan_b['found_at_node']}\n\n"
            
            md += "```mermaid\ngraph LR\n"
            md += "    classDef default fill:#f9f9f9,stroke:#333,stroke-width:1px;\n"
            md += "    classDef fap fill:#e1f5fe,stroke:#01579b,stroke-width:2px;\n"
            md += "    classDef room fill:#fff3e0,stroke:#e65100,stroke-width:2px;\n"
            md += "    linkStyle default stroke:#2ecc71,stroke-width:2px,color:#27ae60;\n\n"

            if plan_b['jumps'] == 0:
                md += f"    START((\"{FAP_ICON} 起点光交\")) -- 距离:0m\\n跳数:0跳 --> END(((\"{ROOM_ICON} 同机房直连\")))\n"
                md += "    class START fap;\n    class END room;\n"
            else:
                nodes = [plan_b['routing'].split('-(')[0]]
                for detail in plan_b.get('path_details', []):
                    nodes.append(detail['终端设施'] or detail['终端机房'] or "未知节点")
                
                for idx, detail in enumerate(plan_b.get('path_details', [])):
                    n1 = nodes[idx]
                    n2 = nodes[idx+1]
                    
                    # 彻底移除所有可能引起语法错误的符号
                    def clean_name(s):
                        import re
                        # 只保留中文、字母、数字
                        return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', str(s))
                    
                    n1_clean = clean_name(n1)
                    n2_clean = clean_name(n2)
                    
                    free = detail.get('空闲数量', '0')
                    total = detail.get('中继纤芯数量', '0')
                    dist = detail.get('长度', '0')
                    
                    md += f"    N{idx}B[\"{FAP_ICON if idx==0 else ROOM_ICON} {n1_clean}\"] -- {free}core_{dist}m --> N{idx+1}B[\"{ROOM_ICON} {n2_clean}\"]\n"
                    if idx == 0: md += f"    class N{idx}B fap;\n"
                    else: md += f"    class N{idx}B room;\n"
                    md += f"    class N{idx+1}B room;\n"
            md += "```\n\n"
            
            md += "**📡 目标设备清单：**\n\n| 设备名称 | 生命周期状态 |\n| :--- | :--- |\n"
            for eq in plan_b.get('equipments_found', []):
                md += f"| `{eq.get('网元名称','')}` | {eq.get('生命周期状态','')} |\n"
            md += "\n"
            
        md += "---\n\n"
    return md

@app.route('/api/plan', methods=['POST'])
def plan():
    try:
        data = request.json
        lon = float(data['lon'])
        lat = float(data['lat'])
        is_gcj02 = data.get('is_gcj02', False)
        
        # 自动坐标系转换
        if is_gcj02:
            lon, lat = gcj02_to_wgs84(lon, lat)
            
        net_type = data.get('type', 'PTN')
        
        # 极速运算：只需 ~50ms，因为引擎在内存里！
        raw_result = demo_v4.find_fap_to_equipment_route(geo_engine, route_engine, lon, lat, net_type)
        
        # 生成 Markdown
        markdown_report = generate_markdown_report(raw_result)
        
        # 打印生成的 Mermaid 以便调试
        import re
        mermaids = re.findall(r'```mermaid\n(.*?)\n```', markdown_report, re.DOTALL)
        for m in mermaids:
            sys.stdout.write("DEBUG MERMAID START:\n")
            sys.stdout.write(m + "\n")
            sys.stdout.write("DEBUG MERMAID END\n")
            sys.stdout.flush()
        
        return jsonify({
            "raw_json": raw_result,
            "markdown": markdown_report
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # 监听 0.0.0.0 允许外部访问
    app.run(host='0.0.0.0', port=5001)
