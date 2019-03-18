# Selector toolbar for FreeCAD
# Copyright (C) 2015, 2016 (as part of TabBar) triplus @ FreeCAD
# Copyright (C) 2017, 2018 triplus @ FreeCAD
#
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA

"""Selector toolbar for FreeCAD."""

import os
import FreeCADGui as Gui
import FreeCAD as App
from PySide import QtGui
from PySide import QtCore

actions = {}
mw = Gui.getMainWindow()
aMenu = QtGui.QAction(mw)
aMenu.setObjectName("SelectorToolbarMenuTb")
sMenu = QtGui.QMenu()
aMenu.setMenu(sMenu)
group = QtGui.QActionGroup(mw)
dList = "ArchWorkbench,PartDesignWorkbench"
path = os.path.dirname(__file__) + "/Resources/icons/"
p = App.ParamGet("User parameter:BaseApp/SelectorToolbar")
aMenuStatic = QtGui.QAction(mw)
aMenuStatic.setText("Menu")
aMenuStatic.setToolTip("Additional workbenches")
aMenuStatic.setObjectName("SelectorToolbarMenu")
aMenuStatic.setIcon(QtGui.QIcon(path + "SelectorToolbarMenu.svg"))
sMenuStatic = QtGui.QMenu()
aMenuStatic.setMenu(sMenuStatic)


def onSelector(a):
    """Activate workbench on selection."""
    Gui.doCommand('Gui.activateWorkbench("' + a.data() + '")')


def wbIcon(i):
    """Create workbench icon."""
    if str(i.find("XPM")) != "-1":
        icon = []
        for a in ((((i
                     .split('{', 1)[1])
                    .rsplit('}', 1)[0])
                   .strip())
                  .split("\n")):
            icon.append((a
                         .split('"', 1)[1])
                        .rsplit('"', 1)[0])
        icon = QtGui.QIcon(QtGui.QPixmap(icon))
    else:
        icon = QtGui.QIcon(QtGui.QPixmap(i))
    if icon.isNull():
        icon = QtGui.QIcon.fromTheme("freecad")
    return icon


def wbActions():
    """Create workbench actions."""
    wbList = Gui.listWorkbenches()
    for i in wbList:
        if i not in actions:
            action = QtGui.QAction(group)
            action.setCheckable(True)
            action.setText(wbList[i].MenuText)
            action.setData(i)
            try:
                action.setIcon(wbIcon(wbList[i].Icon))
            except:
                action.setIcon(QtGui.QIcon.fromTheme("freecad"))
            actions[i] = action


def onOrientationChanged():
    """Style buttons based on the toolbar orientation."""
    if tb.orientation() == QtCore.Qt.Orientation.Horizontal:
        for b in tb.findChildren(QtGui.QToolButton):
            b.setProperty("toolbar_orientation", "horizontal")
            b.style().polish(b)
    else:
        for b in tb.findChildren(QtGui.QToolButton):
            b.setProperty("toolbar_orientation", "vertical")
            b.style().polish(b)


def onStyle():
    """Manage the toolbutton style."""
    if p.GetString("Style") == "IconText":
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    elif p.GetString("Style") == "TextBelow":
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
    elif p.GetString("Style") == "Text":
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
    else:
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)


def selectorMenu():
    """Selector button with menu."""
    sMenu.clear()
    enabled = p.GetString("Enabled")
    partially = p.GetString("Partially")
    unchecked = p.GetString("Unchecked")
    position = p.GetString("Position")
    enabled = enabled.split(",")
    partially = partially.split(",")
    unchecked = unchecked.split(",")
    position = position.split(",")
    active = Gui.activeWorkbench().__class__.__name__
    l = []
    for i in partially:
        if i in actions:
            l.append(i)
    s = list(actions)
    s.sort()
    for i in s:
        if i not in l and i not in enabled and i not in unchecked:
            l.append(i)
    for i in l:
        sMenu.addAction(actions[i])
        sMenuStatic.addAction(actions[i])
    aMenu.setText(actions[active].text())
    aMenu.setIcon(actions[active].icon())


