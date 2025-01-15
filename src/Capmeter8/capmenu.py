import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QMenu, QMessageBox
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction #for context menu etc.

def test_menu(self,pos:QPoint):
    # Create a QMenu
    context_menu = QMenu(self)

    # Add actions to the context menu
    action1 = QAction("Action 1", self)
    action2 = QAction("Action 2", self)
    
    # Create a submenu
    submenu = QMenu("Submenu", self)
    sub_action1 = QAction("Sub Action 1", self)
    sub_action2 = QAction("Sub Action 2", self)
    submenu.addAction(sub_action1)
    submenu.addAction(sub_action2)

    # Add actions and submenu to the context menu
    context_menu.addAction(action1)
    context_menu.addAction(action2)
    context_menu.addMenu(submenu)

    # # Connect actions to slots
    # action1.triggered.connect(self.directFcnCall)
    # #action1.triggered.connect(lambda: self.action_triggered("Action 1"))
    # action2.triggered.connect(lambda: self.action_triggered("Action 2"))
    # sub_action1.triggered.connect(lambda: self.action_triggered("Sub Action 1"))
    # sub_action2.triggered.connect(lambda: self.action_triggered("Sub Action 2"))

    # Show the context menu at the cursor position
    context_menu.exec(self.button.mapToGlobal(pos))


if __name__ == "__main__":
    '''
    to show the layout of the context menu
    '''
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Testing app")
    window.resize(400, 300)
    # Create a mock QPushButton
    window.button = QPushButton("Right-click me", window)
    window.button.setGeometry(100, 100, 200, 50)

    # Set the context menu policy to CustomContextMenu
    window.button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    # **Replace test_menu with the actual context menu**
    window.button.customContextMenuRequested.connect(lambda pos: test_menu(window,pos))

    window.show()
    sys.exit(app.exec())