import csv
import time
import math
import heapq
import json
from collections import defaultdict, deque
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

# ==========================================
# 引擎一：地理空间引擎 (AOI 围栏 & FAP 最近邻计算)
# ==========================================
class GeoSpatialEngine:
    def __init__(self, aoi_csv_path, fap_csv_path):
        self.aoi_names = []
        self.aoi_polygons = []
        self.aoi_tree = None
        self.fap_points = [] 

        print("-" * 50)
        print("开始初始化 GeoSpatialEngine 空间引擎...")
        self._load_aoi_data(aoi_csv_path)
        self._build_aoi_index()
        self._load_fap_data(fap_csv_path)
        print("空间引擎初始化完毕！")
        print("-" * 50)

    def _load_aoi_data(self, csv_file_path):
        print(f"--> [AOI] 正在加载围栏数据: {csv_file_path}")
        start_time = time.time()
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            try: next(reader) 
            except StopIteration: return

            for row_num, row in enumerate(reader, start=2):
                try:
                    name = row[1].strip()
                    coords_str = row[2].strip()
                    if not name or not coords_str: continue
                        
                    points_str = coords_str.split(';')
                    coords = [tuple(map(float, p.split(','))) for p in points_str if p]
                    
                    if len(coords) >= 3:
                        poly = Polygon(coords)
                        if poly.is_valid:
                            self.aoi_polygons.append(poly)
                            self.aoi_names.append(name)
                        else:
                            fixed_poly = poly.buffer(0)
                            if fixed_poly.is_valid:
                                self.aoi_polygons.append(fixed_poly)
                                self.aoi_names.append(name)
                except IndexError: pass
                except Exception as e:
                    print(f"  [AOI 警告] 第 {row_num} 行解析失败: {e}")

        print(f"    成功加载 {len(self.aoi_polygons)} 个围栏。耗时: {time.time() - start_time:.2f} 秒。")

    def _build_aoi_index(self):
        start_time = time.time()
        self.aoi_tree = STRtree(self.aoi_polygons)
        print(f"--> [AOI] 空间索引构建完成！耗时: {time.time() - start_time:.4f} 秒。")

    def match_geofence(self, lon, lat):
        target_point = Point(lon, lat)
        possible_indices = self.aoi_tree.query(target_point)
        if len(possible_indices) == 0:
            return []
        matched_names = []
        for idx in possible_indices:
            if self.aoi_polygons[idx].contains(target_point):
                matched_names.append(self.aoi_names[idx])
        return matched_names

    def _load_fap_data(self, csv_file_path):
        print(f"--> [FAP] 正在加载设施点数据: {csv_file_path}")
        start_time = time.time()
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            try: next(reader)
            except StopIteration: return
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    if len(row) < 9: continue
                    name = row[1].strip()
                    lon_str = row[2].strip()
                    lat_str = row[3].strip()
                    physical_loc = row[7].strip()
                    grid = row[8].strip()
                    
                    if not name or not lon_str or not lat_str: continue
                        
                    self.fap_points.append({
                        'name': name,
                        'lon': float(lon_str),
                        'lat': float(lat_str),
                        'physical_loc': physical_loc,
                        'grid': grid
                    })
                except Exception as e:
                    print(f"  [FAP 警告] 第 {row_num} 行解析失败: {e}")
        print(f"    成功加载 {len(self.fap_points)} 个FAP设施点。耗时: {time.time() - start_time:.2f} 秒。")

    @staticmethod
    def _haversine_distance(lon1, lat1, lon2, lat2):
        R = 6371000 
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def find_nearest_faps(self, lon, lat, top_k=3):
        if not self.fap_points: return []
        def fap_with_distance():
            for fap in self.fap_points:
                dist = self._haversine_distance(lon, lat, fap['lon'], fap['lat'])
                yield {**fap, 'distance': dist}
        return heapq.nsmallest(top_k, fap_with_distance(), key=lambda x: x['distance'])

    def query_location(self, lon, lat, top_k_fap=3):
        matched_aois = self.match_geofence(lon, lat)
        nearest_faps = self.find_nearest_faps(lon, lat, top_k=top_k_fap)
        return {
            'matched_aois': matched_aois,
            'nearest_faps': nearest_faps,
        }