def onWorkbenchActivated():
    """Populate the selector toolbar."""
    tb.clear()
    wbActions()
    selectorMenu()
    static = p.GetBool("Static", 0)
    menu = p.GetString("Menu", "Front")
    enabled = p.GetString("Enabled", dList)
    enabled = enabled.split(",")
    active = Gui.activeWorkbench().__class__.__name__
    if active not in enabled:
        enabled.append(active)
    if menu == "Front" and not static:
        enabled.remove(active)
    elif menu == "End" and not static:
        enabled.remove(active)
    else:
        pass
    if menu == "Front":
        if static:
            tb.addAction(aMenuStatic)
            w = tb.widgetForAction(aMenuStatic)
            w.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        else:
            tb.addAction(aMenu)
            w = tb.widgetForAction(aMenu)
        w.setPopupMode(QtGui.QToolButton
                       .ToolButtonPopupMode
                       .InstantPopup)
    group.blockSignals(True)
    for i in enabled:
        for key in actions:
            if i == actions[key].data():
                a = actions[key]
                a.setChecked(False)
                tb.addAction(a)
                if active == a.data():
                    a.setChecked(True)
    group.blockSignals(False)
    if menu == "End":
        if static:
            tb.addAction(aMenuStatic)
            w = tb.widgetForAction(aMenuStatic)
            w.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        else:
            tb.addAction(aMenu)
            w = tb.widgetForAction(aMenu)
        w.setPopupMode(QtGui.QToolButton
                       .ToolButtonPopupMode
                       .InstantPopup)


