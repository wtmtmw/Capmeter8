import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QMenu, QMessageBox
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QActionGroup #for context menu etc.

def context_axes(parent,pos:QPoint):
    context_menu = QMenu(parent) # create a QMenu

    action_group = QActionGroup(parent) # for setting group mutual exclusivity behavior
    action_group.setExclusive(True)  # Ensure only one can be checked at a time

    # create and add items
    act0 = QAction('Ch0(Y) C', parent)
    act1 = QAction('Ch1(X) G', parent)
    act2 = QAction('Ch2 I', parent)
    act3 = QAction('Ch3 Aux', parent)
    act4 = QAction('Ch4 Ra', parent)
    actions = [act0, act1, act2, act3, act4]

    for act in actions:
        act.setCheckable(True)
        # if act is act0:
        #     act.setChecked(True)
        act.triggered.connect(lambda checked: parent.context_axes_Callback(parent.sender(),act))
        context_menu.addAction(act)
        action_group.addAction(act)
    #TODO - test it, 1/16/2025
    context_menu.exec(parent.sender().mapToGlobal(pos))


# def test_menu(self,pos:QPoint):
#     # Create a QMenu
#     context_menu = QMenu(self)

#     # Add actions to the context menu
#     action1 = QAction("Action 1", self)
#     action1.setCheckable(True)  # Make the action checkable
#     action1.setChecked(True)
#     action2 = QAction("Action 2", self)
    
#     # Create a submenu
#     submenu = QMenu("Submenu", self)
#     sub_action1 = QAction("Sub Action 1", self)
#     sub_action2 = QAction("Sub Action 2", self)
#     submenu.addAction(sub_action1)
#     submenu.addAction(sub_action2)

#     # Add actions and submenu to the context menu
#     context_menu.addAction(action1)
#     context_menu.addAction(action2)
#     context_menu.addMenu(submenu)

#     # Connect actions to slots
#     action1.triggered.connect(self.directFcnCall)
#     #action1.triggered.connect(lambda: self.action_triggered("Action 1"))
#     action2.triggered.connect(lambda: self.action_triggered("Action 2"))
#     sub_action1.triggered.connect(lambda: self.action_triggered("Sub Action 1"))
#     sub_action2.triggered.connect(lambda: self.action_triggered("Sub Action 2"))

#     # Show the context menu at the cursor position
#     context_menu.exec(self.sender().mapToGlobal(pos))


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
    window.button.customContextMenuRequested.connect(lambda pos: context_axes(window,pos))

    window.show()
    sys.exit(app.exec())