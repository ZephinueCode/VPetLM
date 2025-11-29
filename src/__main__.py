import sys
import os

# 确保能找到 src 模块 (如果直接运行此文件)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from PyQt6.QtWidgets import QApplication
from src.pyqt_utils import DesktopPet

def main():
    # 创建应用实例
    app = QApplication(sys.argv)
    
    # 实例化桌宠
    # 默认大小 320x320
    pet = DesktopPet(target_size=(240, 240))
    
    # 显示窗口
    pet.show()
    
    print("Desktop Pet Started.")
    print("Right click on the pet to interact.")
    
    # 进入主事件循环
    sys.exit(app.exec())

if __name__ == "__main__":
    main()