# ==========================================
# 引擎二：光缆跳纤寻路引擎 (图论拓扑 + 网元设备关联)
# ==========================================
class FiberRoutingEngine:
    def __init__(self, relay_csv_files, ne_csv_files=None):
        self.graph = defaultdict(list)
        self.node_equipments = defaultdict(lambda: defaultdict(list))
        
        print("-" * 50)
        print("开始初始化 FiberRoutingEngine 跳纤方案生成引擎...")
        start_time = time.time()
        
        self._build_graph(relay_csv_files)
        
        if ne_csv_files:
            self._load_network_elements(ne_csv_files)
            
        print(f"引擎初始化完成！构建了 {len(self.graph)} 个网络节点。耗时: {time.time() - start_time:.2f} 秒。")
        print("-" * 50)

    def _determine_node_name(self, room_name, facility_name):
        room = str(room_name).strip() if room_name is not None else ""
        facility = str(facility_name).strip() if facility_name is not None else ""
        return room if room else facility

    def _build_graph(self, csv_files):
        for file_path in csv_files:
            print(f"--> [光缆拓扑] 正在加载中继段数据表: {file_path}")
            try:
                with open(file_path, mode='r', encoding='gb18030') as f:
                    reader = csv.DictReader(f)
                    for row_num, row in enumerate(reader, start=2):
                        try:
                            free_val = row.get('空闲数量')
                            free_str = str(free_val).strip() if free_val is not None else '0'
                            try: free_count = float(free_str) if free_str else 0.0
                            except ValueError: free_count = 0.0
                                
                            if free_count == 0: continue

                            node_start = self._determine_node_name(row.get('始端机房'), row.get('始端设施'))
                            node_end = self._determine_node_name(row.get('终端机房'), row.get('终端设施'))

                            if node_start and node_end and node_start != node_end:
                                edge_data = {
                                    "ID": row.get('ID', ''),
                                    "名称": row.get('名称', ''),
                                    "长度": row.get('长度', '0'),
                                    "空闲数量": row.get('空闲数量', '0'),
                                    "中继纤芯数量": row.get('中继纤芯数量', '0'),
                                    "业务状态": row.get('业务状态', ''),
                                    "始端机房": row.get('始端机房', ''),
                                    "终端机房": row.get('终端机房', ''),
                                    "始端设施": row.get('始端设施', ''),
                                    "终端设施": row.get('终端设施', ''),
                                    "关联光缆段": row.get('关联光缆段', '')
                                }
                                self.graph[node_start].append({'target': node_end, 'data': edge_data})
                                self.graph[node_end].append({'target': node_start, 'data': edge_data})
                        except Exception: pass
            except Exception as e:
                print(f"读取文件 {file_path} 时发生严重错误: {e}")

    def _load_network_elements(self, csv_files):
        """解析网元CSV表，使用原生 CSV 库读取并挂载"""
        for file_path in csv_files:
            print(f"--> [网元设备] 正在加载网元数据表: {file_path}")
            f = None
            try:
                try:
                    f = open(file_path, mode='r', encoding='utf-8-sig')
                    reader = csv.DictReader(f)
                    next(reader, None) 
                    f.seek(0)
                    reader = csv.DictReader(f)
                except UnicodeDecodeError:
                    if f: f.close()
                    f = open(file_path, mode='r', encoding='gb18030')
                    reader = csv.DictReader(f)

                valid_count = 0
                for row_num, row in enumerate(reader, start=2):
                    try:
                        lifecycle = str(row.get('生命周期状态', '')).strip()
                        network_type = str(row.get('所属网络', '')).strip().upper()
                        room = str(row.get('所属机房', '')).strip()
                        ne_name = str(row.get('网元名称', '')).strip()
                        
                        if "退网" in lifecycle: continue
                        if not network_type or network_type == "PON": continue
                        if not room: continue
                        if not ne_name: continue
                            
                        self.node_equipments[room][network_type].append({
                            "网元名称": ne_name,
                            "生命周期状态": lifecycle
                        })
                        
                        if room not in self.graph:
                            self.graph[room] = []
                            
                        valid_count += 1
                    except Exception:
                        pass
                print(f"    成功解析并挂载了 {valid_count} 个有效网元。")
            except Exception as e:
                print(f"读取网元文件 {file_path} 时发生严重错误: {e}")
            finally:
                if f: f.close()

    def generate_routing_plans_raw(self, start_node, max_plans=4):
        start_node = start_node.strip()
        if start_node not in self.graph:
            return {"error": f"未在网络中找到起点 [{start_node}] 或已无空闲芯数"}

        if "传输1" in start_node:
            return [{
                "routing": f"{start_node} (该节点即为汇聚机房)",
                "counts": 0,
                "distance": 0.0,
                "details": []
            }]

        queue = deque([(start_node, [start_node], [], {start_node})])
        results = []
        unique_node_paths = set() 

        while queue and len(results) < max_plans:
            curr_node, path_nodes, path_edges, visited = queue.popleft()
            for edge in self.graph[curr_node]:
                neighbor = edge['target']
                edge_data = edge['data']
                
                if neighbor not in visited:
                    new_path_nodes = path_nodes + [neighbor]
                    new_path_edges = path_edges + [edge_data]

                    if "传输1" in neighbor:
                        node_tuple = tuple(new_path_nodes)
                        if node_tuple not in unique_node_paths:
                            unique_node_paths.add(node_tuple)
                            results.append((new_path_nodes, new_path_edges))
                            if len(results) >= max_plans: break
                    else:
                        new_visited = visited.copy()
                        new_visited.add(neighbor)
                        queue.append((neighbor, new_path_nodes, new_path_edges, new_visited))

        output_plans = []
        for path_nodes, path_edges in results:
            total_distance = 0.0
            counts = len(path_edges)
            routing_str = path_nodes[0]
            
            for node, edge_data in zip(path_nodes[1:], path_edges):
                try: total_distance += float(edge_data['长度']) if edge_data['长度'] else 0.0
                except ValueError: pass
                
                free_count = str(edge_data['空闲数量']).strip() or "0"
                total_core = str(edge_data['中继纤芯数量']).strip() or "0"
                routing_str += f"-({free_count}/{total_core})->{node}"
            
            output_plans.append({
                "routing": routing_str,
                "counts": counts,
                "distance": round(total_distance, 2),
                "details": path_edges
            })

        if not output_plans:
            return {"error": "无法找到通往汇聚机房的空闲路由路径"}
        return output_plans

    def find_nearest_network_equipment(self, start_node, target_network_type, require_ts_room=False):
        start_node = start_node.strip()
        target_network_type = target_network_type.strip().upper()
        
        if start_node not in self.graph:
            return {"error": f"未在网络中找到起点 [{start_node}]"}
            
        queue = deque([(start_node, [start_node], [], 0, {start_node})])
        
        while queue:
            curr_node, path_nodes, path_edges, jumps, visited = queue.popleft()
            
            if curr_node in self.node_equipments:
                equip_dict = self.node_equipments[curr_node]
                if target_network_type in equip_dict and len(equip_dict[target_network_type]) > 0:
                    
                    if require_ts_room:
                        # 如果需要是传输机房，必须包含关键词
                        if not ("传输" in curr_node or "汇聚" in curr_node or "核心" in curr_node):
                            # 虽然有设备，但不是核心/传输机房，继续搜其他路径
                            pass
                        else:
                            total_distance = 0.0
                            for edge in path_edges:
                                try: total_distance += float(edge['长度']) if edge['长度'] else 0.0
                                except ValueError: pass
                                
                            if jumps == 0:
                                routing_str = f"{start_node} (目标网元就在起点机房内，跳数为0)"
                            else:
                                routing_str = path_nodes[0]
                                for node, edge_data in zip(path_nodes[1:], path_edges):
                                    free_count = str(edge_data['空闲数量']).strip() or "0"
                                    total_core = str(edge_data['中继纤芯数量']).strip() or "0"
                                    routing_str += f"-({free_count}/{total_core})->{node}"
                                    
                            return {
                                "status": "success",
                                "target_network_type": target_network_type,
                                "found_at_node": curr_node,
                                "jumps": jumps,
                                "distance_meters": round(total_distance, 2),
                                "routing": routing_str,
                                "equipments_found": equip_dict[target_network_type],
                                "path_details": path_edges
                            }
                    else:
                        total_distance = 0.0
                        for edge in path_edges:
                            try: total_distance += float(edge['长度']) if edge['长度'] else 0.0
                            except ValueError: pass
                            
                        if jumps == 0:
                            routing_str = f"{start_node} (目标网元就在起点机房内，跳数为0)"
                        else:
                            routing_str = path_nodes[0]
                            for node, edge_data in zip(path_nodes[1:], path_edges):
                                free_count = str(edge_data['空闲数量']).strip() or "0"
                                total_core = str(edge_data['中继纤芯数量']).strip() or "0"
                                routing_str += f"-({free_count}/{total_core})->{node}"
                                
                        return {
                            "status": "success",
                            "target_network_type": target_network_type,
                            "found_at_node": curr_node,
                            "jumps": jumps,
                            "distance_meters": round(total_distance, 2),
                            "routing": routing_str,
                            "equipments_found": equip_dict[target_network_type],
                            "path_details": path_edges
                        }
                    
            for edge in self.graph[curr_node]:
                neighbor = edge['target']
                edge_data = edge['data']
                
                if neighbor not in visited:
                    new_visited = visited.copy()
                    new_visited.add(neighbor)
                    queue.append((
                        neighbor,
                        path_nodes + [neighbor],
                        path_edges + [edge_data],
                        jumps + 1,
                        new_visited
                    ))
                    
        return {"error": f"寻路失败：在整个连通网络中未能找到可达的 [{target_network_type}] 网元设备。"}