def prefDialog():
    """Preferences dialog."""
    dialog = QtGui.QDialog(mw)
    dialog.resize(800, 450)
    dialog.setWindowTitle("Selector toolbar")
    layout = QtGui.QVBoxLayout()
    dialog.setLayout(layout)
    selector = QtGui.QListWidget(dialog)
    selector.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    btnClose = QtGui.QPushButton("Close", dialog)
    btnClose.setToolTip("Close the preferences dialog")
    btnClose.setDefault(True)
    btnUp = QtGui.QToolButton(dialog)
    btnUp.setToolTip("Move selected item up")
    btnUp.setArrowType(QtCore.Qt.UpArrow)
    btnDown = QtGui.QToolButton(dialog)
    btnDown.setToolTip("Move selected item down")
    btnDown.setArrowType(QtCore.Qt.DownArrow)
    l0 = QtGui.QVBoxLayout()
    g0 = QtGui.QGroupBox("Style:")
    g0.setLayout(l0)
    r0 = QtGui.QRadioButton("Icon", g0)
    r0.setObjectName("Icon")
    r0.setToolTip("Toolbar buttons with icon")
    r1 = QtGui.QRadioButton("Text", g0)
    r1.setObjectName("Text")
    r1.setToolTip("Toolbar buttons with text")
    r2 = QtGui.QRadioButton("Icon and text", g0)
    r2.setObjectName("IconText")
    r2.setToolTip("Toolbar buttons with icon and text")
    r3 = QtGui.QRadioButton("Text below the icon", g0)
    r3.setObjectName("TextBelow")
    r3.setToolTip("Toolbar buttons with icon and text below the icon")
    l0.addWidget(r0)
    l0.addWidget(r1)
    l0.addWidget(r2)
    l0.addWidget(r3)
    l1 = QtGui.QVBoxLayout()
    g1 = QtGui.QGroupBox("Menu:")
    g1.setLayout(l1)
    r4 = QtGui.QRadioButton("Disabled", g1)
    r4.setObjectName("Off")
    r4.setToolTip("Disable selector menu")
    r5 = QtGui.QRadioButton("Front", g1)
    r5.setObjectName("Front")
    r5.setToolTip("Selector menu at front")
    r6 = QtGui.QRadioButton("End", g1)
    r6.setObjectName("End")
    r6.setToolTip("Selector menu at end")
    c1 = QtGui.QCheckBox("Static")
    c1.setToolTip("Do not adapt selector menu to active workbench")
    l1.addWidget(r4)
    l1.addWidget(r5)
    l1.addWidget(r6)
    l1.addWidget(c1)
    l2 = QtGui.QHBoxLayout()
    l2.addWidget(btnUp)
    l2.addWidget(btnDown)
    l2.addStretch(1)
    l2.addWidget(btnClose)
    l3 = QtGui.QHBoxLayout()
    l3.addStretch()
    l4 = QtGui.QVBoxLayout()
    l4.addWidget(g0)
    l4.addWidget(g1)
    l4.addStretch()
    l4.insertLayout(0, l3)
    l5 = QtGui.QHBoxLayout()
    l5.addWidget(selector)
    l5.insertLayout(1, l4)
    layout.insertLayout(0, l5)
    layout.insertLayout(1, l2)

    def onAccepted():
        """Close dialog on button close."""
        dialog.done(1)

    def onFinished():
        """Delete dialog on close."""
        dialog.deleteLater()

    def onItemChanged(item=None):
        """Save workbench list state."""
        if item:
            selector.blockSignals(True)
            if item.data(50) == "Unchecked":
                item.setCheckState(QtCore.Qt.CheckState(1))
                item.setData(50, "Partially")
            elif item.data(50) == "Partially":
                item.setCheckState(QtCore.Qt.CheckState(2))
                item.setData(50, "Checked")
            else:
                item.setCheckState(QtCore.Qt.CheckState(0))
                item.setData(50, "Unchecked")
            selector.blockSignals(False)
        enabled = []
        partially = []
        unchecked = []
        for index in range(selector.count()):
            if selector.item(index).checkState() == QtCore.Qt.Checked:
                enabled.append(selector.item(index).data(32))
            elif selector.item(index).checkState() == QtCore.Qt.PartiallyChecked:
                partially.append(selector.item(index).data(32))
            else:
                unchecked.append(selector.item(index).data(32))
        p.SetString("Enabled", ",".join(enabled))
        p.SetString("Partially", ",".join(partially))
        p.SetString("Unchecked", ",".join(unchecked))
        onWorkbenchActivated()

    def onUp():
        """Save workbench position list."""
        currentIndex = selector.currentRow()
        if currentIndex != 0:
            selector.blockSignals(True)
            currentItem = selector.takeItem(currentIndex)
            selector.insertItem(currentIndex - 1, currentItem)
            selector.setCurrentRow(currentIndex - 1)
            selector.blockSignals(False)
            position = []
            for index in range(selector.count()):
                position.append(selector.item(index).data(32))
            p.SetString("Position", ",".join(position))
            onItemChanged()

    def onDown():
        """Save workbench position list."""
        currentIndex = selector.currentRow()
        if currentIndex != selector.count() - 1 and currentIndex != -1:
            selector.blockSignals(True)
            currentItem = selector.takeItem(currentIndex)
            selector.insertItem(currentIndex + 1, currentItem)
            selector.setCurrentRow(currentIndex + 1)
            selector.blockSignals(False)
            position = []
            for index in range(selector.count()):
                position.append(selector.item(index).data(32))
            p.SetString("Position", ",".join(position))
            onItemChanged()

    def onG0(r):
        """Set toolbar button style."""
        if r:
            for i in g0.findChildren(QtGui.QRadioButton):
                if i.isChecked():
                    p.SetString("Style", i.objectName())
            onStyle()
            onWorkbenchActivated()

    def onG1(r):
        """Manage the selector menu."""
        if r:
            for i in g1.findChildren(QtGui.QRadioButton):
                if i.isChecked():
                    p.SetString("Menu", i.objectName())
                    if i.objectName() == "Off":
                        c1.setEnabled(False)
                    else:
                        c1.setEnabled(True)
            onWorkbenchActivated()

    def onC1(c):
        """Manage the static mode."""
        if c:
            p.SetBool("Static", 1)
        else:
            p.SetBool("Static", 0)
        onWorkbenchActivated()

    enabled = p.GetString("Enabled", dList)
    unchecked = p.GetString("Unchecked")
    position = p.GetString("Position")
    enabled = enabled.split(",")
    unchecked = unchecked.split(",")
    position = position.split(",")
    s = list(actions)
    s.sort()
    for i in s:
        if i not in position:
            position.append(i)
    for i in position:
        if i in actions:
            item = QtGui.QListWidgetItem(selector)
            item.setText(actions[i].text())
            item.setIcon(actions[i].icon())
            item.setData(32, actions[i].data())
            if actions[i].data() in enabled:
                item.setCheckState(QtCore.Qt.CheckState(2))
                item.setData(50, "Checked")
            elif actions[i].data() in unchecked:
                item.setCheckState(QtCore.Qt.CheckState(0))
                item.setData(50, "Unchecked")
            else:
                item.setCheckState(QtCore.Qt.CheckState(1))
                item.setData(50, "Partially")
    style = p.GetString("Style")
    if style == "Text":
        r1.setChecked(True)
    elif style == "IconText":
        r2.setChecked(True)
    elif style == "TextBelow":
        r3.setChecked(True)
    else:
        r0.setChecked(True)
    menu = p.GetString("Menu", "Front")
    if menu == "Front":
        r5.setChecked(True)
    elif menu == "End":
        r6.setChecked(True)
    else:
        r4.setChecked(True)
        c1.setEnabled(False)
    static = p.GetBool("Static", 0)
    if static:
        c1.setChecked(True)
    r0.toggled.connect(onG0)
    r1.toggled.connect(onG0)
    r2.toggled.connect(onG0)
    r3.toggled.connect(onG0)
    r4.toggled.connect(onG1)
    r5.toggled.connect(onG1)
    r6.toggled.connect(onG1)
    c1.stateChanged.connect(onC1)
    btnUp.clicked.connect(onUp)
    btnDown.clicked.connect(onDown)
    selector.itemChanged.connect(onItemChanged)
    dialog.finished.connect(onFinished)
    btnClose.clicked.connect(onAccepted)
    return dialog


