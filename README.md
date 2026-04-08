# Fiber Routing Planner Web System 2.0

> 智能光纤路由前勘 Web 系统 - 双轨算法引擎版

本项目是一个全栈 Web 应用，旨在通过地理空间算法自动规划从目标位置到最近电信网元（PTN/OTN）的最优光纤跳纤路径。

## ✨ 核心特性

- **双轨寻路引擎**：同时计算“绝对最近接入”与“高可靠传输机房接入”两套方案。
- **智能地址解析**：集成 OpenStreetMap 自动转换地理位置为 WGS84 坐标。
- **交互式地图选点**：支持在地图上直接点击获取精确坐标。
- **极速响应**：路网拓扑全量驻留内存，查询响应时间 < 50ms。
- **可视化报表**：自动生成包含 Mermaid 拓扑图和资源明细表的前勘报告。

## 🛠️ 快速部署

### 1. 环境准备
确保系统已安装 Python 3.9+。

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 准备数据文件
将光缆资源数据（CSV格式）放置在项目根目录下（数据文件由于保密原因未包含在仓库中）。

### 4. 启动服务
```bash
python server.py
```
服务启动后，在浏览器访问：`http://localhost:5001`

## 📂 项目结构
- `server.py`: Flask 后端逻辑（包含坐标转换、Markdown生成、API接口）。
- `demo_v4.py`: 核心算法引擎（空间索引与路网寻路）。
- `static/index.html`: 前端交互界面（Tailwind CSS + Leaflet地图）。