# ==========================================
# 顶层调度器：统一调用接口
# ==========================================
def comprehensive_query(geo_engine, route_engine, lon, lat):
    print(f"\n开始综合评估坐标点: ({lon}, {lat})")
    start_time = time.time()
    
    geo_result = geo_engine.query_location(lon, lat, top_k_fap=3)
    matched_aois = geo_result['matched_aois']
    nearest_faps = geo_result['nearest_faps']
    
    final_output = {
        "query_coordinates": {"lon": lon, "lat": lat},
        "matched_aoi_geofence": matched_aois,
        "fap_routing_candidates": []
    }
    
    for i, fap in enumerate(nearest_faps, start=1):
        fap_name = fap['name']
        fap_physical_location = fap['physical_loc']
        fap_distance = fap['distance']
        
        # 将 FAP 物理点传入路网引擎寻找 4 个跳纤方案
        routing_plans = route_engine.generate_routing_plans_raw(fap_physical_location, max_plans=4)
        
        final_output["fap_routing_candidates"].append({
            "candidate_rank": i,
            "fap_name": fap_name,
            "fap_physical_location": fap_physical_location,
            "fap_grid": fap['grid'],
            "distance_to_query_point_meters": round(fap_distance, 2),
            "routing_plans": routing_plans
        })
        
    final_output["total_query_cost_ms"] = round((time.time() - start_time) * 1000, 2)
    return final_output


