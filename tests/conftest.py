import os
import sys
import tempfile

# 全测试共享一个固定临时库路径（tempfile 默认目录按线程解析会导致跨线程库路径不一致）
_测试目录 = os.path.join(tempfile.gettempdir(), "gatetwin-pytest-db")
os.makedirs(_测试目录, exist_ok=True)
os.environ["数据目录"] = _测试目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