def onPreferences():
    """Open the preferences dialog."""
    dialog = prefDialog()
    dialog.show()


def accessoriesMenu():
    """Add selector toolbar preferences to accessories menu."""
    pref = QtGui.QAction(mw)
    pref.setText("Selector toolbar")
    pref.setObjectName("SelectorToolbar")
    pref.triggered.connect(onPreferences)
    try:
        import AccessoriesMenu
        AccessoriesMenu.addItem("SelectorToolbar")
    except ImportError:
        a = mw.findChild(QtGui.QAction, "AccessoriesMenu")
        if a:
            a.menu().addAction(pref)
        else:
            mb = mw.menuBar()
            actionAccessories = QtGui.QAction(mw)
            actionAccessories.setObjectName("AccessoriesMenu")
            actionAccessories.setIconText("Accessories")
            menu = QtGui.QMenu()
            actionAccessories.setMenu(menu)
            menu.addAction(pref)

            def addMenu():
                """Add accessories menu to the menu bar."""
                mb.addAction(actionAccessories)
                actionAccessories.setVisible(True)

            addMenu()
            mw.workbenchActivated.connect(addMenu)


def onClose():
    """Remove selector toolbar on FreeCAD close."""
    pathTB = "User parameter:BaseApp/Workbench/Global/Toolbar"
    pTB = App.ParamGet(pathTB)
    pTB.RemGroup("Selector")


def onStart():
    """Start selector toolbar."""
    start = False
    try:
        mw.mainWindowClosed
        mw.workbenchActivated
        global tb
        tb = mw.findChild(QtGui.QToolBar, "Selector")
        tb.orientationChanged
        start = True
    except AttributeError:
        pass
    if start:
        t.stop()
        t.deleteLater()
        onStyle()
        accessoriesMenu()
        onWorkbenchActivated()
        group.triggered.connect(onSelector)
        mw.mainWindowClosed.connect(onClose)
        mw.workbenchActivated.connect(onWorkbenchActivated)
        tb.orientationChanged.connect(onOrientationChanged)


def onPreStart():
    """Improve start reliability and maintain FreeCAD 0.16 support."""
    if App.Version()[1] < "17":
        onStart()
    else:
        if mw.property("eventLoop"):
            onStart()


t = QtCore.QTimer()
t.timeout.connect(onPreStart)
t.start(500)