# ==========================================
# 测试与使用示例
# ==========================================

def find_fap_to_equipment_route(geo_engine, route_engine, lon, lat, target_network_type="OTN"):
    print(f"\n[业务场景 3：经纬度 -> 周边FAP -> 最近的 {target_network_type} 网元设备]")
    print(f"--> 开始评估坐标: ({lon}, {lat})")
    import time
    start_time = time.time()
    
    geo_result = geo_engine.query_location(lon, lat, top_k_fap=3)
    matched_aois = geo_result.get("matched_aois", [])
    nearest_faps = geo_result.get("nearest_faps", [])
    
    final_output = {
        "query_coordinates": {"lon": lon, "lat": lat},
        "target_network_type": target_network_type,
        "matched_aoi_geofence": matched_aois,
        "fap_to_equipment_candidates": []
    }
    
    for i, fap in enumerate(nearest_faps, start=1):
        fap_name = fap["name"]
        fap_physical_location = fap["physical_loc"]
        fap_distance = fap["distance"]
        
        # 1. 寻找绝对最近的设备
        nearest_route_result = route_engine.find_nearest_network_equipment(
            start_node=fap_physical_location, 
            target_network_type=target_network_type,
            require_ts_room=False
        )
        
        # 2. 寻找最近的传输/汇聚机房设备
        ts_room_route_result = route_engine.find_nearest_network_equipment(
            start_node=fap_physical_location, 
            target_network_type=target_network_type,
            require_ts_room=True
        )
        
        candidate_info = {
            "candidate_rank": i,
            "fap_name": fap_name,
            "fap_physical_location": fap_physical_location,
            "fap_grid": fap.get("grid", "未知"),
            "distance_to_query_point_meters": round(fap_distance, 2),
            "equipment_routing_plan": nearest_route_result, # 为了兼容老版本字段，保持这个为绝对最近
            "transmission_room_routing_plan": ts_room_route_result # 新增的传输机房最优方案
        }
        
        final_output["fap_to_equipment_candidates"].append(candidate_info)
        
    cost = (time.time() - start_time) * 1000
    print(f"--> [全链路寻址完毕，总耗时: {cost:.2f} 毫秒]")
    
    return final_output


if __name__ == "__main__":
    # 【文件路径配置】
    AOI_CSV = "7级AOI（末端网格）0204.csv"
    FAP_CSV = "合规的FAP设施点0202.csv"
    RELAY_CSVS = ["中继段-1.CSV", "中继段-2.CSV"]
    
    # 填入手动另存为 CSV 格式后的网元数据表路径
    NE_CSVS = [
        "传输网元查询-2026-02-10-1770716023730_1.csv", 
        "传输网元查询-2026-02-10-1770716023730_2.csv"
    ]
    
    # 1. 启动两台核心引擎
    geo_engine = GeoSpatialEngine(AOI_CSV, FAP_CSV)
    route_engine = FiberRoutingEngine(RELAY_CSVS, NE_CSVS)
    
    print("==================================================")
    print("所有系统准备就绪，开始执行任务...")
    print("==================================================")

    

    import sys
    import json
    
    if len(sys.argv) >= 3:
        lon = float(sys.argv[1])
        lat = float(sys.argv[2])
        target_type = sys.argv[3] if len(sys.argv) > 3 else "OTN"
        test_coords = [(lon, lat)]
    else:
        test_coords = [(114.36658, 22.71342)]  # 坪山万国
        target_type = "OTN"
    
    for lon, lat in test_coords:
        combined_result = find_fap_to_equipment_route(geo_engine, route_engine, lon, lat, target_type)
        print(json.dumps(combined_result, ensure_ascii=False, indent=4))
