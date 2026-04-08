import os
import subprocess
import sys

# 软件打包配置
APP_NAME = "FiberRoutingPlanner"
ENTRY_POINT = "server.py"
DIST_DIR = "dist"

def build_exe():
    print(f"📦 开始将【智能光纤前勘系统】打包为独立可执行文件...")
    
    # 1. 确保安装了打包工具 PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("正在安装打包引擎 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. 构造打包命令
    # --onefile: 所有的东西压成一个 .exe / .app
    # --add-data: 把前端 HTML 和静态库也塞进去
    # --hidden-import: 确保 Flask 和其他依赖不丢失
    
    cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--onefile",
        "--windowed", # 隐藏黑窗口
        "--add-data", "static:static", # 打包静态网页目录
        "--add-data", "*.csv:.",       # 把数据表也打包进去（可选，建议外部放置）
        "--clean",
        ENTRY_POINT
    ]
    
    print(f"执行打包指令: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ 打包成功！")
        print(f"软件已生成在: {os.path.abspath(DIST_DIR)}")
    except Exception as e:
        print(f"❌ 打包失败: {e}")

if __name__ == "__main__":
    build_exe()
