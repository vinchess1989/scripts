"""
================================================================================
Ball Map Viewer
Version: 2.21.0 (True EDA Canvas Engine & Editor Suite)
================================================================================
Changelog:
- v2.0-v2.8: GraphicsView migration, DRC Engine, HTML Delegates, Zoom fixes.
- v2.9: Checkbox transparency fix, Master DRC select, Recent Files, Diff Pair UX.
- v2.10: 
  * FIX/DEBUG: Added OS-level bounding box telemetry to HTMLDelegate.
  * UX: Smart-Panning for Differential Pairs.
- v2.11: DIFF GUI non-modal implementation, zoom fixes, Delta column.
- v2.12: DIFF GUI Legend relocated, Clear/Reset Delta Colors, Session Tools.
- v2.13: DIFF GUI detached standalone window, Recent Files load dropdowns, zoom fixes.
- v2.14.1: DIFF GUI universal zoom, independent canvas loads, VDD/VSS reset default.
- v2.15: FIX: AnchorUnderMouse zoom. Diff defaults to gray for Delta visibility.
- v2.16:
  * FEATURE: Privacy Filter (Blur Button) added to Main and Diff GUIs.
  * FEATURE: Fully interactive Ball Map Editor added (Tools -> Editor).
  * EDITOR: Features staging container, Direct Swapping, Area Auto-placement.
  * EDITOR: Exports modified layout securely to strictly formatted Excel document.
- v2.17:
  * FIX: Re-opening Diff/Editor no longer crashes (RuntimeError safely caught).
  * FIX: Privacy Blur takes effect immediately (viewport update forced).
  * FIX: Taskbar icon correctly targets .ico file instead of .png.
  * EDITOR: Added full Undo/Redo stack for all layout modifications.
  * EDITOR: Added Save/Load DB functionality.
  * EDITOR: Added Search Box and Total Pins count to Unassigned Container.
- v2.18.1:
  * FIX: Safely wrap diff_pairs_list clear/add calls to prevent AttributeError on load.
  * FIX: Added missing toggle_privacy handler to Main GUI to prevent startup crash.
- v2.19.0:
  * UI: Removed checkboxes and 'Select/Deselect All' feature from the DRC window.
  * UI: DRC violations are now managed through standard selection.
- v2.20.0:
  * UI: Added visible resize handles (horizontal/vertical lines) to all splitters for better UX.
- v2.21.0:
  * FIX: DRC violation IDs are now unique per touch, fixing the count discrepancy in the UI and confirmation dialogs.
================================================================================
"""
__version__ = "2.21.0"

import sys
import os
import json
import re
import argparse
import ctypes
import copy
import colorsys
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QPushButton, QLineEdit, QLabel, QColorDialog,
                             QFileDialog, QComboBox, QMessageBox, QAbstractItemView,
                             QTextEdit, QDialog, QSplitter, QHeaderView, 
                             QCheckBox, QMenuBar, QToolBar, QFrame, QStyledItemDelegate, 
                             QStyle, QStyleOptionButton, QListWidget, QListWidgetItem, 
                             QMenu, QTabWidget, QSizePolicy, QTreeWidget, QTreeWidgetItem, 
                             QGraphicsView, QGraphicsScene, QGraphicsObject, QStyleOptionViewItem,
                             QGraphicsBlurEffect)
from PyQt6.QtGui import QColor, QBrush, QFont, QAction, QIcon, QCursor, QPen, QFontMetrics, QPainter, QTransform, QTextDocument, QPalette
from PyQt6.QtCore import Qt, QEvent, QTimer, QRectF, QRect, QSize, pyqtSignal

DEFAULT_CELL_BG = "#E0E0E0"
HEADER_BG = "#A0C0E0"
CANVAS_BG_DARK = "#2B2B2B"
CANVAS_BG_LIGHT = "#F8F9FA"

CELL_SIZE = 100 

VDD_PALETTE = ["#FFCCCC", "#FF9999", "#FF6666", "#FF3333", "#FF0000", "#CC0000", "#990000", "#FFB266", "#FF9933"]
VSS_PALETTE = ["#CCE5FF", "#99CCFF", "#66B2FF", "#3399FF", "#0080FF", "#0066CC", "#004C99", "#3333FF", "#0000CC"]


class PreferencesDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(300, 150)
        layout = QVBoxLayout(self)
        
        self.cb_circles = QCheckBox("Draw balls as circles (Dark Mode)")
        self.cb_circles.setChecked(getattr(parent, 'draw_circles', False))
        
        self.cb_adaptive = QCheckBox("Use adaptive font sizing")
        self.cb_adaptive.setChecked(getattr(parent, 'adaptive_font', True))
        
        layout.addWidget(self.cb_circles)
        layout.addWidget(self.cb_adaptive)
        
        btn_box = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.apply_prefs)
        btn_box.addStretch()
        btn_box.addWidget(btn_apply)
        layout.addLayout(btn_box)
        self.parent_window = parent

    def apply_prefs(self):
        self.parent_window.draw_circles = self.cb_circles.isChecked()
        self.parent_window.adaptive_font = self.cb_adaptive.isChecked()
        self.parent_window.apply_preferences()
        self.accept()


class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        try: return float(self.text()) < float(other.text())
        except ValueError: return self.text() < other.text()


class CheckboxDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        checked = index.data(Qt.ItemDataRole.UserRole)
        
        painter.fillRect(option.rect, QColor("#FFFFFF"))
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        opts = QStyleOptionButton()
        opts.state |= QStyle.StateFlag.State_On if checked else QStyle.StateFlag.State_Off
        opts.state |= QStyle.StateFlag.State_Enabled
        opts.rect = self.getCheckBoxRect(option)
        QApplication.style().drawControl(QStyle.ControlElement.CE_CheckBox, opts, painter)

    def getCheckBoxRect(self, option):
        style = QApplication.style()
        cb_size = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, option)
        return QRect(
            option.rect.x() + (option.rect.width() - cb_size) // 2,
            option.rect.y() + (option.rect.height() - cb_size) // 2,
            cb_size, cb_size
        )


class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, debug_mode=False):
        super().__init__(parent)
        self.debug_mode = debug_mode

    def paint(self, painter, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        
        painter.save()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml(options.text)
        
        if options.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(options.rect, options.palette.highlight())
            options.state &= ~QStyle.StateFlag.State_Selected 

        # Hide the default text when drawing the base item, but don't alter palette colors
        # (changing text/window colors to transparent removes checkbox borders on some styles)
        options.text = ""
        
        style = option.widget.style() if option.widget else QApplication.style()
        # Draw only the item panel/background first (avoid drawing the native checkbox here)
        try:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, options, painter)
        except Exception:
            # Fallback to full item draw if primitive not supported
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, options, painter)
        
        # Compute text rectangle but avoid overlapping the check indicator
        textRect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, options, option.widget)
        try:
            chkRect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, options, option.widget)
        except Exception:
            chkRect = QRect(0, 0, 0, 0)

        # If the text rect would overlap the checkbox indicator, shift it right
        left = textRect.left()
        if chkRect.isValid() and chkRect.right() + 6 > left:
            left = chkRect.right() + 6
            textRect.setLeft(left)
            textRect.setWidth(max(0, option.rect.right() - left))

        # Render the HTML content within textRect. Use a nested save/restore so we can
        # return the painter to the original coordinate system before drawing the checkbox.
        painter.save()
        painter.translate(textRect.left(), textRect.top() + (textRect.height() - doc.size().height()) / 2)
        clip = QRectF(0, 0, textRect.width(), textRect.height())
        doc.drawContents(painter, clip)
        painter.restore()

        # Debug output for painting coordinates to help trace floating checkbox issues
        if self.debug_mode:
            try:
                print(f"[DEBUG-HTMLDelegate.paint] optionRect={option.rect}, textRect={textRect}, chkRect={chkRect}")
            except Exception:
                pass

        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml(options.text)
        base_size = super().sizeHint(option, index)
        return QSize(base_size.width(), max(base_size.height(), int(doc.size().height()) + 4))

    def editorEvent(self, event, model, option, index):
        if self.debug_mode and event.type() == QEvent.Type.MouseButtonRelease:
            options = QStyleOptionViewItem(option)
            self.initStyleOption(options, index)
            style = option.widget.style() if option.widget else QApplication.style()
            # Use the check indicator subelement (SE_ItemViewItemCheckIndicator)
            ind_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, options, option.widget)
            
            print(f"\n--- [DEBUG-HTMLDelegate] Checkbox Click Telemetry ---")
            print(f"Row Text (stripped): {re.sub(r'<[^>]+>', '', options.text)}")
            print(f"Option Rect: X:{option.rect.x()} Y:{option.rect.y()} W:{option.rect.width()} H:{option.rect.height()}")
            print(f"Indicator Rect (OS calcs): X:{ind_rect.x()} Y:{ind_rect.y()} W:{ind_rect.width()} H:{ind_rect.height()}")
            print(f"State_Enabled: {bool(options.state & QStyle.StateFlag.State_Enabled)}")
            print(f"State_On (Checked): {bool(options.state & QStyle.StateFlag.State_On)}")
            print(f"-------------------------------------------------------")
            
        return super().editorEvent(event, model, option, index)


class DRCWindow(QWidget):
    """Embedded DRCWindow component (kept inside main file as requested).

    - No per-row checkboxes. Multi-selection (Ctrl+click) is used to pick violations
      to waive/un-waive via the buttons.
    - Category summary tooltips hold rule descriptions.
    - Emits `selectionChanged` with a dict of aggregated cell sets.
    """
    selectionChanged = pyqtSignal(dict)

    def __init__(self, parent=None, debug_mode=False):
        super().__init__(parent)
        self.parent = parent
        self.debug_mode = debug_mode

        self.drc_results = {}
        self.waived_violations = set()
        self.valid_diff_pairs = {}

        self.active_violation_cells = set()
        self.active_passing_cells = set()
        self.active_waived_cells = set()

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # DRC Scan tab
        drc_tab = QWidget()
        drc_lay = QVBoxLayout(drc_tab)
        drc_lay.setContentsMargins(0, 5, 0, 0)

        btn_row = QHBoxLayout()
        self.btn_export_report = QPushButton("💾 Export Report")
        self.btn_import_waivers = QPushButton("📥 Import Waivers")
        self.btn_export_waivers = QPushButton("📤 Export Waivers")
        self.btn_waive_selected = QPushButton("✓ Waive Selected")
        self.btn_unwaive_selected = QPushButton("↺ Un-waive Selected")

        btn_row.addWidget(self.btn_export_report)
        btn_row.addWidget(self.btn_import_waivers)
        btn_row.addWidget(self.btn_export_waivers)
        btn_row.addWidget(self.btn_waive_selected)
        btn_row.addWidget(self.btn_unwaive_selected)

        drc_lay.addLayout(btn_row)

        self.drc_tree = QTreeWidget()
        self.drc_tree.setHeaderHidden(True)
        self.drc_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.drc_tree.setAlternatingRowColors(True)
        drc_lay.addWidget(self.drc_tree)

        self.tabs.addTab(drc_tab, "DRC Scan")

        # Differential Pairs tab
        diff_tab = QWidget()
        diff_lay = QVBoxLayout(diff_tab)
        diff_lay.setContentsMargins(0, 5, 0, 0)
        self.diff_pairs_list = QListWidget()
        diff_lay.addWidget(self.diff_pairs_list)
        self.tabs.addTab(diff_tab, "Differential Pairs")

        layout.addWidget(self.tabs)

        # Message Console
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        # Connect signals
        self.drc_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_waive_selected.clicked.connect(self._on_waive_selected)
        self.btn_unwaive_selected.clicked.connect(self._on_unwaive_selected)
        self.btn_export_report.clicked.connect(self._on_export_report)
        self.btn_import_waivers.clicked.connect(self._on_import_waivers)
        self.btn_export_waivers.clicked.connect(self._on_export_waivers)

    def log(self, msg: str):
        self.console.append(f"> {msg}")

    def populate_tree(self, drc_results: dict):
        """Populate the DRC tree from drc_results dict (category -> {'pass':[], 'fail':[]}).

        Each leaf item stores:
          - UserRole: cells list
          - UserRole+1: state string ('pass'/'fail'/'waived')
          - UserRole+3: id string
        """
        self.drc_results = drc_results or {}
        self.drc_tree.clear()

        # Rule descriptions for tooltips (replaces Rules Info tab)
        rule_descriptions = {
            'Proximity Check': 'No CLK net can touch any VDD net in the 8 adjacent cells.',
            'Symmetry (Numbered)': 'If a net has _[NS]# suffix anywhere, it expects balls for ALL discovered numbered dies.',
            'Symmetry (Unnumbered)': 'If a net only has _N or _S, it must match between North and South.'
        }

        for category, data in self.drc_results.items():
            passes = data.get('pass', [])
            fails = data.get('fail', [])

            active_fails = []
            waived_items = []
            for f in fails:
                if f.get('id') in self.waived_violations:
                    waived_items.append(f)
                else:
                    active_fails.append(f)

            if active_fails:
                root_text = f"{category} (Pass: {len(passes)}, Fail: {len(active_fails)}, Waived: {len(waived_items)})"
            else:
                root_text = f"{category} (Pass: {len(passes)}, Fail: {len(active_fails)}, Waived: {len(waived_items)})"

            root_node = QTreeWidgetItem(self.drc_tree, [root_text])
            root_node.setToolTip(0, rule_descriptions.get(category, ''))
            root_node.setData(0, Qt.ItemDataRole.UserRole + 2, category)

            if active_fails:
                n_fail = QTreeWidgetItem(root_node, [f"Fail ({len(active_fails)})"])
                n_fail.setData(0, Qt.ItemDataRole.UserRole + 1, "fail")
                for f in active_fails:
                    item = QTreeWidgetItem(n_fail, [f.get('html', f.get('raw', ''))])
                    item.setToolTip(0, f"<html>{f.get('html','')}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, f.get('cells'))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, 'fail')
                    item.setData(0, Qt.ItemDataRole.UserRole + 3, f.get('id'))

            if waived_items:
                n_waived = QTreeWidgetItem(root_node, [f"Waived ({len(waived_items)})"])
                n_waived.setData(0, Qt.ItemDataRole.UserRole + 1, "waived")
                for w in waived_items:
                    item = QTreeWidgetItem(n_waived, [w.get('html', w.get('raw',''))])
                    item.setToolTip(0, f"<html>{w.get('html','')}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, w.get('cells'))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, 'waived')
                    item.setData(0, Qt.ItemDataRole.UserRole + 3, w.get('id'))

            if passes:
                n_pass = QTreeWidgetItem(root_node, [f"Pass ({len(passes)})"])
                n_pass.setData(0, Qt.ItemDataRole.UserRole + 1, "pass")
                for p in passes:
                    item = QTreeWidgetItem(n_pass, [p.get('html', p.get('raw',''))])
                    item.setToolTip(0, f"<html>{p.get('html','')}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, p.get('cells'))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, 'pass')

        self.drc_tree.expandToDepth(0)

    def _on_selection_changed(self):
        self.active_violation_cells.clear()
        self.active_passing_cells.clear()
        self.active_waived_cells.clear()

        def extract_cells(node, force_state=None):
            c = node.data(0, Qt.ItemDataRole.UserRole) or []
            s = force_state or node.data(0, Qt.ItemDataRole.UserRole + 1)
            if s == 'fail': self.active_violation_cells.update(c)
            elif s == 'pass': self.active_passing_cells.update(c)
            elif s == 'waived': self.active_waived_cells.update(c)
            for i in range(node.childCount()):
                extract_cells(node.child(i), s)

        for item in self.drc_tree.selectedItems():
            extract_cells(item)

        sel_info = {
            'fail': set(self.active_violation_cells),
            'pass': set(self.active_passing_cells),
            'waived': set(self.active_waived_cells)
        }
        self.selectionChanged.emit(sel_info)

    def _on_waive_selected(self):
        items_to_waive = []
        for item in self.drc_tree.selectedItems():
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == 'fail':
                item_id = item.data(0, Qt.ItemDataRole.UserRole + 3)
                if item_id: items_to_waive.append(item_id)
        if not items_to_waive:
            QMessageBox.information(self, "Waive", "No failed items selected.")
            return
        reply = QMessageBox.question(self, "Confirm Waiver", f"Are you sure you want to waive {len(items_to_waive)} violations?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.waived_violations.update(items_to_waive)
            self.populate_tree(self.drc_results)
            self.log(f"Waived {len(items_to_waive)} violations.")

    def _on_unwaive_selected(self):
        items_to_unwaive = []
        for item in self.drc_tree.selectedItems():
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == 'waived':
                item_id = item.data(0, Qt.ItemDataRole.UserRole + 3)
                if item_id: items_to_unwaive.append(item_id)
        if not items_to_unwaive:
            QMessageBox.information(self, "Un-waive", "No waived items selected.")
            return
        reply = QMessageBox.question(self, "Confirm Un-waive", f"Are you sure you want to un-waive {len(items_to_unwaive)} violations?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for item_id in items_to_unwaive:
                self.waived_violations.discard(item_id)
            self.populate_tree(self.drc_results)
            self.log(f"Un-waived {len(items_to_unwaive)} violations.")

    def _on_export_report(self):
        if not self.drc_results:
            QMessageBox.information(self, "Export", "No violations to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Violations", "", "Excel Files (*.xlsx)")
        if not file_path: return
        try:
            import pandas as pd
            data = []
            for i in range(self.drc_tree.topLevelItemCount()):
                rule_node = self.drc_tree.topLevelItem(i)
                rule_name = rule_node.data(0, Qt.ItemDataRole.UserRole + 2) or "General"
                for j in range(rule_node.childCount()):
                    state_node = rule_node.child(j)
                    state = state_node.data(0, Qt.ItemDataRole.UserRole + 1)
                    for k in range(state_node.childCount()):
                        item = state_node.child(k)
                        msg_html = item.text(0)
                        msg_clean = re.sub(r'<[^>]+>', '', msg_html)
                        cells = item.data(0, Qt.ItemDataRole.UserRole)
                        pins_str = ""
                        if cells:
                            try:
                                pins = [f"{self.parent.row_headers[r]}{self.parent.col_headers[c]}" for r, c in cells if 0 <= r < len(self.parent.row_headers) and 0 <= c < len(self.parent.col_headers)]
                                pins_str = ", ".join(pins)
                            except Exception:
                                pins_str = ""
                        data.append({"Category": rule_name, "Result": state.upper(), "Description": msg_clean, "Affected Cells": pins_str})
            pd.DataFrame(data).to_excel(file_path, index=False)
            self.log(f"Exported structured DRC tree to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export report:\n{str(e)}")

    def _on_import_waivers(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Waivers", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    self.waived_violations.update(data)
                self.populate_tree(self.drc_results)
                self.log(f"Imported waivers from {os.path.basename(file_path)}.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import waivers:\n{str(e)}")

    def _on_export_waivers(self):
        if not self.waived_violations:
            QMessageBox.information(self, "Export Waivers", "No waivers currently exist.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Waivers", "waivers.json", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(list(self.waived_violations), f, indent=4)
                self.log(f"Exported {len(self.waived_violations)} waivers.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export waivers:\n{str(e)}")


class HeaderItem(QGraphicsObject):
    def __init__(self, x, y, width, height, text, parent_view):
        super().__init__()
        self.rect = QRectF(0, 0, width, height)
        self.setPos(x, y)
        self.text = str(text)
        self.parent_view = parent_view
        self.setToolTip(self.text)
        
        self.font = QFont()
        self.font.setBold(True)
        self.font.setPointSize(24) 
        
    def boundingRect(self):
        return self.rect
        
    def paint(self, painter, option, widget):
        draw_circles = self.parent_view.draw_circles
        bg_col = QColor("#444444") if draw_circles else QColor(HEADER_BG)
        txt_col = QColor("white") if draw_circles else QColor("black")
        
        painter.fillRect(self.rect, bg_col)
        painter.setPen(QPen(QColor("#222222" if draw_circles else "gray"), 1))
        painter.drawRect(self.rect)
        
        painter.setPen(txt_col)
        painter.setFont(self.font)
        painter.drawText(self.rect, Qt.AlignmentFlag.AlignCenter, self.text)


class BallItem(QGraphicsObject):
    def __init__(self, r, c, net, pin, parent_view):
        super().__init__()
        self.r = r
        self.c = c
        self.net = net
        self.pin = pin
        self.parent_view = parent_view
        
        self.rect = QRectF(0, 0, CELL_SIZE, CELL_SIZE)
        self.setPos((c+1) * CELL_SIZE, (r+1) * CELL_SIZE) 
        
        self.setFlags(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        self.bg_color = QColor(DEFAULT_CELL_BG)
        self.is_net_checked = False
        self.highlight_color = None
        
        self.display_text = net.replace("_", "_\u200B")
        self.cached_font = None
        
        self.setToolTip(f"Pin: {pin}\nNet: {net}")

    def update_visuals(self, bg_color, is_checked, highlight):
        self.bg_color = QColor(bg_color)
        self.is_net_checked = is_checked
        self.highlight_color = highlight
        self.update()

    def boundingRect(self):
        return self.rect

    def paint(self, painter, option, widget):
        draw_circles = self.parent_view.draw_circles
        adaptive_font = self.parent_view.adaptive_font
        is_selected = self.isSelected()
        
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if draw_circles:
            shape_rect = self.rect.adjusted(2, 2, -2, -2)
            painter.setBrush(QBrush(self.bg_color))
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.drawEllipse(shape_rect)
            
            margin = int(CELL_SIZE * 0.05)
            text_rect = self.rect.adjusted(margin, margin, -margin, -margin)
        else:
            painter.fillRect(self.rect, self.bg_color)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#CCCCCC"), 1))
            painter.drawRect(self.rect)
            text_rect = self.rect.adjusted(4, 4, -4, -4)

        painter.setPen(QColor("black"))
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        
        if adaptive_font:
            if not self.cached_font:
                f = QFont(); f.setBold(True)
                current_pt = 32 
                f.setPointSize(current_pt)
                for pt in range(current_pt, 4, -1):
                    f.setPointSize(pt)
                    fm = QFontMetrics(f)
                    br = fm.boundingRect(text_rect.toRect(), flags, self.display_text)
                    if br.width() <= text_rect.width() and br.height() <= text_rect.height():
                        break
                self.cached_font = f
            painter.setFont(self.cached_font)
        else:
            f = QFont(); f.setBold(True); f.setPointSize(14)
            painter.setFont(f)
            
        painter.drawText(text_rect, flags, self.display_text)

        active_col = self.highlight_color
        
        if active_col:
            painter.setPen(QPen(QColor(active_col), 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if draw_circles: painter.drawEllipse(self.rect.adjusted(3, 3, -3, -3))
            else: painter.drawRect(self.rect.adjusted(3, 3, -3, -3))
            
            if is_selected or self.is_net_checked:
                painter.setPen(QPen(QColor("white" if draw_circles else "black"), 3))
                if draw_circles: painter.drawEllipse(self.rect.adjusted(8, 8, -8, -8))
                else: painter.drawRect(self.rect.adjusted(8, 8, -8, -8))
                
        elif is_selected or self.is_net_checked:
            painter.setPen(QPen(QColor("white" if draw_circles else "black"), 5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if draw_circles: painter.drawEllipse(self.rect.adjusted(3, 3, -3, -3))
            else: painter.drawRect(self.rect.adjusted(3, 3, -3, -3))


class EDA_Canvas(QGraphicsView):
    def __init__(self, parent_gui):
        super().__init__()
        self.parent_gui = parent_gui
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)

    def drawBackground(self, painter, rect):
        bg_col = CANVAS_BG_DARK if self.parent_gui.draw_circles else CANVAS_BG_LIGHT
        painter.fillRect(rect, QColor(bg_col))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if hasattr(self.parent_gui, 'handle_canvas_click'):
            self.parent_gui.handle_canvas_click(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            if hasattr(self.parent_gui, 'handle_area_assignment'):
                self.parent_gui.handle_area_assignment()

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            event.accept() 
            
            factor = 1.05 if event.angleDelta().y() > 0 else 0.95
            self.scale(factor, factor)
            
            if hasattr(self.parent_gui, 'sync_zoom_act') and getattr(self.parent_gui.sync_zoom_act, 'isChecked', lambda: False)():
                other_view = self.parent_gui.right_view if self == self.parent_gui.left_view else self.parent_gui.left_view
                center_pt = self.mapToScene(self.viewport().rect().center())
                other_view.setTransform(self.transform())
                other_view.centerOn(center_pt)
        else:
            super().wheelEvent(event)


class ComparisonDialog(QDialog):
    def __init__(self, parent_gui, debug_mode=False):
        super().__init__(None) 
        self.parent_gui = parent_gui
        self.debug_mode = debug_mode
        self.draw_circles = getattr(parent_gui, 'draw_circles', False)
        self.adaptive_font = getattr(parent_gui, 'adaptive_font', True)
        self._updating_checks = False
        self.is_blurred = False
        
        self.setWindowTitle(f"Ball Map Viewer v{__version__} - Diff Interface")
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "BallMapViewer.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1600, 900)
        
        self.old_records, self.old_map = None, None
        self.new_records, self.new_map = None, None
        self.old_meta, self.new_meta = ("Not Loaded", "0.0"), ("Not Loaded", "0.0")
        
        self.pan_active = False
        self.show_delta_colors = True
        
        self.grid_data_left, self.grid_data_right = [], []
        self.left_bg_colors, self.right_bg_colors = {}, {}
        self.diff_manual_colors_left, self.diff_manual_colors_right = {}, {}
        self.ball_items_left, self.ball_items_right = {}, {}
        
        self.diff_rows, self.diff_cols = 0, 0
        self.diff_net_state = {}
        self.default_diff_net_colors = {}
        self.report_highlights = {} 
        self.saved_views = {}
        self.view_counter = 1
        self.valid_diff_pairs = {}
        
        self.init_ui()

    def init_ui(self):
        base_layout = QVBoxLayout(self)
        base_layout.setContentsMargins(0, 0, 0, 0)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                width: 6px;
            }
        """)
        base_layout.addWidget(self.main_splitter)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        self.toolbar = QToolBar()
        
        self.pan_act = QAction("✋", self); self.pan_act.setToolTip("Pan Mode"); self.pan_act.setCheckable(True); self.pan_act.toggled.connect(self.toggle_pan); self.toolbar.addAction(self.pan_act)
        self.toggle_side_act = QAction("🗔", self); self.toggle_side_act.setToolTip("Toggle Sidebar"); self.toggle_side_act.triggered.connect(self.toggle_sidebar); self.toolbar.addAction(self.toggle_side_act)
        self.toolbar.addSeparator()
        
        self.sync_zoom_act = QAction("🔗 Sync Views", self); self.sync_zoom_act.setToolTip("Sync Views Zoom/Scroll"); self.sync_zoom_act.setCheckable(True); self.sync_zoom_act.setChecked(True)
        self.sync_zoom_act.toggled.connect(self.on_sync_toggled)
        self.toolbar.addAction(self.sync_zoom_act)
        
        self.btn_sync_zoom_in = QAction("🔍+", self); self.btn_sync_zoom_in.setToolTip("Zoom In (Both)"); self.btn_sync_zoom_in.triggered.connect(self.sync_zoom_in); self.toolbar.addAction(self.btn_sync_zoom_in)
        self.btn_sync_zoom_out = QAction("🔍-", self); self.btn_sync_zoom_out.setToolTip("Zoom Out (Both)"); self.btn_sync_zoom_out.triggered.connect(self.sync_zoom_out); self.toolbar.addAction(self.btn_sync_zoom_out)
        self.btn_sync_zoom_fit = QAction("⛶ Fit", self); self.btn_sync_zoom_fit.setToolTip("Fit to Screen (Both)"); self.btn_sync_zoom_fit.triggered.connect(self.fit_to_screen); self.toolbar.addAction(self.btn_sync_zoom_fit)
        
        self.toolbar.addSeparator()
        self.input_view_name = QLineEdit()
        self.input_view_name.setPlaceholderText("View Name...")
        self.input_view_name.setMaximumWidth(150)
        self.input_view_name.setText(f"Diff_View_{self.view_counter}")
        self.toolbar.addWidget(self.input_view_name)

        self.act_save_view = QAction("💾", self); self.act_save_view.setToolTip("Save Diff View"); self.act_save_view.triggered.connect(self.save_view); self.toolbar.addAction(self.act_save_view)

        self.combo_views = QComboBox()
        self.combo_views.setMaximumWidth(150)
        self.toolbar.addWidget(self.combo_views)

        self.act_load_view = QAction("📂", self); self.act_load_view.setToolTip("Load Selected Diff View"); self.act_load_view.triggered.connect(self.load_view); self.toolbar.addAction(self.act_load_view)
        
        self.toolbar.addSeparator()
        self.act_save_db = QAction("💾 DB", self); self.act_save_db.setToolTip("Save Diff Session (DB)"); self.act_save_db.triggered.connect(self.save_db); self.toolbar.addAction(self.act_save_db)
        self.act_load_db = QAction("📂 DB", self); self.act_load_db.setToolTip("Load Diff Session (DB)"); self.act_load_db.triggered.connect(self.load_db); self.toolbar.addAction(self.act_load_db)
        
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)
        
        self.btn_privacy = QAction("👁️ Privacy Blur", self)
        self.btn_privacy.setCheckable(True)
        self.btn_privacy.setToolTip("Toggle Privacy Filter")
        self.btn_privacy.toggled.connect(self.toggle_privacy)
        self.toolbar.addAction(self.btn_privacy)

        left_layout.addWidget(self.toolbar, 0) 

        titles_widget = QWidget()
        titles_layout = QHBoxLayout(titles_widget)
        titles_layout.setContentsMargins(0, 5, 0, 5)
        
        left_title_lyt = QVBoxLayout()
        left_local_tools = QHBoxLayout()
        
        self.btn_load_left = QPushButton("📂 Load Old Version")
        self.btn_load_left.clicked.connect(lambda: self.load_left_map())
        self.btn_left_recent = QPushButton("▼")
        self.btn_left_recent.setMaximumWidth(20)
        self.left_recent_menu = QMenu()
        self.btn_left_recent.setMenu(self.left_recent_menu)
        left_local_tools.addWidget(self.btn_load_left)
        left_local_tools.addWidget(self.btn_left_recent)
        
        self.btn_zoom_in_left = QPushButton("🔍+")
        self.btn_zoom_out_left = QPushButton("🔍-")
        self.btn_zoom_fit_left = QPushButton("⛶ Fit")
        self.btn_zoom_in_left.clicked.connect(lambda: self.left_view.scale(1.05, 1.05))
        self.btn_zoom_out_left.clicked.connect(lambda: self.left_view.scale(0.95, 0.95))
        self.btn_zoom_fit_left.clicked.connect(self.fit_left_view)
        
        left_local_tools.addWidget(self.btn_zoom_in_left)
        left_local_tools.addWidget(self.btn_zoom_out_left)
        left_local_tools.addWidget(self.btn_zoom_fit_left)
        
        self.lbl_sel_left = QLabel("0 cells selected")
        left_local_tools.addStretch(); left_local_tools.addWidget(self.lbl_sel_left)
        self.lbl_left_title = QLabel(f"<h3 style='text-align: center; margin:0; color: #444;'>Old Version: Not Loaded</h3>")
        left_title_lyt.addWidget(self.lbl_left_title)
        left_title_lyt.addLayout(left_local_tools)
        titles_layout.addLayout(left_title_lyt)

        right_title_lyt = QVBoxLayout()
        right_local_tools = QHBoxLayout()
        
        self.btn_load_right = QPushButton("📂 Load New Version")
        self.btn_load_right.clicked.connect(lambda: self.load_right_map())
        self.btn_right_recent = QPushButton("▼")
        self.btn_right_recent.setMaximumWidth(20)
        self.right_recent_menu = QMenu()
        self.btn_right_recent.setMenu(self.right_recent_menu)
        right_local_tools.addWidget(self.btn_load_right)
        right_local_tools.addWidget(self.btn_right_recent)
        
        self.btn_zoom_in_right = QPushButton("🔍+")
        self.btn_zoom_out_right = QPushButton("🔍-")
        self.btn_zoom_fit_right = QPushButton("⛶ Fit")
        self.btn_zoom_in_right.clicked.connect(lambda: self.right_view.scale(1.05, 1.05))
        self.btn_zoom_out_right.clicked.connect(lambda: self.right_view.scale(0.95, 0.95))
        self.btn_zoom_fit_right.clicked.connect(self.fit_right_view)
        
        right_local_tools.addWidget(self.btn_zoom_in_right)
        right_local_tools.addWidget(self.btn_zoom_out_right)
        right_local_tools.addWidget(self.btn_zoom_fit_right)
        
        self.lbl_sel_right = QLabel("0 cells selected")
        right_local_tools.addStretch(); right_local_tools.addWidget(self.lbl_sel_right)
        self.lbl_right_title = QLabel(f"<h3 style='text-align: center; margin:0; color: #444;'>New Version: Not Loaded</h3>")
        right_title_lyt.addWidget(self.lbl_right_title)
        right_title_lyt.addLayout(right_local_tools)
        titles_layout.addLayout(right_title_lyt)

        left_layout.addWidget(titles_widget, 0)

        self.grids_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.grids_splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                width: 6px;
            }
        """)
        
        self.left_scene = QGraphicsScene()
        self.left_view = EDA_Canvas(self)
        self.left_view.setScene(self.left_scene)
        self.left_scene.selectionChanged.connect(self.on_selection_changed)
        
        self.right_scene = QGraphicsScene()
        self.right_view = EDA_Canvas(self)
        self.right_view.setScene(self.right_scene)
        self.right_scene.selectionChanged.connect(self.on_selection_changed)
        
        self.left_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.left_view.customContextMenuRequested.connect(lambda pos: self.show_diff_context_menu(pos, 1))
        self.right_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.right_view.customContextMenuRequested.connect(lambda pos: self.show_diff_context_menu(pos, 2))
        
        self.grids_splitter.addWidget(self.left_view)
        self.grids_splitter.addWidget(self.right_view)
        left_layout.addWidget(self.grids_splitter, 1)
        
        self.main_splitter.addWidget(left_pane)

        self.right_pane = QWidget()
        right_layout = QVBoxLayout(self.right_pane)
        
        self.right_vert_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_vert_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                height: 6px;
            }
        """)
        
        # 1. Delta Report Panel
        report_widget = QWidget()
        rep_lay = QVBoxLayout(report_widget)
        rep_lay.setContentsMargins(0, 0, 0, 0)
        rep_lay.addWidget(QLabel("<b>Delta Report</b>"))
        
        legend_widget = QWidget()
        leg_lay = QHBoxLayout(legend_widget)
        leg_lay.setContentsMargins(0, 5, 0, 5)
        leg_lay.setSpacing(10)
        leg_lay.addLayout(self.create_legend_item("Unchanged", "#E0E0E0", "Pin exists in both versions with the identical net name."))
        leg_lay.addLayout(self.create_legend_item("Added", "#A9DFBF", "Pin did not exist (or was unassigned) in the older version, but exists in the newer version."))
        leg_lay.addLayout(self.create_legend_item("Removed", "#F5B7B1", "Pin existed in the older version, but is missing (or unassigned) in the newer version."))
        leg_lay.addLayout(self.create_legend_item("Modified", "#FAD7A1", "Pin exists in both versions, but the assigned net name has changed."))
        rep_lay.addWidget(legend_widget)

        self.report_list = QListWidget()
        self.report_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.report_list.itemClicked.connect(self.on_report_clicked)
        rep_lay.addWidget(self.report_list)

        report_btn_layout = QHBoxLayout()
        self.btn_rep_color = QPushButton("🎨 Highlight Selected")
        self.btn_rep_color.clicked.connect(self.highlight_report_items)
        self.btn_rep_clear = QPushButton("❌ Clear Highlight")
        self.btn_rep_clear.clicked.connect(self.clear_report_items)
        report_btn_layout.addWidget(self.btn_rep_color)
        report_btn_layout.addWidget(self.btn_rep_clear)
        rep_lay.addLayout(report_btn_layout)
        
        delta_bg_btn_layout = QHBoxLayout()
        self.btn_clear_delta = QPushButton("❌ Clear Delta Colors")
        self.btn_clear_delta.clicked.connect(self.clear_delta_colors)
        self.btn_reset_delta = QPushButton("🔄 Reset Delta Colors")
        self.btn_reset_delta.clicked.connect(self.reset_delta_colors)
        delta_bg_btn_layout.addWidget(self.btn_clear_delta)
        delta_bg_btn_layout.addWidget(self.btn_reset_delta)
        rep_lay.addLayout(delta_bg_btn_layout)
        
        self.right_vert_splitter.addWidget(report_widget)

        # 2. Nets Panel
        nets_widget = QWidget()
        net_lay = QVBoxLayout(nets_widget)
        net_lay.setContentsMargins(0, 10, 0, 0)
        net_lay.addWidget(QLabel("<b>Diff Nets Control</b>"))
        
        diff_bulk_layout = QHBoxLayout()
        self.act_sel_all = QPushButton("☑️"); self.act_sel_all.setMaximumWidth(40); self.act_sel_all.setToolTip("Select All Nets"); self.act_sel_all.clicked.connect(self.diff_select_all_visible); diff_bulk_layout.addWidget(self.act_sel_all)
        self.act_desel_all = QPushButton("☐"); self.act_desel_all.setMaximumWidth(40); self.act_desel_all.setToolTip("Deselect All"); self.act_desel_all.clicked.connect(self.diff_deselect_all); diff_bulk_layout.addWidget(self.act_desel_all)
        self.act_clear_all = QPushButton("❌"); self.act_clear_all.setMaximumWidth(40); self.act_clear_all.setToolTip("Clear Colors"); self.act_clear_all.clicked.connect(self.diff_clear_all_selections); diff_bulk_layout.addWidget(self.act_clear_all)
        self.act_color_chk = QPushButton("🎨"); self.act_color_chk.setMaximumWidth(40); self.act_color_chk.setToolTip("Color Checked"); self.act_color_chk.clicked.connect(self.color_checked_diff_nets); diff_bulk_layout.addWidget(self.act_color_chk)
        self.act_reset_diff_col = QPushButton("🔄"); self.act_reset_diff_col.setMaximumWidth(40); self.act_reset_diff_col.setToolTip("Reset Net Colors"); self.act_reset_diff_col.clicked.connect(self.reset_diff_net_colors); diff_bulk_layout.addWidget(self.act_reset_diff_col)
        net_lay.addLayout(diff_bulk_layout)

        search_lay = QHBoxLayout()
        self.input_regex = QLineEdit()
        self.input_regex.setPlaceholderText("Search Nets (e.g., VDD)")
        self.input_regex.textChanged.connect(self.filter_diff_nets_table)
        self.cb_use_regex = QCheckBox("Use strict Regex")
        self.cb_use_regex.stateChanged.connect(self.filter_diff_nets_table)
        btn_info = QPushButton("ℹ️")
        btn_info.setMaximumWidth(30)
        btn_info.clicked.connect(self.show_regex_info)
        search_lay.addWidget(self.input_regex)
        search_lay.addWidget(self.cb_use_regex)
        search_lay.addWidget(btn_info)
        net_lay.addLayout(search_lay)

        self.diff_nets_table = QTableWidget()
        self.diff_nets_table.setAlternatingRowColors(True)
        self.diff_nets_table.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
        self.diff_nets_table.setColumnCount(6)
        self.diff_nets_table.setHorizontalHeaderLabels(["Select", "Net Name", "Delta", "Old", "New", "Color"])
        self.diff_nets_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.diff_nets_table.setWordWrap(False)
        self.diff_nets_table.verticalHeader().setVisible(False)
        
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive) 
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.diff_nets_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        
        self.cb_delegate = CheckboxDelegate(self)
        self.diff_nets_table.setItemDelegateForColumn(0, self.cb_delegate)
        self.diff_nets_table.cellClicked.connect(self.on_diff_net_checkbox_clicked)
        
        net_lay.addWidget(self.diff_nets_table)
        self.right_vert_splitter.addWidget(nets_widget)

        # legacy diff pairs list (fallback for code paths that reference self.diff_pairs_list)
        if not hasattr(self, 'diff_pairs_list'):
            self.diff_pairs_list = QListWidget()
            self.diff_pairs_list.setAlternatingRowColors(True)
            self.diff_pairs_list.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
            self.diff_pairs_list.setSortingEnabled(True)
            self.diff_pairs_list.itemSelectionChanged.connect(self.on_diff_pair_selected)

        # 3. Diff Pairs Panel
        diff_pairs_widget = QWidget()
        d_lay = QVBoxLayout(diff_pairs_widget)
        d_lay.setContentsMargins(0, 10, 0, 0)
        d_lay.addWidget(QLabel("<b>Differential Pairs</b>"))
        
        diff_btns = QHBoxLayout()
        self.btn_color_diffs = QPushButton("🎨 Auto-Color All Diff Pairs")
        self.btn_color_diffs.clicked.connect(self.auto_color_diff_pairs)
        self.btn_clear_diffs = QPushButton("❌ Clear Diff Colors")
        self.btn_clear_diffs.clicked.connect(self.clear_auto_color_diff_pairs)
        diff_btns.addWidget(self.btn_color_diffs)
        diff_btns.addWidget(self.btn_clear_diffs)
        d_lay.addLayout(diff_btns)
        
        if hasattr(self, 'diff_pairs_list'):
            d_lay.addWidget(self.diff_pairs_list)
        
        self.right_vert_splitter.addWidget(diff_pairs_widget)

        # 4. Console Panel
        console_widget = QWidget()
        cons_lay = QVBoxLayout(console_widget)
        cons_lay.setContentsMargins(0, 10, 0, 0)
        cons_lay.addWidget(QLabel("<b>Message Console</b>"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #FFFFFF; color: #000000; font-family: monospace; border: 1px solid #CCC; padding-bottom: 1em;")
        cons_lay.addWidget(self.console)
        self.right_vert_splitter.addWidget(console_widget)

        right_layout.addWidget(self.right_vert_splitter)
        self.main_splitter.addWidget(self.right_pane)
        self.main_splitter.setSizes([1200, 300]) # 80/20 default ratio
        
        self.update_recent_menus()
        self.on_sync_toggled(True) # Force initial button states

    def toggle_privacy(self, checked):
        self.is_blurred = checked
        if checked:
            blur1 = QGraphicsBlurEffect()
            blur1.setBlurRadius(15)
            self.left_view.setGraphicsEffect(blur1)
            self.left_view.viewport().update()
            
            blur2 = QGraphicsBlurEffect()
            blur2.setBlurRadius(15)
            self.right_view.setGraphicsEffect(blur2)
            self.right_view.viewport().update()
            self.log("Privacy filter ON. Maps are blurred.")
        else:
            self.left_view.setGraphicsEffect(None)
            self.left_view.viewport().update()
            self.right_view.setGraphicsEffect(None)
            self.right_view.viewport().update()
            self.log("Privacy filter OFF.")

    def sync_zoom_in(self):
        self.left_view.scale(1.05, 1.05)
        self.right_view.scale(1.05, 1.05)
        
    def sync_zoom_out(self):
        self.left_view.scale(0.95, 0.95)
        self.right_view.scale(0.95, 0.95)

    def update_recent_menus(self):
        self.left_recent_menu.clear()
        self.right_recent_menu.clear()
        if not self.parent_gui.recent_files: return
        for path in self.parent_gui.recent_files:
            act_l = QAction(os.path.basename(path), self)
            act_l.setToolTip(path)
            act_l.triggered.connect(lambda checked, p=path: self.load_left_map(p))
            self.left_recent_menu.addAction(act_l)
            
            act_r = QAction(os.path.basename(path), self)
            act_r.setToolTip(path)
            act_r.triggered.connect(lambda checked, p=path: self.load_right_map(p))
            self.right_recent_menu.addAction(act_r)

    def load_left_map(self, filepath=None):
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(self, "Select OLDER Version Excel", "", "Excel Files (*.xlsx *.xls)")
        if not filepath: return
        try:
            self.old_records, self.old_map = self.parent_gui.parse_excel_to_dict(filepath)
            self.old_meta = self.parent_gui.extract_metadata(os.path.basename(filepath))
            self.lbl_left_title.setText(f"<h3 style='text-align: center; margin:0; color: #444;'>Old Version: {self.old_meta[0]} Rev {self.old_meta[1]}</h3>")
            self.parent_gui.add_recent_file(filepath)
            self.update_recent_menus()
            self.log(f"Loaded Old Version Map: {os.path.basename(filepath)}")
            self.render_single_map(is_left=True)
            self.check_build_engine()
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to load map:\n{str(e)}")

    def load_right_map(self, filepath=None):
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(self, "Select NEWER Version Excel", "", "Excel Files (*.xlsx *.xls)")
        if not filepath: return
        try:
            self.new_records, self.new_map = self.parent_gui.parse_excel_to_dict(filepath)
            self.new_meta = self.parent_gui.extract_metadata(os.path.basename(filepath))
            self.lbl_right_title.setText(f"<h3 style='text-align: center; margin:0; color: #444;'>New Version: {self.new_meta[0]} Rev {self.new_meta[1]}</h3>")
            self.parent_gui.add_recent_file(filepath)
            self.update_recent_menus()
            self.log(f"Loaded New Version Map: {os.path.basename(filepath)}")
            self.render_single_map(is_left=False)
            self.check_build_engine()
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to load map:\n{str(e)}")

    def render_single_map(self, is_left):
        records = self.old_records if is_left else self.new_records
        if not records: return
        
        y_vals = [r['Y Coord'] for r in records if r.get('Y Coord') != ""]
        x_vals = [r['X Coord'] for r in records if r.get('X Coord') != ""]
        if not y_vals or not x_vals: return
        unique_y = sorted(list(set(y_vals)), reverse=True)
        unique_x = sorted(list(set(x_vals)))
        
        y_to_row = {y: i for i, y in enumerate(unique_y)}
        x_to_col = {x: i for i, x in enumerate(unique_x)}
        rows, cols = len(unique_y), len(unique_x)
        
        grid_data = [["" for _ in range(cols)] for _ in range(rows)]
        row_headers, col_headers = [""] * rows, [""] * cols
        unique_nets = set()
        
        for r_data in records:
            x, y = r_data.get('X Coord'), r_data.get('Y Coord')
            if x == "" or y == "": continue
            r, c = y_to_row[y], x_to_col[x]
            net = str(r_data.get('L2 Net Name', '')).strip()
            pin = str(r_data.get('Pin Number', '')).strip()
            
            if net and net != 'nan':
                grid_data[r][c] = net
                unique_nets.add(net)
            if pin and pin != 'nan':
                match = re.match(r"([A-Za-z]+)(\d+)", pin)
                if match: row_headers[r], col_headers[c] = match.groups()
                
        vdd_idx, vss_idx = 0, 0
        for net in sorted(list(unique_nets)):
            if net not in self.diff_net_state:
                color = DEFAULT_CELL_BG
                if "VDD" in net.upper():
                    color = VDD_PALETTE[vdd_idx % len(VDD_PALETTE)]
                    vdd_idx += 1
                elif "VSS" in net.upper():
                    color = VSS_PALETTE[vss_idx % len(VSS_PALETTE)]
                    vss_idx += 1
                # Still assigning color for defaults, but we need to keep it transparent on grid
                self.diff_net_state[net] = {"selected": False, "color": DEFAULT_CELL_BG}

        if is_left:
            self.grid_data_left = grid_data
            self.left_bg_colors.clear() 
            self.render_grid(self.left_scene, 1, rows, cols, row_headers, col_headers, grid_data)
            self.fit_left_view()
        else:
            self.grid_data_right = grid_data
            self.right_bg_colors.clear() 
            self.render_grid(self.right_scene, 2, rows, cols, row_headers, col_headers, grid_data)
            self.fit_right_view()

    def check_build_engine(self):
        if self.old_records is not None and self.new_records is not None:
            self.build_diff_engine()
            def delayed_fit():
                QApplication.processEvents()
                self.fit_to_screen()
            QTimer.singleShot(300, delayed_fit)

    def create_legend_item(self, text, color, tooltip):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        color_box = QLabel()
        color_box.setFixedSize(20, 20)
        color_box.setStyleSheet(f"background-color: {color}; border: 1px solid gray;")
        color_box.setToolTip(tooltip)
        
        lbl = QLabel(text)
        lbl.setToolTip(tooltip)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        font = lbl.font()
        font.setPointSize(8)
        lbl.setFont(font)
        
        top_lay = QHBoxLayout()
        top_lay.addStretch()
        top_lay.addWidget(color_box)
        top_lay.addStretch()
        
        layout.addLayout(top_lay)
        layout.addWidget(lbl)
        return layout

    def apply_preferences(self):
        self.left_view.viewport().update()
        self.right_view.viewport().update()

    def show_regex_info(self):
        QMessageBox.information(self, "Regex Match Info", 
        "<b>Regex Matching Rules:</b><br><br>"
        "• <b>^VDD.*</b> : Matches any net starting with VDD.<br>"
        "• <b>.*CLK.*</b> : Matches any net containing CLK.<br>"
        "• <b>_N\\d+$</b> : Matches nets ending in _N followed by a number.<br><br>"
        "<i>Check 'Use strict Regex' to evaluate rules. Otherwise, uses simple sub-string matching.</i>")

    def on_sync_toggled(self, checked):
        self.btn_sync_zoom_in.setEnabled(checked)
        self.btn_sync_zoom_out.setEnabled(checked)
        self.btn_sync_zoom_fit.setEnabled(checked)
        self.btn_zoom_in_left.setDisabled(checked)
        self.btn_zoom_out_left.setDisabled(checked)
        self.btn_zoom_fit_left.setDisabled(checked)
        self.btn_zoom_in_right.setDisabled(checked)
        self.btn_zoom_out_right.setDisabled(checked)
        self.btn_zoom_fit_right.setDisabled(checked)
        if checked:
            self.fit_to_screen()

    def log(self, message):
        self.console.append(f"> {message}")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def update_diff_cell_color(self, table_idx, r, c):
        items_dict = self.ball_items_left if table_idx == 1 else self.ball_items_right
        manual_colors = self.diff_manual_colors_left if table_idx == 1 else self.diff_manual_colors_right
        bg_colors = self.left_bg_colors if table_idx == 1 else self.right_bg_colors
        
        item = items_dict.get((r, c))
        if not item: return
        
        base_bg = bg_colors.get((r, c), DEFAULT_CELL_BG)
        if not self.show_delta_colors:
            base_bg = DEFAULT_CELL_BG
            
        bg_col = base_bg
        
        if (r, c) in manual_colors:
            bg_col = manual_colors[(r, c)]
        elif item.net and item.net in self.diff_net_state and self.diff_net_state[item.net]["color"] != DEFAULT_CELL_BG:
            bg_col = self.diff_net_state[item.net]["color"]
            
        is_chk = item.net and item.net in self.diff_net_state and self.diff_net_state[item.net]["selected"]
        
        hl_col = None
        if (r, c) in self.report_highlights: hl_col = self.report_highlights[(r, c)]
        
        item.update_visuals(bg_col, is_chk, hl_col)

    def on_selection_changed(self):
        checked_nets = {net for net, state in self.diff_net_state.items() if state.get("selected")}
        
        l_native = sum(1 for i in self.left_scene.selectedItems() if isinstance(i, BallItem))
        l_net = 0
        if checked_nets and self.grid_data_left:
            for (r, c), item in self.ball_items_left.items():
                if item.net in checked_nets and not item.isSelected(): l_net += 1
        self.lbl_sel_left.setText(f"{l_native + l_net} cells selected")
        
        r_native = sum(1 for i in self.right_scene.selectedItems() if isinstance(i, BallItem))
        r_net = 0
        if checked_nets and self.grid_data_right:
            for (r, c), item in self.ball_items_right.items():
                if item.net in checked_nets and not item.isSelected(): r_net += 1
        self.lbl_sel_right.setText(f"{r_native + r_net} cells selected")

    def toggle_sidebar(self):
        self.right_pane.setVisible(not self.right_pane.isVisible())
        self.fit_to_screen()

    def show_diff_context_menu(self, pos, table_idx):
        view = self.left_view if table_idx == 1 else self.right_view
        scene = self.left_scene if table_idx == 1 else self.right_scene
        manual_colors = self.diff_manual_colors_left if table_idx == 1 else self.diff_manual_colors_right
        
        selected_items = [i for i in scene.selectedItems() if isinstance(i, BallItem)]
        if not selected_items: return
        
        menu = QMenu(view)
        color_action = menu.addAction("🎨 Set Color for Selected Balls...")
        clear_action = menu.addAction("❌ Clear Manual Color")
        
        action = menu.exec(view.mapToGlobal(pos))
        if action == color_action:
            color = QColorDialog.getColor()
            if color.isValid():
                hex_color = color.name()
                for item in selected_items:
                    manual_colors[(item.r, item.c)] = hex_color
                    self.update_diff_cell_color(table_idx, item.r, item.c)
        elif action == clear_action:
            for item in selected_items:
                if (item.r, item.c) in manual_colors:
                    del manual_colors[(item.r, item.c)]
                    self.update_diff_cell_color(table_idx, item.r, item.c)

    def clear_delta_colors(self):
        self.show_delta_colors = False
        for r in range(self.diff_rows):
            for c in range(self.diff_cols):
                self.update_diff_cell_color(1, r, c)
                self.update_diff_cell_color(2, r, c)
        self.log("Delta background colors cleared.")

    def reset_delta_colors(self):
        self.show_delta_colors = True
        for r in range(self.diff_rows):
            for c in range(self.diff_cols):
                self.update_diff_cell_color(1, r, c)
                self.update_diff_cell_color(2, r, c)
        self.log("Delta background colors reset to legend defaults.")

    def reset_diff_net_colors(self):
        for net_name in self.diff_net_state.keys():
            default_col = self.default_diff_net_colors.get(net_name, DEFAULT_CELL_BG)
            self.diff_net_state[net_name]["color"] = default_col
            for i in range(self.diff_nets_table.rowCount()):
                if self.diff_nets_table.item(i, 1).text() == net_name:
                    self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {default_col}; border: 1px solid darkgray;")
        for (r, c) in self.ball_items_left.keys(): self.update_diff_cell_color(1, r, c)
        for (r, c) in self.ball_items_right.keys(): self.update_diff_cell_color(2, r, c)
        self.log("Diff net foreground colors reset to default VDD/VSS palettes.")

    def save_view(self):
        view_name = self.input_view_name.text()
        if not view_name:
            QMessageBox.warning(self, "Warning", "Please enter a View Name.")
            return
        self.saved_views[view_name] = {
            'net_state': {k: v.copy() for k, v in self.diff_net_state.items()},
            'manual_left': self.diff_manual_colors_left.copy(),
            'manual_right': self.diff_manual_colors_right.copy()
        }
        if self.combo_views.findText(view_name) == -1: self.combo_views.addItem(view_name)
        self.log(f"Saved diff view '{view_name}'.")
        self.view_counter += 1
        self.input_view_name.setText(f"Diff_View_{self.view_counter}")

    def load_view(self):
        view_name = self.combo_views.currentText()
        if not view_name or view_name not in self.saved_views: return
        self.diff_clear_all_selections()
        view_data = self.saved_views[view_name]
        
        for net_name, data in view_data['net_state'].items():
            if net_name in self.diff_net_state: self.diff_net_state[net_name] = data.copy()
        self.diff_manual_colors_left = view_data['manual_left'].copy()
        self.diff_manual_colors_right = view_data['manual_right'].copy()
        
        self._updating_checks = True
        for i in range(self.diff_nets_table.rowCount()):
            net_name = self.diff_nets_table.item(i, 1).text()
            state = self.diff_net_state.get(net_name, {"selected": False, "color": DEFAULT_CELL_BG})
            self.diff_nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, state["selected"])
            self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {state['color']}; border: 1px solid darkgray;")
        self._updating_checks = False
        
        for (r, c) in self.ball_items_left.keys(): self.update_diff_cell_color(1, r, c)
        for (r, c) in self.ball_items_right.keys(): self.update_diff_cell_color(2, r, c)
        self.log(f"Loaded diff view '{view_name}'.")

    def save_db(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Diff Database", "session_diff.json", "JSON Files (*.json)")
        if not file_path: return
        
        ml_list = [{"r": r, "c": c, "color": color} for (r, c), color in self.diff_manual_colors_left.items()]
        mr_list = [{"r": r, "c": c, "color": color} for (r, c), color in self.diff_manual_colors_right.items()]
        
        db_data = {
            "old_records": self.old_records,
            "new_records": self.new_records,
            "old_map": self.old_map,
            "new_map": self.new_map,
            "old_meta": self.old_meta,
            "new_meta": self.new_meta,
            "diff_net_state": self.diff_net_state,
            "default_diff_net_colors": self.default_diff_net_colors,
            "saved_views": self.saved_views,
            "manual_colors_left": ml_list,
            "manual_colors_right": mr_list,
            "report_highlights": [{"r": r, "c": c, "color": color} for (r, c), color in self.report_highlights.items()]
        }
        with open(file_path, 'w') as f: json.dump(db_data, f)
        self.log("Diff session database saved successfully.")

    def load_db(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Diff Database", "", "JSON Files (*.json)")
        if not file_path: return
        try:
            with open(file_path, 'r') as f: db_data = json.load(f)
            
            self.old_records = db_data.get("old_records")
            self.new_records = db_data.get("new_records")
            self.old_map = db_data.get("old_map", {})
            self.new_map = db_data.get("new_map", {})
            self.old_meta = db_data.get("old_meta", ("Not Loaded", "0.0"))
            self.new_meta = db_data.get("new_meta", ("Not Loaded", "0.0"))
            
            self.lbl_left_title.setText(f"<h3 style='text-align: center; margin:0; color: #444;'>Old Version: {self.old_meta[0]} Rev {self.old_meta[1]}</h3>")
            self.lbl_right_title.setText(f"<h3 style='text-align: center; margin:0; color: #444;'>New Version: {self.new_meta[0]} Rev {self.new_meta[1]}</h3>")
            
            self.render_single_map(True)
            self.render_single_map(False)
            self.build_diff_engine() 
            
            self.default_diff_net_colors = db_data.get("default_diff_net_colors", self.default_diff_net_colors)
            self.diff_net_state = db_data.get("diff_net_state", self.diff_net_state)
            self.saved_views = db_data.get("saved_views", {})
            
            ml_list = db_data.get("manual_colors_left", [])
            self.diff_manual_colors_left = {(item["r"], item["c"]): item["color"] for item in ml_list}
            
            mr_list = db_data.get("manual_colors_right", [])
            self.diff_manual_colors_right = {(item["r"], item["c"]): item["color"] for item in mr_list}
            
            rh_list = db_data.get("report_highlights", [])
            self.report_highlights = {(item["r"], item["c"]): item["color"] for item in rh_list}
            
            self._updating_checks = True
            for i in range(self.diff_nets_table.rowCount()):
                net_name = self.diff_nets_table.item(i, 1).text()
                state = self.diff_net_state.get(net_name, {"selected": False, "color": DEFAULT_CELL_BG})
                self.diff_nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, state["selected"])
                self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {state['color']}; border: 1px solid darkgray;")
            self._updating_checks = False
            
            self.combo_views.clear()
            self.combo_views.addItems(list(self.saved_views.keys()))
            
            for (r, c) in self.ball_items_left.keys(): self.update_diff_cell_color(1, r, c)
            for (r, c) in self.ball_items_right.keys(): self.update_diff_cell_color(2, r, c)
            
            self.log("Diff Database session loaded seamlessly.")
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    def on_report_clicked(self, item):
        cells = item.data(Qt.ItemDataRole.UserRole)
        self.left_scene.clearSelection()
        self.right_scene.clearSelection()
        if cells:
            for r, c in cells:
                if (r, c) in self.ball_items_left: self.ball_items_left[(r, c)].setSelected(True)
                if (r, c) in self.ball_items_right: self.ball_items_right[(r, c)].setSelected(True)
            r, c = cells[0]
            if (r, c) in self.ball_items_left: self.left_view.centerOn(self.ball_items_left[(r, c)])
            if (r, c) in self.ball_items_right: self.right_view.centerOn(self.ball_items_right[(r, c)])
        self.log(f"Investigating Delta: {item.text()}")

    def highlight_report_items(self):
        items = self.report_list.selectedItems()
        if not items: return
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            for item in items:
                cells = item.data(Qt.ItemDataRole.UserRole)
                if cells:
                    for r, c in cells:
                        self.report_highlights[(r, c)] = hex_color
                        self.update_diff_cell_color(1, r, c)
                        self.update_diff_cell_color(2, r, c)
                item.setForeground(QBrush(QColor(hex_color)))
                font = item.font(); font.setBold(True); item.setFont(font)

    def clear_report_items(self):
        items = self.report_list.selectedItems()
        if not items: return
        for item in items:
            cells = item.data(Qt.ItemDataRole.UserRole)
            if cells:
                for r, c in cells:
                    if (r, c) in self.report_highlights:
                        del self.report_highlights[(r, c)]
                        self.update_diff_cell_color(1, r, c)
                        self.update_diff_cell_color(2, r, c)
            item.setForeground(QBrush(QColor("black")))
            font = item.font(); font.setBold(False); item.setFont(font)
        self.left_scene.clearSelection()
        self.right_scene.clearSelection()

    def toggle_pan(self, checked):
        self.pan_active = checked
        self.left_view.setInteractive(not checked)
        self.right_view.setInteractive(not checked)
        if checked:
            self.left_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.right_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.left_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.right_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def fit_left_view(self):
        if not self.grid_data_left: return
        self.left_view.resetTransform()
        br = self.left_scene.itemsBoundingRect()
        pad = 2000
        self.left_scene.setSceneRect(br.adjusted(-pad, -pad, pad, pad))
        self.left_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.left_view.fitInView(br, Qt.AspectRatioMode.KeepAspectRatio)
        self.left_view.scale(0.95, 0.95)
        self.left_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def fit_right_view(self):
        if not self.grid_data_right: return
        self.right_view.resetTransform()
        br = self.right_scene.itemsBoundingRect()
        pad = 2000
        self.right_scene.setSceneRect(br.adjusted(-pad, -pad, pad, pad))
        self.right_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.right_view.fitInView(br, Qt.AspectRatioMode.KeepAspectRatio)
        self.right_view.scale(0.95, 0.95)
        self.right_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def fit_to_screen(self):
        if self.diff_rows == 0 or self.diff_cols == 0: return
        self.fit_left_view()
        self.fit_right_view()
        if self.debug_mode: print(f"[DEBUG] Executed Global Diff Fit-To-Screen")

    def add_report_item(self, text, cells):
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, cells)
        self.report_list.addItem(item)

    def render_grid(self, scene, table_idx, rows, cols, row_headers, col_headers, grid_data):
        scene.clear()
        if table_idx == 1: self.ball_items_left.clear()
        else: self.ball_items_right.clear()
        
        for c in range(cols):
            scene.addItem(HeaderItem((c+1)*CELL_SIZE, 0, CELL_SIZE, CELL_SIZE, col_headers[c], self))
            scene.addItem(HeaderItem((c+1)*CELL_SIZE, (rows+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, col_headers[c], self))
        for r in range(rows):
            scene.addItem(HeaderItem(0, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, row_headers[r], self))
            scene.addItem(HeaderItem((cols+1)*CELL_SIZE, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, row_headers[r], self))
            
        for r in range(rows):
            for c in range(cols):
                net_name = grid_data[r][c]
                pin_name = f"{row_headers[r]}{col_headers[c]}"
                item = BallItem(r, c, net_name, pin_name, self)
                scene.addItem(item)
                if table_idx == 1: self.ball_items_left[(r, c)] = item
                else: self.ball_items_right[(r, c)] = item
                self.update_diff_cell_color(table_idx, r, c)

    def build_diff_engine(self):
        self.report_list.clear()
        old_y = [r['Y Coord'] for r in self.old_records if r.get('Y Coord') != ""]
        new_y = [r['Y Coord'] for r in self.new_records if r.get('Y Coord') != ""]
        all_y = sorted(list(set(old_y + new_y)), reverse=True)
        
        old_x = [r['X Coord'] for r in self.old_records if r.get('X Coord') != ""]
        new_x = [r['X Coord'] for r in self.new_records if r.get('X Coord') != ""]
        all_x = sorted(list(set(old_x + new_x)))
        
        y_to_row = {y: i for i, y in enumerate(all_y)}
        x_to_col = {x: i for i, x in enumerate(all_x)}
        
        self.diff_rows, self.diff_cols = len(all_y), len(all_x)
        self.grid_data_left = [["" for _ in range(self.diff_cols)] for _ in range(self.diff_rows)]
        self.grid_data_right = [["" for _ in range(self.diff_cols)] for _ in range(self.diff_rows)]
        
        all_nets = sorted(list(set(list(self.old_map.values()) + list(self.new_map.values()))))
        vdd_idx, vss_idx = 0, 0
        self.default_diff_net_colors = {}
        for net in all_nets:
            color = DEFAULT_CELL_BG
            if "VDD" in net.upper():
                color = VDD_PALETTE[vdd_idx % len(VDD_PALETTE)]
                vdd_idx += 1
            elif "VSS" in net.upper():
                color = VSS_PALETTE[vss_idx % len(VSS_PALETTE)]
                vss_idx += 1
            self.default_diff_net_colors[net] = color
            if net not in self.diff_net_state:
                # Store defaults in memory, but initialize active state as gray for clear Delta reading
                self.diff_net_state[net] = {"selected": False, "color": DEFAULT_CELL_BG}
        
        rc_counter = 1
        for r_data in self.new_records:
            if r_data.get('X Coord') == "" or r_data.get('Y Coord') == "": continue
            r, c = y_to_row[r_data['Y Coord']], x_to_col[r_data['X Coord']]
            net, pin = str(r_data.get('L2 Net Name', '')).strip(), str(r_data.get('Pin Number', '')).strip()
            old_net = self.old_map.get(pin, "UNASSIGNED")
            
            color = "#E0E0E0" 
            if old_net == "UNASSIGNED": 
                color = "#A9DFBF" 
                self.add_report_item(f"{rc_counter}. Pin {pin}: Added [{net}]", [(r, c)])
                rc_counter += 1
            elif old_net != net: 
                color = "#FAD7A1" 
                self.add_report_item(f"{rc_counter}. Pin {pin}: {old_net} ➔ {net}", [(r, c)])
                rc_counter += 1

            self.grid_data_right[r][c] = net
            self.right_bg_colors[(r, c)] = color

        for r_data in self.old_records:
            if r_data.get('X Coord') == "" or r_data.get('Y Coord') == "": continue
            r, c = y_to_row[r_data['Y Coord']], x_to_col[r_data['X Coord']]
            net, pin = str(r_data.get('L2 Net Name', '')).strip(), str(r_data.get('Pin Number', '')).strip()
            
            new_net = self.new_map.get(pin, "UNASSIGNED")
            color = "#E0E0E0"
            if new_net == "UNASSIGNED":
                color = "#F5B7B1" 
                self.add_report_item(f"{rc_counter}. Pin {pin}: Removed [{net}]", [(r, c)])
                rc_counter += 1
            elif new_net != net:
                color = "#FAD7A1" 

            self.grid_data_left[r][c] = net
            self.left_bg_colors[(r, c)] = color
            
        # Extract headers for render
        row_headers_l, col_headers_l = [""] * self.diff_rows, [""] * self.diff_cols
        row_headers_r, col_headers_r = [""] * self.diff_rows, [""] * self.diff_cols
        
        for r_data in self.old_records:
            x, y = r_data.get('X Coord'), r_data.get('Y Coord')
            if x == "" or y == "": continue
            r, c = y_to_row[y], x_to_col[x]
            pin = str(r_data.get('Pin Number', '')).strip()
            if pin and pin != 'nan':
                match = re.match(r"([A-Za-z]+)(\d+)", pin)
                if match: row_headers_l[r], col_headers_l[c] = match.groups()
                
        for r_data in self.new_records:
            x, y = r_data.get('X Coord'), r_data.get('Y Coord')
            if x == "" or y == "": continue
            r, c = y_to_row[y], x_to_col[x]
            pin = str(r_data.get('Pin Number', '')).strip()
            if pin and pin != 'nan':
                match = re.match(r"([A-Za-z]+)(\d+)", pin)
                if match: row_headers_r[r], col_headers_r[c] = match.groups()
                
        self.render_grid(self.left_scene, 1, self.diff_rows, self.diff_cols, row_headers_l, col_headers_l, self.grid_data_left)
        self.render_grid(self.right_scene, 2, self.diff_rows, self.diff_cols, row_headers_r, col_headers_r, self.grid_data_right)

        if self.report_list.count() == 0:
            self.report_list.addItem("No layout changes detected.")

        old_counts, new_counts = {}, {}
        for net in self.old_map.values(): old_counts[net] = old_counts.get(net, 0) + 1
        for net in self.new_map.values(): new_counts[net] = new_counts.get(net, 0) + 1

        self.diff_nets_table.setSortingEnabled(False)
        self.diff_nets_table.setRowCount(len(all_nets))
        self._updating_checks = True
        
        for idx, net_name in enumerate(all_nets):
            state = self.diff_net_state[net_name]
            
            item_chk = QTableWidgetItem("")
            item_chk.setData(Qt.ItemDataRole.UserRole, state["selected"])
            self.diff_nets_table.setItem(idx, 0, item_chk)
            
            name_item = QTableWidgetItem(net_name)
            name_item.setToolTip(net_name)
            self.diff_nets_table.setItem(idx, 1, name_item)
            
            old_c_val = old_counts.get(net_name, 0)
            new_c_val = new_counts.get(net_name, 0)
            
            delta = new_c_val - old_c_val
            delta_str = f"{delta:+d}" if delta != 0 else "0"
            delta_item = NumericItem(delta_str)
            delta_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            delta_item.setToolTip(delta_str)
            self.diff_nets_table.setItem(idx, 2, delta_item)

            old_c = NumericItem(str(old_c_val))
            old_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            old_c.setToolTip(str(old_c_val))
            self.diff_nets_table.setItem(idx, 3, old_c)

            new_c = NumericItem(str(new_c_val))
            new_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            new_c.setToolTip(str(new_c_val))
            self.diff_nets_table.setItem(idx, 4, new_c)

            color_btn = QPushButton()
            color_btn.setStyleSheet(f"background-color: {state['color']}; border: 1px solid darkgray;")
            color_btn.setMinimumWidth(30)
            color_btn.clicked.connect(lambda checked, net=net_name, btn=color_btn: self.pick_diff_net_color(net, btn))
            
            self.diff_nets_table.setItem(idx, 5, QTableWidgetItem(""))
            self.diff_nets_table.setCellWidget(idx, 5, color_btn)
            
        self._updating_checks = False
        self.diff_nets_table.setSortingEnabled(True)
        self.detect_diff_pairs()

    def on_diff_net_checkbox_clicked(self, row, col):
        if getattr(self, '_updating_checks', False): return
        if col == 0:
            item = self.diff_nets_table.item(row, 0)
            net_name = self.diff_nets_table.item(row, 1).text()
            current_state = item.data(Qt.ItemDataRole.UserRole)
            new_state = not current_state
            item.setData(Qt.ItemDataRole.UserRole, new_state)
            
            self.diff_net_state[net_name]["selected"] = new_state
            self.on_selection_changed()
            for (r, c), b_item in self.ball_items_left.items():
                if b_item.net == net_name: self.update_diff_cell_color(1, r, c)
            for (r, c), b_item in self.ball_items_right.items():
                if b_item.net == net_name: self.update_diff_cell_color(2, r, c)

    def filter_diff_nets_table(self):
        pattern = self.input_regex.text().strip()
        use_regex = self.cb_use_regex.isChecked()
        try:
            if use_regex: regex = re.compile(pattern, re.IGNORECASE)
        except re.error: return 

        for idx in range(self.diff_nets_table.rowCount()):
            net_name_item = self.diff_nets_table.item(idx, 1)
            if net_name_item:
                net_text = net_name_item.text()
                if use_regex: is_visible = bool(regex.fullmatch(net_text)) if pattern else True
                else: is_visible = pattern.upper() in net_text.upper() 
                self.diff_nets_table.setRowHidden(idx, not is_visible)
        
    def pick_diff_net_color(self, net_name, color_btn):
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            self.diff_net_state[net_name]["color"] = hex_color
            color_btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
            for r in range(self.diff_rows):
                for c in range(self.diff_cols):
                    if self.grid_data_left[r][c] == net_name:
                        self.update_diff_cell_color(1, r, c)
                    if self.grid_data_right[r][c] == net_name:
                        self.update_diff_cell_color(2, r, c)

    def diff_select_all_visible(self):
        self._updating_checks = True
        self.diff_nets_table.setUpdatesEnabled(False)
        for i in range(self.diff_nets_table.rowCount()):
            if not self.diff_nets_table.isRowHidden(i):
                self.diff_nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, True)
                net_name = self.diff_nets_table.item(i, 1).text()
                self.diff_net_state[net_name]["selected"] = True
                
        self.diff_nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.on_selection_changed()
        for (r, c), b_item in self.ball_items_left.items():
            if b_item.net in self.diff_net_state and self.diff_net_state[b_item.net]["selected"]: self.update_diff_cell_color(1, r, c)
        for (r, c), b_item in self.ball_items_right.items():
            if b_item.net in self.diff_net_state and self.diff_net_state[b_item.net]["selected"]: self.update_diff_cell_color(2, r, c)

    def diff_deselect_all(self):
        self._updating_checks = True
        self.diff_nets_table.setUpdatesEnabled(False)
        for i in range(self.diff_nets_table.rowCount()):
            self.diff_nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, False)
            net_name = self.diff_nets_table.item(i, 1).text()
            self.diff_net_state[net_name]["selected"] = False
            
        self.diff_nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.left_scene.clearSelection()
        self.right_scene.clearSelection()
        for (r, c), b_item in self.ball_items_left.items(): self.update_diff_cell_color(1, r, c)
        for (r, c), b_item in self.ball_items_right.items(): self.update_diff_cell_color(2, r, c)

    def diff_clear_all_selections(self):
        self.diff_deselect_all()
        self.diff_manual_colors_left.clear()
        self.diff_manual_colors_right.clear()
        self.report_highlights.clear()
        
        for net_name in self.diff_net_state.keys():
            self.diff_net_state[net_name]["color"] = DEFAULT_CELL_BG
            for i in range(self.diff_nets_table.rowCount()):
                if self.diff_nets_table.item(i, 1).text() == net_name:
                    color_btn = self.diff_nets_table.cellWidget(i, 5)
                    color_btn.setStyleSheet(f"background-color: {DEFAULT_CELL_BG}; border: 1px solid darkgray;")
                    
        for (r, c) in self.ball_items_left.keys(): self.update_diff_cell_color(1, r, c)
        for (r, c) in self.ball_items_right.keys(): self.update_diff_cell_color(2, r, c)

    def color_checked_diff_nets(self):
        checked_nets = []
        for i in range(self.diff_nets_table.rowCount()):
            if not self.diff_nets_table.isRowHidden(i):
                if self.diff_nets_table.item(i, 0).data(Qt.ItemDataRole.UserRole):
                    checked_nets.append(self.diff_nets_table.item(i, 1).text())
                    
        valid_left = [i for i in self.left_scene.selectedItems() if isinstance(i, BallItem)]
        valid_right = [i for i in self.right_scene.selectedItems() if isinstance(i, BallItem)]
                
        if not checked_nets and not valid_left and not valid_right: return
        
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            
            for net_name in checked_nets:
                self.diff_net_state[net_name]["color"] = hex_color
                for i in range(self.diff_nets_table.rowCount()):
                    if self.diff_nets_table.item(i, 1).text() == net_name:
                        self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
                        break
                        
            for r in range(self.diff_rows):
                for c in range(self.diff_cols):
                    if self.grid_data_left[r][c] in checked_nets:
                        self.update_diff_cell_color(1, r, c)
                    if self.grid_data_right[r][c] in checked_nets:
                        self.update_diff_cell_color(2, r, c)
                        
            for item in valid_left:
                self.diff_manual_colors_left[(item.r, item.c)] = hex_color
                self.update_diff_cell_color(1, item.r, item.c)
            for item in valid_right:
                self.diff_manual_colors_right[(item.r, item.c)] = hex_color
                self.update_diff_cell_color(2, item.r, item.c)

    def detect_diff_pairs(self):
        self.valid_diff_pairs.clear()
        if hasattr(self, 'diff_pairs_list'): self.diff_pairs_list.clear()
        
        rows, cols = self.diff_rows, self.diff_cols
        net_pin_counts = {}
        for r in range(rows):
            for c in range(cols):
                net = self.grid_data_right[r][c]
                if net:
                    net_pin_counts[net] = net_pin_counts.get(net, 0) + 1
                    
        diff_pattern = re.compile(r'^(.*)_([NP])$', re.IGNORECASE)
        potential_pairs = {}
        for net in net_pin_counts.keys():
            m = diff_pattern.match(net)
            if m:
                base, pfx = m.groups()
                pfx = pfx.upper()
                if base not in potential_pairs: potential_pairs[base] = {}
                potential_pairs[base][pfx] = net
                
        self.valid_diff_pairs = {b: pairs for b, pairs in potential_pairs.items() if 'P' in pairs and 'N' in pairs}
        for b in sorted(self.valid_diff_pairs.keys()):
            if hasattr(self, 'diff_pairs_list'): self.diff_pairs_list.addItem(f"{b} (_P / _N)")

    def auto_color_diff_pairs(self):
        if not self.valid_diff_pairs: return
        for i, (base, pairs) in enumerate(self.valid_diff_pairs.items()):
            hue = (i * 0.618033988749895) % 1.0
            rgb = colorsys.hls_to_rgb(hue, 0.7, 0.6)
            hex_color = "#{:02x}{:02x}{:02x}".format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            p_net = pairs.get('P')
            n_net = pairs.get('N')
            if p_net not in self.diff_net_state: self.diff_net_state[p_net] = {"selected": False}
            if n_net not in self.diff_net_state: self.diff_net_state[n_net] = {"selected": False}
            
            self.diff_net_state[p_net]['color'] = hex_color
            self.diff_net_state[n_net]['color'] = hex_color
            
        for item in self.ball_items_left.values(): self.update_diff_cell_color(1, item.r, item.c)
        for item in self.ball_items_right.values(): self.update_diff_cell_color(2, item.r, item.c)
                
        # Update the UI buttons
        for i in range(self.diff_nets_table.rowCount()):
            net_name = self.diff_nets_table.item(i, 1).text()
            if net_name in self.diff_net_state:
                self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {self.diff_net_state[net_name]['color']}; border: 1px solid darkgray;")
                
        self.log(f"Auto-colored {len(self.valid_diff_pairs)} differential pairs.")

    def clear_auto_color_diff_pairs(self):
        if not self.valid_diff_pairs: return
        for base, pairs in self.valid_diff_pairs.items():
            p_net = pairs.get('P')
            n_net = pairs.get('N')
            if p_net in self.diff_net_state: self.diff_net_state[p_net]['color'] = DEFAULT_CELL_BG 
            if n_net in self.diff_net_state: self.diff_net_state[n_net]['color'] = DEFAULT_CELL_BG
            
        for item in self.ball_items_left.values(): self.update_diff_cell_color(1, item.r, item.c)
        for item in self.ball_items_right.values(): self.update_diff_cell_color(2, item.r, item.c)
        
        # Update the UI buttons
        for i in range(self.diff_nets_table.rowCount()):
            net_name = self.diff_nets_table.item(i, 1).text()
            if net_name in self.diff_net_state:
                self.diff_nets_table.cellWidget(i, 5).setStyleSheet(f"background-color: {self.diff_net_state[net_name]['color']}; border: 1px solid darkgray;")
                
        self.log("Cleared differential pair auto-colors.")

    def on_diff_pair_selected(self):
        items = self.diff_pairs_list.selectedItems() if hasattr(self, 'diff_pairs_list') else []
        if not items: return
        base_name = items[0].text().replace(" (_P / _N)", "")
        pairs = self.valid_diff_pairs.get(base_name)
        if not pairs: return
        
        target_nets = [pairs.get('P'), pairs.get('N')]
        self.left_scene.clearSelection()
        self.right_scene.clearSelection()
        
        c_left = []
        c_right = []
        for item in self.ball_items_left.values():
            if item.net in target_nets:
                item.setSelected(True)
                c_left.append(item)
        for item in self.ball_items_right.values():
            if item.net in target_nets:
                item.setSelected(True)
                c_right.append(item)
                
        # Smart Pan: Only center if the item is not fully visible
        if c_left:
            visible_rect_l = self.left_view.mapToScene(self.left_view.viewport().rect()).boundingRect()
            if not visible_rect_l.contains(c_left[0].sceneBoundingRect()):
                self.left_view.centerOn(c_left[0])
                
        if c_right:
            visible_rect_r = self.right_view.mapToScene(self.right_view.viewport().rect()).boundingRect()
            if not visible_rect_r.contains(c_right[0].sceneBoundingRect()):
                self.right_view.centerOn(c_right[0])


class BallMapEditor(QDialog):
    def __init__(self, parent_gui):
        super().__init__(None)
        self.parent_gui = parent_gui
        self.debug_mode = parent_gui.debug_mode
        self.draw_circles = parent_gui.draw_circles
        self.adaptive_font = parent_gui.adaptive_font
        self._updating_checks = False
        self.is_blurred = False
        
        self.setWindowTitle(f"Ball Map Editor v{__version__} - {self.parent_gui.base_device} Rev {self.parent_gui.base_version}")
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "BallMapViewer.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1400, 900)
        
        self.editor_records = copy.deepcopy(self.parent_gui.current_records)
        self.grid_data = copy.deepcopy(self.parent_gui.grid_data)
        self.row_headers = copy.deepcopy(self.parent_gui.row_headers)
        self.col_headers = copy.deepcopy(self.parent_gui.col_headers)
        self.net_frequences = copy.deepcopy(self.parent_gui.net_frequences)
        self.net_view_state = copy.deepcopy(self.parent_gui.net_view_state)
        self.default_net_colors = copy.deepcopy(self.parent_gui.default_net_colors)
        
        self.ball_items = {}
        self.manual_colors = {}
        self.active_violation_cells = set()
        self.active_passing_cells = set()
        self.active_waived_cells = set()
        
        self.unassigned_nets = {}
        self.active_tool = "IDLE"
        self.swap_selection = None
        self.selected_unassigned_net = None
        
        self.undo_stack = []
        self.redo_stack = []
        
        self.init_ui()
        self.render_grid()
        self.populate_nets_table()
        
        def delayed_fit():
            QApplication.processEvents()
            self.fit_to_screen()
        QTimer.singleShot(300, delayed_fit)
        self.log("Ball Map Editor initialized. Drag, Swap, or reassign nets.")

    def init_ui(self):
        base_layout = QVBoxLayout(self)
        base_layout.setContentsMargins(0, 0, 0, 0)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                width: 6px;
            }
        """)
        base_layout.addWidget(self.main_splitter)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        self.toolbar = QToolBar()
        self.act_export = QAction("💾 Export Excel", self)
        self.act_export.setToolTip("Export modified map to Excel")
        self.act_export.triggered.connect(self.export_excel)
        self.toolbar.addAction(self.act_export)
        
        self.toolbar.addSeparator()
        self.act_undo = QAction("↶ Undo", self)
        self.act_undo.setToolTip("Undo last action")
        self.act_undo.triggered.connect(self.undo)
        self.toolbar.addAction(self.act_undo)
        
        self.act_redo = QAction("↷ Redo", self)
        self.act_redo.setToolTip("Redo last action")
        self.act_redo.triggered.connect(self.redo)
        self.toolbar.addAction(self.act_redo)
        
        self.toolbar.addSeparator()
        self.act_save_db = QAction("💾 Save DB", self)
        self.act_save_db.setToolTip("Save Editor Session")
        self.act_save_db.triggered.connect(self.save_db)
        self.toolbar.addAction(self.act_save_db)
        
        self.act_load_db = QAction("📂 Load DB", self)
        self.act_load_db.setToolTip("Load Editor Session")
        self.act_load_db.triggered.connect(self.load_db)
        self.toolbar.addAction(self.act_load_db)
        
        self.toolbar.addSeparator()
        self.pan_act = QAction("✋ Pan", self)
        self.pan_act.setCheckable(True)
        self.pan_act.toggled.connect(self.toggle_pan)
        self.toolbar.addAction(self.pan_act)
        
        self.act_swap = QAction("⇄ Swap Nets", self)
        self.act_swap.setCheckable(True)
        self.act_swap.setToolTip("Click two cells to instantly swap their nets")
        self.act_swap.toggled.connect(self.toggle_swap)
        self.toolbar.addAction(self.act_swap)
        
        self.toolbar.addSeparator()
        z_in = QAction("🔍+", self); z_in.triggered.connect(lambda: self.view.wheelEvent(self._mock_wheel(120))); self.toolbar.addAction(z_in)
        z_out = QAction("🔍-", self); z_out.triggered.connect(lambda: self.view.wheelEvent(self._mock_wheel(-120))); self.toolbar.addAction(z_out)
        fit = QAction("⛶ Fit", self); fit.triggered.connect(self.fit_to_screen); self.toolbar.addAction(fit)
        
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)
        
        self.lbl_selection = QLabel("<b>Selected Cells:</b> 0")
        self.lbl_selection.setContentsMargins(0, 0, 10, 0)
        self.toolbar.addWidget(self.lbl_selection)
        
        self.btn_privacy = QAction("👁️ Privacy Blur", self)
        self.btn_privacy.setCheckable(True)
        self.btn_privacy.setToolTip("Toggle Privacy Filter")
        self.btn_privacy.toggled.connect(self.toggle_privacy)
        self.toolbar.addAction(self.btn_privacy)

        left_layout.addWidget(self.toolbar, 0) 

        self.scene = QGraphicsScene()
        self.view = EDA_Canvas(self)
        self.view.setScene(self.scene)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.view, 1)
        
        self.main_splitter.addWidget(left_pane)

        self.right_pane = QWidget()
        right_layout = QVBoxLayout(self.right_pane)
        self.right_vert_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_vert_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                height: 6px;
            }
        """)
        
        # 1. Unassigned Container
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        unassigned_header_lay = QHBoxLayout()
        unassigned_header_lay.addWidget(QLabel("<b>Unassigned Nets Container</b>"))
        unassigned_header_lay.addStretch()
        self.lbl_unassigned_count = QLabel("Total Pins: 0")
        unassigned_header_lay.addWidget(self.lbl_unassigned_count)
        container_layout.addLayout(unassigned_header_lay)
        
        self.lbl_selected_unassigned = QLabel("Selected Net: None")
        container_layout.addWidget(self.lbl_selected_unassigned)
        
        self.unassigned_search = QLineEdit()
        self.unassigned_search.setPlaceholderText("Search Unassigned Nets...")
        self.unassigned_search.textChanged.connect(self.filter_unassigned_list)
        container_layout.addWidget(self.unassigned_search)
        
        self.unassigned_list = QListWidget()
        self.unassigned_list.setAlternatingRowColors(True)
        self.unassigned_list.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
        self.unassigned_list.itemClicked.connect(self.on_unassigned_selected)
        container_layout.addWidget(self.unassigned_list)
        
        self.right_vert_splitter.addWidget(container_widget)
        
        # 2. Dynamic Nets Control
        nets_widget = QWidget()
        nets_layout = QVBoxLayout(nets_widget)
        nets_layout.setContentsMargins(0, 10, 0, 0)
        nets_layout.addWidget(QLabel("<b>Dynamic Net Control</b>"))
        
        bulk_layout = QHBoxLayout()
        self.act_sel_all = QPushButton("☑️"); self.act_sel_all.setMaximumWidth(40); self.act_sel_all.clicked.connect(self.nets_select_all_visible); bulk_layout.addWidget(self.act_sel_all)
        self.act_desel_all = QPushButton("☐"); self.act_desel_all.setMaximumWidth(40); self.act_desel_all.clicked.connect(self.nets_deselect_all); bulk_layout.addWidget(self.act_desel_all)
        self.act_clear_all = QPushButton("❌"); self.act_clear_all.setMaximumWidth(40); self.act_clear_all.clicked.connect(self.clear_all_selections); bulk_layout.addWidget(self.act_clear_all)
        self.act_color_chk = QPushButton("🎨"); self.act_color_chk.setMaximumWidth(40); self.act_color_chk.clicked.connect(self.color_checked_nets); bulk_layout.addWidget(self.act_color_chk)
        self.act_reset_col = QPushButton("🔄"); self.act_reset_col.setMaximumWidth(40); self.act_reset_col.clicked.connect(self.reset_default_colors); bulk_layout.addWidget(self.act_reset_col)
        nets_layout.addLayout(bulk_layout)

        search_lay = QHBoxLayout()
        self.input_regex = QLineEdit()
        self.input_regex.setPlaceholderText("Search Nets (e.g., VDD)")
        self.input_regex.textChanged.connect(self.filter_nets_table)
        search_lay.addWidget(self.input_regex)
        nets_layout.addLayout(search_lay)

        self.nets_table = QTableWidget()
        self.nets_table.setAlternatingRowColors(True)
        self.nets_table.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
        self.nets_table.setColumnCount(4)
        self.nets_table.setHorizontalHeaderLabels(["Select", "Net Name", "Count", "Color"])
        self.nets_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.nets_table.setWordWrap(False)
        self.nets_table.verticalHeader().setVisible(False)
        self.nets_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.nets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        self.cb_delegate = CheckboxDelegate(self)
        self.nets_table.setItemDelegateForColumn(0, self.cb_delegate)
        self.nets_table.cellClicked.connect(self.on_net_checkbox_clicked)
        
        nets_layout.addWidget(self.nets_table)
        self.right_vert_splitter.addWidget(nets_widget)
        
        # 3. Console Panel
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(0, 10, 0, 0)
        console_layout.addWidget(QLabel("<b>Message Console</b>"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #FFFFFF; color: #000000; font-family: monospace; border: 1px solid #CCC; padding-bottom: 1em;")
        console_layout.addWidget(self.console)
        self.right_vert_splitter.addWidget(console_widget)

        right_layout.addWidget(self.right_vert_splitter)
        self.main_splitter.addWidget(self.right_pane)
        self.main_splitter.setSizes([1000, 300]) # 80/20 default ratio

    def log(self, message):
        self.console.append(f"> {message}")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def toggle_privacy(self, checked):
        self.is_blurred = checked
        if checked:
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(15)
            self.view.setGraphicsEffect(blur)
            self.view.viewport().update()
            self.log("Privacy filter ON. Map blurred.")
        else:
            self.view.setGraphicsEffect(None)
            self.view.viewport().update()
            self.log("Privacy filter OFF.")

    def save_state(self):
        state = {
            'grid_data': copy.deepcopy(self.grid_data),
            'unassigned_nets': copy.deepcopy(self.unassigned_nets),
            'net_frequences': copy.deepcopy(self.net_frequences),
            'net_view_state': copy.deepcopy(self.net_view_state),
            'manual_colors': copy.deepcopy(self.manual_colors)
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def _get_current_state(self):
        return {
            'grid_data': copy.deepcopy(self.grid_data),
            'unassigned_nets': copy.deepcopy(self.unassigned_nets),
            'net_frequences': copy.deepcopy(self.net_frequences),
            'net_view_state': copy.deepcopy(self.net_view_state),
            'manual_colors': copy.deepcopy(self.manual_colors)
        }

    def undo(self):
        if not self.undo_stack: return
        self.redo_stack.append(self._get_current_state())
        state = self.undo_stack.pop()
        self._apply_state(state)
        self.log("Undo applied.")

    def redo(self):
        if not self.redo_stack: return
        self.undo_stack.append(self._get_current_state())
        state = self.redo_stack.pop()
        self._apply_state(state)
        self.log("Redo applied.")

    def _apply_state(self, state):
        self.grid_data = copy.deepcopy(state['grid_data'])
        self.unassigned_nets = copy.deepcopy(state['unassigned_nets'])
        self.net_frequences = copy.deepcopy(state['net_frequences'])
        self.net_view_state = copy.deepcopy(state['net_view_state'])
        self.manual_colors = copy.deepcopy(state['manual_colors'])
        
        self.render_grid()
        self.populate_nets_table()
        self.refresh_unassigned_list()
        self.swap_selection = None

    def save_db(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Editor DB", "editor_session.json", "JSON Files (*.json)")
        if not file_path: return
        
        db_data = {
            "grid_data": self.grid_data,
            "unassigned_nets": self.unassigned_nets,
            "manual_colors": [{"r": r, "c": c, "color": color} for (r, c), color in self.manual_colors.items()],
            "net_frequences": self.net_frequences,
            "net_view_state": self.net_view_state
        }
        with open(file_path, 'w') as f: json.dump(db_data, f)
        self.log("Editor session database saved successfully.")

    def load_db(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Editor DB", "", "JSON Files (*.json)")
        if not file_path: return
        try:
            with open(file_path, 'r') as f: db_data = json.load(f)
            
            self.save_state() 
            
            self.grid_data = db_data.get("grid_data", self.grid_data)
            self.unassigned_nets = db_data.get("unassigned_nets", self.unassigned_nets)
            self.net_frequences = db_data.get("net_frequences", self.net_frequences)
            self.net_view_state = db_data.get("net_view_state", self.net_view_state)
            
            mc_list = db_data.get("manual_colors", [])
            self.manual_colors = {(item["r"], item["c"]): item["color"] for item in mc_list}
            
            self.render_grid()
            self.populate_nets_table()
            self.refresh_unassigned_list()
            
            self.log("Editor Database session loaded seamlessly.")
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    def filter_unassigned_list(self):
        query = self.unassigned_search.text().lower()
        for i in range(self.unassigned_list.count()):
            item = self.unassigned_list.item(i)
            item.setHidden(query not in item.text().lower())

    def _mock_wheel(self, delta):
        import PyQt6.QtGui as QtGui
        import PyQt6.QtCore as QtCore
        center = self.view.viewport().rect().center()
        return QtGui.QWheelEvent(QtCore.QPointF(center), QtCore.QPointF(center), QtCore.QPoint(0, delta), QtCore.QPoint(0, delta), Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)

    def toggle_pan(self, checked):
        self.pan_active = checked
        self.view.setInteractive(not checked)
        if checked:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            if self.act_swap.isChecked(): self.act_swap.setChecked(False)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def toggle_swap(self, checked):
        if checked:
            self.active_tool = "SWAP"
            self.swap_selection = None
            if self.pan_act.isChecked(): self.pan_act.setChecked(False)
            self.unassigned_list.clearSelection()
            self.selected_unassigned_net = None
            self.lbl_selected_unassigned.setText("Selected Net: None")
            self.log("Swap Mode Active. Click two cells to swap.")
        else:
            self.active_tool = "IDLE"
            if self.swap_selection:
                r, c = self.swap_selection.r, self.swap_selection.c
                self.swap_selection = None
                self.update_cell_color(r, c)
            self.log("Swap Mode Deactivated.")

    def on_unassigned_selected(self, item):
        self.active_tool = "ASSIGN"
        if self.act_swap.isChecked(): self.act_swap.setChecked(False)
        if self.pan_act.isChecked(): self.pan_act.setChecked(False)
        net_name = item.text().split(" (")[0]
        self.selected_unassigned_net = net_name
        self.lbl_selected_unassigned.setText(f"Selected Net: {net_name}")
        self.log(f"Assign Tool Active: Ready to place '{net_name}'")

    def refresh_unassigned_list(self):
        self.unassigned_list.clear()
        for net, count in sorted(self.unassigned_nets.items()):
            self.unassigned_list.addItem(f"{net} ({count})")
        
        total_pins = sum(self.unassigned_nets.values())
        self.lbl_unassigned_count.setText(f"Total Pins: {total_pins}")
        self.filter_unassigned_list()

    def handle_canvas_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        scene_pos = self.view.mapToScene(event.pos())
        item = self.scene.itemAt(scene_pos, self.view.transform())
        
        if isinstance(item, BallItem):
            if self.active_tool == "SWAP":
                if not self.swap_selection:
                    self.swap_selection = item
                    self.update_cell_color(item.r, item.c) 
                else:
                    item1 = self.swap_selection
                    item2 = item
                    
                    if item1 == item2:
                        self.swap_selection = None
                        self.update_cell_color(item1.r, item1.c)
                        return

                    n1, n2 = item1.net, item2.net
                    
                    reply = QMessageBox.question(self, "Confirm Swap", 
                                               f"Are you sure you want to swap the nets of {item1.pin} and {item2.pin}?\n\n"
                                               f"{item1.pin}: {n1} ⇄ {n2}\n"
                                               f"{item2.pin}: {n2} ⇄ {n1}",
                                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        self.save_state()
                        item1.net, item2.net = n2, n1
                        item1.display_text = n2.replace("_", "_\u200B")
                        item2.display_text = n1.replace("_", "_\u200B")
                        self.grid_data[item1.r][item1.c] = n2
                        self.grid_data[item2.r][item2.c] = n1
                        
                        self.swap_selection = None
                        self.update_cell_color(item1.r, item1.c)
                        self.update_cell_color(item2.r, item2.c)
                        
                        if n1 != n2:
                            self.log(f"Swapped {item1.pin} [{n1}] with {item2.pin} [{n2}]")
                    else:
                        self.swap_selection = None
                        self.update_cell_color(item1.r, item1.c)
                        self.update_cell_color(item2.r, item2.c)
                        self.log("Swap cancelled.")
                        
            elif self.active_tool == "ASSIGN" and self.selected_unassigned_net:
                old_net = item.net
                new_net = self.selected_unassigned_net
                if old_net == new_net: return
                
                self.save_state()
                
                if old_net:
                    self.unassigned_nets[old_net] = self.unassigned_nets.get(old_net, 0) + 1
                    
                self.unassigned_nets[new_net] -= 1
                
                item.net = new_net
                item.display_text = new_net.replace("_", "_\u200B")
                self.grid_data[item.r][item.c] = new_net
                
                if old_net:
                    self.net_frequences[old_net] -= 1
                self.net_frequences[new_net] = self.net_frequences.get(new_net, 0) + 1
                
                if new_net not in self.net_view_state:
                    self.net_view_state[new_net] = {"selected": False, "color": DEFAULT_CELL_BG}
                    self.default_net_colors[new_net] = DEFAULT_CELL_BG
                
                self.update_cell_color(item.r, item.c)
                
                if self.unassigned_nets[new_net] <= 0:
                    del self.unassigned_nets[new_net]
                    self.selected_unassigned_net = None
                    self.lbl_selected_unassigned.setText("Selected Net: None")
                    self.unassigned_list.clearSelection()
                    
                self.refresh_unassigned_list()
                self.populate_nets_table()
                
                msg = f"Assigned '{new_net}' to {item.pin}."
                if old_net: msg += f" Displaced '{old_net}' to container."
                self.log(msg)

    def handle_area_assignment(self):
        if self.active_tool != "ASSIGN" or not self.selected_unassigned_net: return
        selected = [i for i in self.scene.selectedItems() if isinstance(i, BallItem)]
        if not selected: return
        
        assigned_count = 0
        new_net = self.selected_unassigned_net
        state_saved = False
        
        for item in sorted(selected, key=lambda x: (x.r, x.c)):
            if not item.net:
                if not state_saved:
                    self.save_state()
                    state_saved = True
                    
                item.net = new_net
                item.display_text = new_net.replace("_", "_\u200B")
                self.grid_data[item.r][item.c] = new_net
                
                self.net_frequences[new_net] = self.net_frequences.get(new_net, 0) + 1
                if new_net not in self.net_view_state:
                    self.net_view_state[new_net] = {"selected": False, "color": DEFAULT_CELL_BG}
                    self.default_net_colors[new_net] = DEFAULT_CELL_BG
                    
                self.update_cell_color(item.r, item.c)
                
                self.unassigned_nets[new_net] -= 1
                assigned_count += 1
                
                if self.unassigned_nets[new_net] <= 0:
                    del self.unassigned_nets[new_net]
                    self.selected_unassigned_net = None
                    self.lbl_selected_unassigned.setText("Selected Net: None")
                    self.unassigned_list.clearSelection()
                    break
                    
        if assigned_count > 0:
            self.refresh_unassigned_list()
            self.populate_nets_table()
            self.log(f"Auto-assigned {assigned_count} instances of '{new_net}' via area selection.")

    def show_context_menu(self, pos):
        if not self.grid_data: return
        selected_items = [i for i in self.scene.selectedItems() if isinstance(i, BallItem)]
        if not selected_items: return
        
        menu = QMenu(self.view)
        unassign_act = menu.addAction("🗑️ Send to Unassigned Container")
        menu.addSeparator()
        color_act = menu.addAction("🎨 Set Custom Color...")
        clear_act = menu.addAction("❌ Clear Custom Color")
        
        action = menu.exec(self.view.mapToGlobal(pos))
        if action == unassign_act:
            unassigned_count = 0
            state_saved = False
            for item in selected_items:
                net = item.net
                if net:
                    if not state_saved:
                        self.save_state()
                        state_saved = True
                    self.unassigned_nets[net] = self.unassigned_nets.get(net, 0) + 1
                    item.net = ""
                    item.display_text = ""
                    self.grid_data[item.r][item.c] = ""
                    self.net_frequences[net] -= 1
                    self.update_cell_color(item.r, item.c)
                    unassigned_count += 1
            if unassigned_count > 0:
                self.refresh_unassigned_list()
                self.populate_nets_table()
                self.log(f"Unassigned {unassigned_count} pins to container.")
        elif action == color_act:
            color = QColorDialog.getColor()
            if color.isValid():
                self.save_state()
                hex_color = color.name()
                for item in selected_items:
                    self.manual_colors[(item.r, item.c)] = hex_color
                    self.update_cell_color(item.r, item.c)
        elif action == clear_act:
            self.save_state()
            for item in selected_items:
                if (item.r, item.c) in self.manual_colors:
                    del self.manual_colors[(item.r, item.c)]
                    self.update_cell_color(item.r, item.c)

    def export_excel(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Modified Map", "modified_map.xlsx", "Excel Files (*.xlsx)")
        if not file_path: return
        
        try:
            export_records = copy.deepcopy(self.parent_gui.current_records)
            y_vals = [r['Y Coord'] for r in export_records if r.get('Y Coord') != ""]
            x_vals = [r['X Coord'] for r in export_records if r.get('X Coord') != ""]
            unique_y = sorted(list(set(y_vals)), reverse=True)
            unique_x = sorted(list(set(x_vals)))
            y_to_row = {y: i for i, y in enumerate(unique_y)}
            x_to_col = {x: i for i, x in enumerate(unique_x)}
            
            for r_data in export_records:
                x, y = r_data.get('X Coord'), r_data.get('Y Coord')
                if x == "" or y == "": continue
                r, c = y_to_row[y], x_to_col[x]
                r_data['L2 Net Name'] = self.grid_data[r][c]
                
            df = pd.DataFrame(export_records)
            df.to_excel(file_path, sheet_name='L2 data', index=False)
            self.log(f"Successfully exported modified layout to '{os.path.basename(file_path)}'.")
            QMessageBox.information(self, "Export Complete", "Ball map successfully exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def fit_to_screen(self):
        if not self.grid_data: return
        self.view.resetTransform()
        br = self.scene.itemsBoundingRect()
        pad = 2000
        self.scene.setSceneRect(br.adjusted(-pad, -pad, pad, pad))
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.fitInView(br, Qt.AspectRatioMode.KeepAspectRatio)
        self.view.scale(0.95, 0.95)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def render_grid(self):
        self.scene.clear()
        self.ball_items.clear()
        if not self.grid_data: return
        rows, cols = len(self.grid_data), len(self.grid_data[0])

        for c in range(cols):
            self.scene.addItem(HeaderItem((c+1)*CELL_SIZE, 0, CELL_SIZE, CELL_SIZE, self.col_headers[c], self))
            self.scene.addItem(HeaderItem((c+1)*CELL_SIZE, (rows+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.col_headers[c], self))
        for r in range(rows):
            self.scene.addItem(HeaderItem(0, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.row_headers[r], self))
            self.scene.addItem(HeaderItem((cols+1)*CELL_SIZE, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.row_headers[r], self))

        for r in range(rows):
            for c in range(cols):
                val = self.grid_data[r][c]
                pin_name = f"{self.row_headers[r]}{self.col_headers[c]}"
                item = BallItem(r, c, val, pin_name, self)
                self.scene.addItem(item)
                self.ball_items[(r, c)] = item
                self.update_cell_color(r, c)

    def update_cell_color(self, r, c):
        item = self.ball_items.get((r, c))
        if not item: return
        
        bg_col = DEFAULT_CELL_BG
        val = self.grid_data[r][c]
        
        if (r, c) in self.manual_colors:
            bg_col = self.manual_colors[(r, c)]
        elif val and val in self.net_view_state and self.net_view_state[val]["color"] != DEFAULT_CELL_BG:
            bg_col = self.net_view_state[val]["color"]
            
        is_chk = val and val in self.net_view_state and self.net_view_state[val]["selected"]
        
        hl_col = None
        if self.swap_selection and self.swap_selection.r == r and self.swap_selection.c == c:
            hl_col = "cyan"
            
        item.update_visuals(bg_col, is_chk, hl_col)

    def populate_nets_table(self):
        self._updating_checks = True
        self.nets_table.setSortingEnabled(False)
        self.nets_table.setRowCount(0)
        if not self.net_view_state: 
            self._updating_checks = False
            return
            
        valid_nets = {k: v for k, v in self.net_frequences.items() if v > 0}
        sorted_nets = sorted(valid_nets.keys())
        self.nets_table.setRowCount(len(sorted_nets))

        for idx, net_name in enumerate(sorted_nets):
            state = self.net_view_state[net_name]
            
            chk_item = QTableWidgetItem("")
            chk_item.setData(Qt.ItemDataRole.UserRole, state["selected"])
            self.nets_table.setItem(idx, 0, chk_item)

            name_item = QTableWidgetItem(net_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(net_name)
            self.nets_table.setItem(idx, 1, name_item)

            count_item = NumericItem(str(valid_nets.get(net_name, 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setToolTip(str(valid_nets.get(net_name, 0)))
            self.nets_table.setItem(idx, 2, count_item)

            color_btn = QPushButton()
            color_btn.setStyleSheet(f"background-color: {state['color']}; border: 1px solid darkgray;")
            color_btn.setMinimumWidth(30)
            color_btn.clicked.connect(lambda checked, net=net_name, btn=color_btn: self.pick_net_color(net, btn))
            
            self.nets_table.setItem(idx, 3, QTableWidgetItem(""))
            self.nets_table.setCellWidget(idx, 3, color_btn)
            
        self.nets_table.setSortingEnabled(True)
        self._updating_checks = False

    def filter_nets_table(self):
        pattern = self.input_regex.text().strip()
        use_regex = self.cb_use_regex.isChecked()
        try:
            if use_regex: regex = re.compile(pattern, re.IGNORECASE)
        except re.error: return 

        for idx in range(self.nets_table.rowCount()):
            net_name_item = self.nets_table.item(idx, 1)
            if net_name_item:
                net_text = net_name_item.text()
                if use_regex: is_visible = bool(regex.fullmatch(net_text)) if pattern else True
                else: is_visible = pattern.upper() in net_text.upper() 
                self.nets_table.setRowHidden(idx, not is_visible)

    def on_net_checkbox_clicked(self, row, col):
        if getattr(self, '_updating_checks', False): return
        if col == 0:
            item = self.nets_table.item(row, 0)
            net_name = self.nets_table.item(row, 1).text()
            current_state = item.data(Qt.ItemDataRole.UserRole)
            new_state = not current_state
            item.setData(Qt.ItemDataRole.UserRole, new_state)
            
            self.net_view_state[net_name]["selected"] = new_state
            self.on_selection_changed()
            for b_item in self.ball_items.values():
                if b_item.net == net_name:
                    self.update_cell_color(b_item.r, b_item.c)

    def pick_net_color(self, net_name, color_btn):
        color = QColorDialog.getColor(QColor(self.net_view_state[net_name]["color"]))
        if color.isValid():
            self.save_state()
            hex_color = color.name()
            self.net_view_state[net_name]["color"] = hex_color
            color_btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
            
            for item in self.ball_items.values():
                if item.net == net_name:
                    self.update_cell_color(item.r, item.c)

    def nets_select_all_visible(self):
        self._updating_checks = True
        self.nets_table.setUpdatesEnabled(False)
        for i in range(self.nets_table.rowCount()):
            if not self.nets_table.isRowHidden(i):
                self.nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, True)
                net_name = self.nets_table.item(i, 1).text()
                self.net_view_state[net_name]["selected"] = True
                
        self.nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.on_selection_changed()
        for item in self.ball_items.values():
            if item.net in self.net_view_state and self.net_view_state[item.net]["selected"]: 
                self.update_cell_color(item.r, item.c)

    def nets_deselect_all(self):
        self._updating_checks = True
        self.nets_table.setUpdatesEnabled(False)
        for i in range(self.nets_table.rowCount()):
            self.nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, False)
            net_name = self.nets_table.item(i, 1).text()
            self.net_view_state[net_name]["selected"] = False
            
        self.nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.scene.clearSelection()
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)

    def clear_all_selections(self):
        self.save_state()
        self.nets_deselect_all()
        self.manual_colors.clear()
        
        for net_name in self.net_view_state.keys():
            self.net_view_state[net_name]["color"] = DEFAULT_CELL_BG
            for i in range(self.nets_table.rowCount()):
                if self.nets_table.item(i, 1).text() == net_name:
                    color_btn = self.nets_table.cellWidget(i, 3)
                    color_btn.setStyleSheet(f"background-color: {DEFAULT_CELL_BG}; border: 1px solid darkgray;")
                    
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
        self.log("Cleared all selections and wiped assigned colors.")

    def color_checked_nets(self):
        checked_nets = []
        for i in range(self.nets_table.rowCount()):
            if not self.nets_table.isRowHidden(i):
                if self.nets_table.item(i, 0).data(Qt.ItemDataRole.UserRole):
                    checked_nets.append(self.nets_table.item(i, 1).text())
                    
        valid_items = [i for i in self.scene.selectedItems() if isinstance(i, BallItem)]
                
        if not checked_nets and not valid_items: return
        
        color = QColorDialog.getColor()
        if color.isValid():
            self.save_state()
            hex_color = color.name()
            
            for net_name in checked_nets:
                self.net_view_state[net_name]["color"] = hex_color
                for i in range(self.nets_table.rowCount()):
                    if self.nets_table.item(i, 1).text() == net_name:
                        self.nets_table.cellWidget(i, 3).setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
                        break
                        
            for item in self.ball_items.values():
                if item.net in checked_nets:
                    self.update_cell_color(item.r, item.c)
                    
            for item in valid_items:
                self.manual_colors[(item.r, item.c)] = hex_color
                self.update_cell_color(item.r, item.c)

    def reset_default_colors(self):
        self.save_state()
        for net_name in self.net_view_state.keys():
            self.net_view_state[net_name]["color"] = self.default_net_colors.get(net_name, DEFAULT_CELL_BG)
        
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
                
        for i in range(self.nets_table.rowCount()):
            net_name = self.nets_table.item(i, 1).text()
            c_btn = self.nets_table.cellWidget(i, 3)
            c_btn.setStyleSheet(f"background-color: {self.net_view_state[net_name]['color']}; border: 1px solid darkgray;")
        self.log("Colors reset to default VDD/VSS palettes.")

    def on_selection_changed(self):
        native_sel = sum(1 for i in self.scene.selectedItems() if isinstance(i, BallItem))
        net_sel_count = 0
        
        checked_nets = {net for net, state in self.net_view_state.items() if state.get("selected")}
        if checked_nets and self.grid_data:
            for (r, c), item in self.ball_items.items():
                if item.net in checked_nets and not item.isSelected():
                    net_sel_count += 1
                            
        total = native_sel + net_sel_count
        self.lbl_selection.setText(f"<b>Selected Cells:</b> {total}")


class BallMapViewer(QMainWindow):
    def __init__(self, debug_mode=False):
        super().__init__()
        self.debug_mode = debug_mode
        self.draw_circles = False
        self.adaptive_font = True
        self._updating_checks = False
        self.is_blurred = False
        self.setWindowTitle(f"Ball Map Viewer v{__version__}")
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        icon_path = os.path.join(base_dir, "BallMapViewer.ico")
        if os.path.exists(icon_path): 
            self.setWindowIcon(QIcon(icon_path))
        
        self.current_records = []
        self.current_pin_map = {}
        self.grid_data, self.full_pin_data = [], {}
        self.row_headers, self.col_headers = [], []
        self.pin_to_cell, self.net_frequences, self.net_view_state = {}, {}, {}
        self.ball_items = {}
        self.saved_views = {} 
        self.manual_colors = {} 
        self.default_net_colors = {} 
        self.recent_files = []
        
        self.active_violation_cells = set()
        self.active_passing_cells = set()
        self.active_waived_cells = set()
        self.valid_diff_pairs = {}
        self.waived_violations = set()
        self.drc_results = {}
        
        self.base_device, self.base_version = "Unknown", "0.0"
        self.view_counter = 1
        self.pan_active = False

        self.load_recent_files()
        self.init_ui()
        self.log("Ball Map Viewer initialized. Awaiting file input...")

    def init_ui(self):
        self.create_menus()
        self.create_toolbar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                width: 6px;
            }
        """)
        main_layout.addWidget(self.splitter)

        self.scene = QGraphicsScene()
        self.view = EDA_Canvas(self)
        self.view.setScene(self.scene)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_context_menu)
        
        self.splitter.addWidget(self.view)

        self.right_pane = QWidget()
        right_layout = QVBoxLayout(self.right_pane)
        right_layout.setContentsMargins(0,0,0,0)
        
        self.right_vert_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_vert_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eee, stop:0.4 #eee, stop:0.5 #888, stop:0.6 #eee, stop:1 #eee);
                height: 6px;
            }
        """)
        
        # 1. Nets Panel
        nets_widget = QWidget()
        nets_layout = QVBoxLayout(nets_widget)
        nets_layout.setContentsMargins(0,0,0,0)
        
        nets_layout.addWidget(QLabel("<b>Dynamic Net Control</b>"))
        
        bulk_layout = QHBoxLayout()
        self.act_sel_all = QPushButton("☑️"); self.act_sel_all.setMaximumWidth(40); self.act_sel_all.setToolTip("Select All Visible Nets"); self.act_sel_all.clicked.connect(self.nets_select_all_visible); bulk_layout.addWidget(self.act_sel_all)
        self.act_desel_all = QPushButton("☐"); self.act_desel_all.setMaximumWidth(40); self.act_desel_all.setToolTip("Deselect All"); self.act_desel_all.clicked.connect(self.nets_deselect_all); bulk_layout.addWidget(self.act_desel_all)
        self.act_clear_all = QPushButton("❌"); self.act_clear_all.setMaximumWidth(40); self.act_clear_all.setToolTip("Clear Colors"); self.act_clear_all.clicked.connect(self.clear_all_selections); bulk_layout.addWidget(self.act_clear_all)
        self.act_color_chk = QPushButton("🎨"); self.act_color_chk.setMaximumWidth(40); self.act_color_chk.setToolTip("Color Checked"); self.act_color_chk.clicked.connect(self.color_checked_nets); bulk_layout.addWidget(self.act_color_chk)
        self.act_reset_col = QPushButton("🔄"); self.act_reset_col.setMaximumWidth(40); self.act_reset_col.setToolTip("Reset Defaults"); self.act_reset_col.clicked.connect(self.reset_default_colors); bulk_layout.addWidget(self.act_reset_col)
        nets_layout.addLayout(bulk_layout)

        search_lay = QHBoxLayout()
        self.input_regex = QLineEdit()
        self.input_regex.setPlaceholderText("Search Nets (e.g., VDD)")
        self.input_regex.textChanged.connect(self.filter_nets_table)
        self.cb_use_regex = QCheckBox("Use strict Regex")
        self.cb_use_regex.stateChanged.connect(self.filter_nets_table)
        btn_info = QPushButton("ℹ️")
        btn_info.setMaximumWidth(30)
        btn_info.clicked.connect(self.show_regex_info)
        search_lay.addWidget(self.input_regex)
        search_lay.addWidget(self.cb_use_regex)
        search_lay.addWidget(btn_info)
        nets_layout.addLayout(search_lay)

        self.nets_table = QTableWidget()
        self.nets_table.setAlternatingRowColors(True)
        self.nets_table.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
        self.nets_table.setColumnCount(4)
        self.nets_table.setHorizontalHeaderLabels(["Select", "Net Name", "Count", "Color"])
        self.nets_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.nets_table.setWordWrap(False)
        self.nets_table.verticalHeader().setVisible(False)
        self.nets_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.nets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        self.cb_delegate = CheckboxDelegate(self)
        self.nets_table.setItemDelegateForColumn(0, self.cb_delegate)
        self.nets_table.cellClicked.connect(self.on_net_checkbox_clicked)
        
        nets_layout.addWidget(self.nets_table)
        
        self.right_vert_splitter.addWidget(nets_widget)
        
        # 2. DRC Violations Panel
        viol_widget = QWidget()
        viol_layout = QVBoxLayout(viol_widget)
        viol_layout.setContentsMargins(0, 10, 0, 0)
        
        self.drc_tabs = QTabWidget()
        
        viol_tab = QWidget()
        v_lay = QVBoxLayout(viol_tab)
        v_lay.setContentsMargins(0, 5, 0, 0)
        
        drc_btn_lay = QHBoxLayout()
        self.btn_export_drc = QPushButton("💾 Export Report")
        self.btn_export_drc.clicked.connect(self.export_drc)
        self.btn_export_waivers = QPushButton("📤 Export Waivers")
        self.btn_export_waivers.clicked.connect(self.export_waivers)
        self.btn_import_waivers = QPushButton("📥 Import Waivers")
        self.btn_import_waivers.clicked.connect(self.import_waivers)
        drc_btn_lay.addWidget(self.btn_export_drc)
        drc_btn_lay.addWidget(self.btn_import_waivers)
        drc_btn_lay.addWidget(self.btn_export_waivers)
        v_lay.addLayout(drc_btn_lay)
        
        waive_btn_lay = QHBoxLayout()
        self.btn_waive_selected = QPushButton("✓ Waive Selected")
        self.btn_waive_selected.clicked.connect(self.waive_selected_items)
        self.btn_unwaive_selected = QPushButton("↺ Un-waive Selected")
        self.btn_unwaive_selected.clicked.connect(self.unwaive_selected_items)
        waive_btn_lay.addWidget(self.btn_waive_selected)
        waive_btn_lay.addWidget(self.btn_unwaive_selected)
        v_lay.addLayout(waive_btn_lay)
        
        self.drc_tree = QTreeWidget()
        self.drc_tree.setHeaderHidden(True)
        self.drc_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.drc_tree.setAlternatingRowColors(True)
        self.drc_tree.setStyleSheet("QTreeWidget { alternate-background-color: #F0F0F0; background-color: #FFFFFF; }")
        
        self.drc_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.drc_tree.header().setStretchLastSection(False)
        self.drc_tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        self.html_delegate = HTMLDelegate(self.drc_tree, self.debug_mode)
        self.drc_tree.setItemDelegate(self.html_delegate)
        self.drc_tree.itemSelectionChanged.connect(self.on_drc_selection_changed)
        v_lay.addWidget(self.drc_tree)
        self.drc_tabs.addTab(viol_tab, "DRC Scan")
        
        diff_tab = QWidget()
        d_lay = QVBoxLayout(diff_tab)
        d_lay.setContentsMargins(0, 5, 0, 0)
        
        diff_btns = QHBoxLayout()
        self.btn_color_diffs = QPushButton("🎨 Auto-Color All Diff Pairs")
        self.btn_color_diffs.clicked.connect(self.auto_color_diff_pairs)
        self.btn_clear_diffs = QPushButton("❌ Clear Diff Colors")
        self.btn_clear_diffs.clicked.connect(self.clear_auto_color_diff_pairs)
        diff_btns.addWidget(self.btn_color_diffs)
        diff_btns.addWidget(self.btn_clear_diffs)
        d_lay.addLayout(diff_btns)
        
        self.diff_pairs_list = QListWidget()
        self.diff_pairs_list.setAlternatingRowColors(True)
        self.diff_pairs_list.setStyleSheet("alternate-background-color: #F0F0F0; background-color: #FFFFFF;")
        self.diff_pairs_list.setSortingEnabled(True)
        self.diff_pairs_list.itemSelectionChanged.connect(self.on_diff_pair_selected)
        d_lay.addWidget(self.diff_pairs_list)
        self.drc_tabs.addTab(diff_tab, "Differential Pairs")
        
        info_tab = QWidget()
        i_lay = QVBoxLayout(info_tab)
        i_lay.setContentsMargins(0, 5, 0, 0)
        self.drc_info_text = QTextEdit()
        self.drc_info_text.setReadOnly(True)
        i_lay.addWidget(self.drc_info_text)
        self.drc_tabs.addTab(info_tab, "Rules Info")
        
        viol_layout.addWidget(self.drc_tabs)
        self.right_vert_splitter.addWidget(viol_widget)

        # 3. Console Panel
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(0, 10, 0, 0)
        
        console_layout.addWidget(QLabel("<b>Message Console</b>"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #FFFFFF; color: #000000; font-family: monospace; border: 1px solid #CCC; padding-bottom: 1em;")
        console_layout.addWidget(self.console)
        self.right_vert_splitter.addWidget(console_widget)

        right_layout.addWidget(self.right_vert_splitter)
        self.splitter.addWidget(self.right_pane)
        
        fm = QFontMetrics(self.console.font())
        five_lines_px = fm.lineSpacing() * 5
        panel_min_h = five_lines_px + 45

        self.splitter.setSizes([1000, 400])
        self.right_vert_splitter.setSizes([500, panel_min_h, panel_min_h])

    def get_recent_files_path(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "recent_files.json")

    def load_recent_files(self):
        self.recent_files = []
        filepath = self.get_recent_files_path()
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, list):
                        self.recent_files = loaded_data
            except: pass

    def save_recent_files(self):
        try:
            filepath = self.get_recent_files_path()
            with open(filepath, "w") as f:
                json.dump(self.recent_files, f)
        except: pass

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[:10]
        self.save_recent_files()
        self.update_recent_menu()
        
        # Also sync up the Diff GUI if it's currently open
        if hasattr(self, 'active_diff_dialog') and self.active_diff_dialog.isVisible():
            self.active_diff_dialog.update_recent_menus()

    def update_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            act = QAction("No Recent Files", self)
            act.setEnabled(False)
            self.recent_menu.addAction(act)
            return
        for path in self.recent_files:
            act = QAction(os.path.basename(path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self.load_excel(p))
            self.recent_menu.addAction(act)

    def apply_preferences(self):
        for item in self.ball_items.values():
            item.cached_font = None
        self.view.viewport().update()

    def show_regex_info(self):
        QMessageBox.information(self, "Regex Match Info", 
        "<b>Regex Matching Rules:</b><br><br>"
        "• <b>^VDD.*</b> : Matches any net starting with VDD.<br>"
        "• <b>.*CLK.*</b> : Matches any net containing CLK.<br>"
        "• <b>_N\\d+$</b> : Matches nets ending in _N followed by a number.<br><br>"
        "<i>Check 'Use strict Regex' to evaluate rules. Otherwise, uses simple sub-string matching.</i>")

    def log(self, message):
        self.console.append(f"> {message}")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def on_selection_changed(self):
        native_sel = sum(1 for i in self.scene.selectedItems() if isinstance(i, BallItem))
        net_sel_count = 0
        
        checked_nets = {net for net, state in self.net_view_state.items() if state.get("selected")}
        if checked_nets and self.grid_data:
            for (r, c), item in self.ball_items.items():
                if item.net in checked_nets and not item.isSelected():
                    net_sel_count += 1
                            
        total = native_sel + net_sel_count
        self.lbl_selection.setText(f"<b>Selected Cells:</b> {total}")

    def create_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        open_act = QAction("Open Excel...", self)
        open_act.triggered.connect(lambda: self.load_excel())
        file_menu.addAction(open_act)
        
        self.recent_menu = file_menu.addMenu("Recently Opened")
        self.update_recent_menu()
        
        file_menu.addSeparator()
        
        save_db_act = QAction("Save Session (DB)...", self)
        save_db_act.triggered.connect(self.save_db)
        file_menu.addAction(save_db_act)
        
        load_db_act = QAction("Load Session (DB)...", self)
        load_db_act.triggered.connect(self.load_db)
        file_menu.addAction(load_db_act)

        file_menu.addSeparator()
        
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        edit_menu = menubar.addMenu("Edit")
        pref_act = QAction("Preferences...", self)
        pref_act.triggered.connect(lambda: PreferencesDialog(self).exec())
        edit_menu.addAction(pref_act)
        
        tools_menu = menubar.addMenu("Tools")
        editor_act = QAction("Launch Ball Map Editor...", self)
        editor_act.triggered.connect(self.launch_editor_gui)
        tools_menu.addAction(editor_act)
        tools_menu.addSeparator()
        diff_act = QAction("Launch Diff Interface...", self)
        diff_act.triggered.connect(self.launch_diff_gui)
        tools_menu.addAction(diff_act)

        help_menu = menubar.addMenu("Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(lambda: QMessageBox.about(self, "About", f"Ball Map Viewer v{__version__}\nHardware EDA utility."))
        help_menu.addAction(about_act)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        z_in = QAction("🔍+", self); z_in.setToolTip("Zoom In"); z_in.triggered.connect(lambda: self.view.wheelEvent(self._mock_wheel(120))); toolbar.addAction(z_in)
        z_out = QAction("🔍-", self); z_out.setToolTip("Zoom Out"); z_out.triggered.connect(lambda: self.view.wheelEvent(self._mock_wheel(-120))); toolbar.addAction(z_out)
        fit = QAction("⛶", self); fit.setToolTip("Fit to Screen"); fit.triggered.connect(self.fit_to_screen); toolbar.addAction(fit)
        
        toolbar.addSeparator()
        self.pan_act = QAction("✋", self); self.pan_act.setToolTip("Pan Mode"); self.pan_act.setCheckable(True); self.pan_act.toggled.connect(self.toggle_pan); toolbar.addAction(self.pan_act)
        
        self.toggle_side_act = QAction("🗔", self); self.toggle_side_act.setToolTip("Toggle Sidebar"); self.toggle_side_act.triggered.connect(self.toggle_sidebar); toolbar.addAction(self.toggle_side_act)

        toolbar.addSeparator()
        self.input_view_name = QLineEdit()
        self.input_view_name.setPlaceholderText("View Name...")
        self.input_view_name.setMaximumWidth(150)
        toolbar.addWidget(self.input_view_name)

        self.act_save_view = QAction("💾", self); self.act_save_view.setToolTip("Save Session View"); self.act_save_view.triggered.connect(self.save_view); toolbar.addAction(self.act_save_view)

        self.combo_views = QComboBox()
        self.combo_views.setMaximumWidth(150)
        toolbar.addWidget(self.combo_views)

        self.act_load_view = QAction("📂", self); self.act_load_view.setToolTip("Load Selected View"); self.act_load_view.triggered.connect(self.load_view); toolbar.addAction(self.act_load_view)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        toolbar.addWidget(spacer)
        
        self.lbl_selection = QLabel("<b>Selected Cells:</b> 0")
        self.lbl_selection.setContentsMargins(0, 0, 10, 0)
        toolbar.addWidget(self.lbl_selection)
        
        self.btn_privacy = QAction("👁️ Privacy Blur", self)
        self.btn_privacy.setCheckable(True)
        self.btn_privacy.setToolTip("Toggle Privacy Filter")
        self.btn_privacy.toggled.connect(self.toggle_privacy)
        toolbar.addAction(self.btn_privacy)

    def _mock_wheel(self, delta):
        import PyQt6.QtGui as QtGui
        import PyQt6.QtCore as QtCore
        center = self.view.viewport().rect().center()
        return QtGui.QWheelEvent(QtCore.QPointF(center), QtCore.QPointF(center), QtCore.QPoint(0, delta), QtCore.QPoint(0, delta), Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)

    def toggle_sidebar(self):
        self.right_pane.setVisible(not self.right_pane.isVisible())
        self.fit_to_screen()

    def toggle_pan(self, checked):
        self.pan_active = checked
        self.view.setInteractive(not checked)
        if checked:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def toggle_privacy(self, checked):
        self.is_blurred = checked
        if checked:
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(15)
            self.view.setGraphicsEffect(blur)
            self.view.viewport().update()
            self.log("Privacy filter ON. Map blurred.")
        else:
            self.view.setGraphicsEffect(None)
            self.view.viewport().update()
            self.log("Privacy filter OFF.")

    def show_context_menu(self, pos):
        if not self.grid_data: return
        selected_items = [i for i in self.scene.selectedItems() if isinstance(i, BallItem)]
        if not selected_items: return
        
        menu = QMenu(self.view)
        color_action = menu.addAction("🎨 Set Color for Selected Balls...")
        clear_action = menu.addAction("❌ Clear Manual Color")
        
        action = menu.exec(self.view.mapToGlobal(pos))
        if action == color_action:
            color = QColorDialog.getColor()
            if color.isValid():
                hex_color = color.name()
                for item in selected_items:
                    self.manual_colors[(item.r, item.c)] = hex_color
                    self.update_cell_color(item.r, item.c)
        elif action == clear_action:
            for item in selected_items:
                if (item.r, item.c) in self.manual_colors:
                    del self.manual_colors[(item.r, item.c)]
                    self.update_cell_color(item.r, item.c)

    def fit_to_screen(self):
        if not self.grid_data: return
        cols = len(self.grid_data[0])
        rows = len(self.grid_data)
        
        self.view.resetTransform()
        
        br = self.scene.itemsBoundingRect()
        pad = 2000
        self.scene.setSceneRect(br.adjusted(-pad, -pad, pad, pad))
        
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.fitInView(br, Qt.AspectRatioMode.KeepAspectRatio)
        self.view.scale(0.95, 0.95)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        if self.debug_mode: print(f"[DEBUG] Executed CAD View Fit-To-Screen: {cols}x{rows} grid")

    def extract_metadata(self, filename):
        match = re.search(r"(.*?)_?rev_([\d\.]+)", filename, re.IGNORECASE)
        if match: return (match.group(1).strip('_') or "Unknown_Device", match.group(2))
        return "Unknown_Device", "0.0"

    def parse_excel_to_dict(self, file_path):
        df = pd.read_excel(file_path, sheet_name='L2 data')
        df.columns = df.columns.str.strip()
        pin_map = {}
        records = []
        for index, row in df.iterrows():
            row_dict = row.to_dict()
            clean_row = {k: ("" if pd.isna(v) else v) for k, v in row_dict.items()}
            
            pin = str(clean_row.get('Pin Number', '')).strip()
            net = str(clean_row.get('L2 Net Name', '')).strip()
            
            if pin and pin != 'nan' and net and net != 'nan':
                pin_map[pin] = net
                
            records.append(clean_row)
        return records, pin_map

    def export_drc(self):
        if self.drc_tree.topLevelItemCount() == 0:
            QMessageBox.information(self, "Export", "No violations to export.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Violations", "", "Excel Files (*.xlsx)")
        if not file_path: return
        
        data = []
        for i in range(self.drc_tree.topLevelItemCount()):
            rule_node = self.drc_tree.topLevelItem(i)
            rule_name = rule_node.data(0, Qt.ItemDataRole.UserRole + 2) or "General"
            for j in range(rule_node.childCount()):
                state_node = rule_node.child(j)
                state = state_node.data(0, Qt.ItemDataRole.UserRole + 1)
                for k in range(state_node.childCount()):
                    item = state_node.child(k)
                    msg_html = item.text(0)
                    msg_clean = re.sub(r'<[^>]+>', '', msg_html) 
                    cells = item.data(0, Qt.ItemDataRole.UserRole)
                    
                    pins_str = ""
                    if cells:
                        pins = [f"{self.row_headers[r]}{self.col_headers[c]}" for r, c in cells if 0 <= r < len(self.row_headers) and 0 <= c < len(self.col_headers)]
                        pins_str = ", ".join(pins)
                        
                    data.append({"Category": rule_name, "Result": state.upper(), "Description": msg_clean, "Affected Cells": pins_str})
            
        pd.DataFrame(data).to_excel(file_path, index=False)
        self.log(f"Exported structured DRC tree to {file_path}")

    def export_waivers(self):
        if not self.waived_violations:
            QMessageBox.information(self, "Export Waivers", "No waivers currently exist.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Waivers", "waivers.json", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(list(self.waived_violations), f, indent=4)
            self.log(f"Exported {len(self.waived_violations)} waivers.")

    def import_waivers(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Waivers", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    self.waived_violations.update(data)
                self.render_drc_tree()
                self.log(f"Imported waivers from {os.path.basename(file_path)}.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import waivers:\n{str(e)}")

    def waive_selected_items(self):
        items_to_waive = []
        
        def collect_items(item):
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            item_id = item.data(0, Qt.ItemDataRole.UserRole + 3)
            if item_type == "fail" and item_id:
                items_to_waive.append(item_id)
            for i in range(item.childCount()):
                collect_items(item.child(i))

        for item in self.drc_tree.selectedItems():
            collect_items(item)
        
        if not items_to_waive:
            QMessageBox.information(self, "Waive", "No failed items are selected.")
            return
            
        reply = QMessageBox.question(self, "Confirm Waiver", f"Are you sure you want to waive {len(set(items_to_waive))} violations?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.waived_violations.update(items_to_waive)
            self.render_drc_tree()
            self.log(f"Waived {len(set(items_to_waive))} violations.")

    def unwaive_selected_items(self):
        items_to_unwaive = []
        
        def collect_items(item):
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            item_id = item.data(0, Qt.ItemDataRole.UserRole + 3)
            if item_type == "waived" and item_id:
                items_to_unwaive.append(item_id)
            for i in range(item.childCount()):
                collect_items(item.child(i))

        for item in self.drc_tree.selectedItems():
            collect_items(item)
        
        if not items_to_unwaive:
            QMessageBox.information(self, "Un-waive", "No waived items are selected.")
            return
            
        reply = QMessageBox.question(self, "Confirm Un-waive", f"Are you sure you want to un-waive {len(set(items_to_unwaive))} violations?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for item_id in set(items_to_unwaive):
                self.waived_violations.discard(item_id)
            self.render_drc_tree()
            self.log(f"Un-waived {len(set(items_to_unwaive))} violations.")

    def on_drc_selection_changed(self):
        self.active_violation_cells.clear()
        self.active_passing_cells.clear()
        self.active_waived_cells.clear()
        
        def extract_cells(node, force_state=None):
            c = node.data(0, Qt.ItemDataRole.UserRole) or []
            s = force_state or node.data(0, Qt.ItemDataRole.UserRole + 1)
            
            if s == 'fail': self.active_violation_cells.update(c)
            elif s == 'pass': self.active_passing_cells.update(c)
            elif s == 'waived': self.active_waived_cells.update(c)
            
            for i in range(node.childCount()):
                extract_cells(node.child(i), s)
                
        for item in self.drc_tree.selectedItems():
            extract_cells(item)
            
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)

    def run_drc(self):
        self.valid_diff_pairs.clear()
        if hasattr(self, 'diff_pairs_list'): self.diff_pairs_list.clear()
        self.active_violation_cells.clear()
        self.active_passing_cells.clear()
        self.active_waived_cells.clear()
        
        self.drc_results = {
            "Proximity Check": {"pass": [], "fail": []},
            "Symmetry (Numbered)": {"pass": [], "fail": []},
            "Symmetry (Unnumbered)": {"pass": [], "fail": []}
        }
        
        rows, cols = len(self.grid_data), len(self.grid_data[0])
        net_pin_counts = {}
        for r in range(rows):
            for c in range(cols):
                net = self.grid_data[r][c]
                if net:
                    net_pin_counts[net] = net_pin_counts.get(net, 0) + 1
                    
        # --- DIFFERENTIAL PAIR DETECTION ---
        diff_pattern = re.compile(r'^(.*)_([NP])$', re.IGNORECASE)
        potential_pairs = {}
        for net in net_pin_counts.keys():
            m = diff_pattern.match(net)
            if m:
                base, pfx = m.groups()
                pfx = pfx.upper()
                if base not in potential_pairs: potential_pairs[base] = {}
                potential_pairs[base][pfx] = net
                
        self.valid_diff_pairs = {b: pairs for b, pairs in potential_pairs.items() if 'P' in pairs and 'N' in pairs}
        for b in sorted(self.valid_diff_pairs.keys()):
            if hasattr(self, 'diff_pairs_list'): self.diff_pairs_list.addItem(f"{b} (_P / _N)")

        # --- DRC ENGINE ---
        failed_prox_nets = set()

        for r in range(rows):
            for c in range(cols):
                net = self.grid_data[r][c]
                if not net or "CLK" not in net.upper(): continue
                
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0: continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols:
                            neighbor_net = self.grid_data[nr][nc]
                            if neighbor_net and "VDD" in neighbor_net.upper():
                                failed_prox_nets.add(net)
                                msg = f"CLK '{net}' touching VDD '{neighbor_net}' at Pin {self.row_headers[r]}{self.col_headers[c]}"
                                self.drc_results["Proximity Check"]["fail"].append({
                                    "id": f"Prox::{net}::{self.row_headers[r]}{self.col_headers[c]}::vs::{neighbor_net}::{self.row_headers[nr]}{self.col_headers[nc]}",
                                    "raw": msg, "html": msg, "cells": [(r, c), (nr, nc)]
                                })

        for r in range(rows):
            for c in range(cols):
                net = self.grid_data[r][c]
                if net and "CLK" in net.upper() and net not in failed_prox_nets:
                    msg = f"Safe CLK Net: {net}"
                    self.drc_results["Proximity Check"]["pass"].append({
                        "id": f"ProxPass::{net}", "raw": msg, "html": msg, "cells": [(r, c)]
                    })

        numbered_pattern = re.compile(r'^(.*?)_([NS])(\d+)(.*)$', re.IGNORECASE)
        unnumbered_pattern = re.compile(r'^(.*)_([NS])$', re.IGNORECASE)
        
        global_numbered = set()
        numbered_nets = {}
        unnumbered_nets = {}
        
        for net, count in net_pin_counts.items():
            match_num = numbered_pattern.match(net)
            if match_num:
                g1, ns, num, g4 = match_num.groups()
                die = f"{ns.upper()}{num}"
                global_numbered.add(die)
                
                base_key = f"{g1}____{g4}"
                if base_key not in numbered_nets: numbered_nets[base_key] = {'g1': g1, 'g4': g4, 'counts': {}}
                numbered_nets[base_key]['counts'][die] = count
                continue
                
            match_unnum = unnumbered_pattern.match(net)
            if match_unnum:
                base, pfx = match_unnum.groups()
                pfx = pfx.upper()
                if base not in unnumbered_nets: unnumbered_nets[base] = {}
                unnumbered_nets[base][pfx] = count

        if global_numbered:
            self.log(f"DRC Config: Detected Numbered Dies - {sorted(list(global_numbered))}")

        for base_key, data in numbered_nets.items():
            g1 = data['g1']
            g4 = data['g4']
            dies_present = data['counts']
            missing = global_numbered - set(dies_present.keys())
            
            cells = []
            expected_nets = [f"{g1}_{die}{g4}" for die in global_numbered]
            for pin, (r, c) in self.pin_to_cell.items():
                if self.grid_data[r][c].upper() in [en.upper() for en in expected_nets]:
                    cells.append((r, c))

            base_display = f"{g1}_*{g4}"
            max_count = max(dies_present.values()) if dies_present else 0
            
            if missing or len(set(dies_present.values())) > 1:
                details_html = []
                details_raw = []
                for expected_die in sorted(global_numbered):
                    if expected_die in missing:
                        details_html.append(f"[<span style='color:red;'>{expected_die}: Missing</span>]")
                        details_raw.append(f"[{expected_die}: Missing]")
                    else:
                        c = dies_present[expected_die]
                        if c < max_count:
                            details_html.append(f"[<span style='color:red;'>{expected_die}: {c}</span>]")
                        else:
                            details_html.append(f"[<span style='color:green;'>{expected_die}: {c}</span>]")
                        details_raw.append(f"[{expected_die}: {c}]")
                        
                self.drc_results["Symmetry (Numbered)"]["fail"].append({
                    "id": f"SymNum::{base_key}",
                    "html": f"Mismatch on '{base_display}'. " + " ".join(details_html),
                    "raw": f"Mismatch on '{base_display}'. " + " ".join(details_raw),
                    "cells": cells
                })
            else:
                msg = f"Matched '{base_display}' ({max_count} pins/die)"
                self.drc_results["Symmetry (Numbered)"]["pass"].append({
                    "id": f"SymNumPass::{base_key}", "html": msg, "raw": msg, "cells": cells
                })

        for base, dies_present in unnumbered_nets.items():
            expected_unnumbered = {'N', 'S'}
            missing = expected_unnumbered - set(dies_present.keys())
            
            cells = []
            for pin, (r, c) in self.pin_to_cell.items():
                if self.grid_data[r][c].upper() in [f"{base}_N".upper(), f"{base}_S".upper()]:
                    cells.append((r, c))

            max_count = max(dies_present.values()) if dies_present else 0
            if missing or len(set(dies_present.values())) > 1:
                details_html = []
                details_raw = []
                for expected_die in sorted(expected_unnumbered):
                    if expected_die in missing:
                        details_html.append(f"[<span style='color:red;'>{expected_die}: Missing</span>]")
                        details_raw.append(f"[{expected_die}: Missing]")
                    else:
                        c = dies_present[expected_die]
                        if c < max_count:
                            details_html.append(f"[<span style='color:red;'>{expected_die}: {c}</span>]")
                        else:
                            details_html.append(f"[<span style='color:green;'>{expected_die}: {c}</span>]")
                        details_raw.append(f"[{expected_die}: {c}]")
                self.drc_results["Symmetry (Unnumbered)"]["fail"].append({
                    "id": f"SymUnnum::{base}",
                    "html": f"Mismatch on '{base}'. " + " ".join(details_html),
                    "raw": f"Mismatch on '{base}'. " + " ".join(details_raw),
                    "cells": cells
                })
            else:
                msg = f"Matched '{base}' ({max_count} pins/die)"
                self.drc_results["Symmetry (Unnumbered)"]["pass"].append({
                    "id": f"SymUnnumPass::{base}", "html": msg, "raw": msg, "cells": cells
                })

        self.render_drc_tree()
        
        info_html = "<h3>DRC Rules Evaluated</h3>"
        info_html += "<ul>"
        info_html += "<li><b>Proximity:</b> No CLK net can touch any VDD net in the 8 adjacent cells.</li>"
        info_html += "<li><b>Symmetry (Numbered):</b> If a net has any _[NS]# suffix ANYWHERE, it expects balls for ALL discovered global numbered dies in the chip layout.</li>"
        info_html += "<li><b>Symmetry (Unnumbered):</b> Fallback. If a net ONLY has _N or _S, it must match exactly between North and South.</li>"
        info_html += "</ul><br>"
        self.drc_info_text.setHtml(info_html)
        
        self.log(f"DRC Scan Complete. {len(failed_prox_nets) + len(self.drc_results['Symmetry (Numbered)']['fail']) + len(self.drc_results['Symmetry (Unnumbered)']['fail'])} total violations found.")

    def render_drc_tree(self):
        # Save expansion state
        expanded_paths = set()
        for i in range(self.drc_tree.topLevelItemCount()):
            root = self.drc_tree.topLevelItem(i)
            category = root.data(0, Qt.ItemDataRole.UserRole + 2)
            if root.isExpanded():
                expanded_paths.add(category)
            for j in range(root.childCount()):
                child = root.child(j)
                item_type = child.data(0, Qt.ItemDataRole.UserRole + 1)
                if child.isExpanded():
                    expanded_paths.add(f"{category}|{item_type}")

        self.drc_tree.clear()
        
        for category, data in self.drc_results.items():
            passes = data.get('pass', [])
            fails = data.get('fail', [])
            
            active_fails = []
            waived_items = []
            for f in fails:
                if f['id'] in self.waived_violations: waived_items.append(f)
                else: active_fails.append(f)
            
            if active_fails:
                root_text = f"<span style='color:red; font-weight:bold;'>{category}</span> (Pass: {len(passes)}, Fail: {len(active_fails)}, Waived: {len(waived_items)})"
            else:
                root_text = f"<span style='font-weight:bold;'>{category}</span> (Pass: {len(passes)}, Fail: {len(active_fails)}, Waived: {len(waived_items)})"
                
            root_node = QTreeWidgetItem(self.drc_tree, [root_text])
            root_node.setData(0, Qt.ItemDataRole.UserRole + 2, category)
            if category in expanded_paths:
                root_node.setExpanded(True)
                
            if active_fails:
                n_fail = QTreeWidgetItem(root_node, [f"Fail ({len(active_fails)})"])
                n_fail.setData(0, Qt.ItemDataRole.UserRole + 1, "fail")
                if f"{category}|fail" in expanded_paths:
                    n_fail.setExpanded(True)
                for f in active_fails:
                    item = QTreeWidgetItem(n_fail, [f['html']])
                    item.setToolTip(0, f"<html>{f['html']}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, f['cells'])
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, "fail")
                    item.setData(0, Qt.ItemDataRole.UserRole + 3, f['id'])
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            if waived_items:
                n_waived = QTreeWidgetItem(root_node, [f"Waived ({len(waived_items)})"])
                n_waived.setData(0, Qt.ItemDataRole.UserRole + 1, "waived") 
                if f"{category}|waived" in expanded_paths:
                    n_waived.setExpanded(True)
                for w in waived_items:
                    item = QTreeWidgetItem(n_waived, [w['html']])
                    item.setToolTip(0, f"<html>{w['html']}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, w['cells'])
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, "waived")
                    item.setData(0, Qt.ItemDataRole.UserRole + 3, w['id'])
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            if passes:
                n_pass = QTreeWidgetItem(root_node, [f"Pass ({len(passes)})"])
                n_pass.setData(0, Qt.ItemDataRole.UserRole + 1, "pass")
                if f"{category}|pass" in expanded_paths:
                    n_pass.setExpanded(True)
                for p in passes:
                    item = QTreeWidgetItem(n_pass, [p['html']])
                    item.setToolTip(0, f"<html>{p['html']}</html>")
                    item.setData(0, Qt.ItemDataRole.UserRole, p['cells'])
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, "pass")

    def auto_color_diff_pairs(self):
        if not self.valid_diff_pairs: return
        
        for i, (base, pairs) in enumerate(self.valid_diff_pairs.items()):
            hue = (i * 0.618033988749895) % 1.0
            rgb = colorsys.hls_to_rgb(hue, 0.7, 0.6)
            hex_color = "#{:02x}{:02x}{:02x}".format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            p_net = pairs.get('P')
            n_net = pairs.get('N')
            if p_net not in self.net_view_state: self.net_view_state[p_net] = {"selected": False}
            if n_net not in self.net_view_state: self.net_view_state[n_net] = {"selected": False}
            
            self.net_view_state[p_net]['color'] = hex_color
            self.net_view_state[n_net]['color'] = hex_color
            
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
                
        self.populate_nets_table()
        self.log(f"Auto-colored {len(self.valid_diff_pairs)} differential pairs.")

    def clear_auto_color_diff_pairs(self):
        if not self.valid_diff_pairs: return
        
        for base, pairs in self.valid_diff_pairs.items():
            p_net = pairs.get('P')
            n_net = pairs.get('N')
            if p_net in self.net_view_state:
                self.net_view_state[p_net]['color'] = self.default_net_colors.get(p_net, DEFAULT_CELL_BG)
            if n_net in self.net_view_state:
                self.net_view_state[n_net]['color'] = self.default_net_colors.get(n_net, DEFAULT_CELL_BG)
                
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
            
        self.populate_nets_table()
        self.log("Cleared differential pair auto-colors.")

    def on_diff_pair_selected(self):
        items = self.diff_pairs_list.selectedItems() if hasattr(self, 'diff_pairs_list') else []
        if not items: return
        base_name = items[0].text().replace(" (_P / _N)", "")
        pairs = self.valid_diff_pairs.get(base_name)
        if not pairs: return
        
        target_nets = [pairs.get('P'), pairs.get('N')]
        self.scene.clearSelection()
        
        cells_to_focus = []
        for item in self.ball_items.values():
            if item.net in target_nets:
                item.setSelected(True)
                cells_to_focus.append(item)
                
        # Smart Pan: Only center if the item is not fully visible
        if cells_to_focus:
            visible_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
            if not visible_rect.contains(cells_to_focus[0].sceneBoundingRect()):
                self.view.centerOn(cells_to_focus[0])

    def reset_default_colors(self):
        for net_name in self.net_view_state.keys():
            self.net_view_state[net_name]["color"] = self.default_net_colors.get(net_name, DEFAULT_CELL_BG)
        
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
                
        for i in range(self.nets_table.rowCount()):
            net_name = self.nets_table.item(i, 1).text()
            c_btn = self.nets_table.cellWidget(i, 3)
            c_btn.setStyleSheet(f"background-color: {self.net_view_state[net_name]['color']}; border: 1px solid darkgray;")
        self.log("Colors reset to default VDD/VSS palettes.")

    def load_excel(self, force_path=None):
        if force_path:
            file_path = force_path
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "Open Excel", "", "Excel Files (*.xlsx *.xls)")
            if not file_path: return
            
        try:
            filename = os.path.basename(file_path)
            self.base_device, self.base_version = self.extract_metadata(filename)
            self.setWindowTitle(f"Ball Map Viewer v{__version__}  |  {self.base_device} (Rev {self.base_version})")
            
            self.add_recent_file(file_path)
            
            self.view_counter = 1
            self.input_view_name.setText(f"{self.base_device}_v{self.base_version}_View_{self.view_counter}")

            self.current_records, self.current_pin_map = self.parse_excel_to_dict(file_path)
            
            if self.debug_mode:
                print(f"[DEBUG] Loaded Excel. Records: {len(self.current_records)}, Pin Map Keys: {len(self.current_pin_map)}")
            
            self.full_pin_data = {}
            for r_data in self.current_records:
                pin = str(r_data.get('Pin Number', '')).strip()
                if pin and pin != 'nan': self.full_pin_data[pin] = r_data

            y_vals = [r['Y Coord'] for r in self.current_records if r.get('Y Coord') != ""]
            x_vals = [r['X Coord'] for r in self.current_records if r.get('X Coord') != ""]
            
            unique_y = sorted(list(set(y_vals)), reverse=True)
            unique_x = sorted(list(set(x_vals)))
            
            y_to_row = {y: i for i, y in enumerate(unique_y)}
            x_to_col = {x: i for i, x in enumerate(unique_x)}
            rows, cols = len(unique_y), len(unique_x)
            
            if self.debug_mode:
                print(f"[DEBUG] Grid Bounds: {rows} Rows x {cols} Cols")

            self.grid_data = [["" for _ in range(cols)] for _ in range(rows)]
            self.row_headers, self.col_headers = [""] * rows, [""] * cols
            self.pin_to_cell, self.net_frequences, self.net_view_state = {}, {}, {}
            self.manual_colors = {}
            self.default_net_colors = {}
            self.active_violation_cells.clear()
            self.active_passing_cells.clear()
            self.active_waived_cells.clear()

            for r_data in self.current_records:
                x, y = r_data.get('X Coord'), r_data.get('Y Coord')
                if x == "" or y == "": continue
                r, c = y_to_row[y], x_to_col[x]
                net = str(r_data.get('L2 Net Name', '')).strip()
                pin = str(r_data.get('Pin Number', '')).strip()
                
                if net and net != 'nan':
                    self.grid_data[r][c] = net
                    self.net_frequences[net] = self.net_frequences.get(net, 0) + 1

                if pin and pin != 'nan':
                    self.pin_to_cell[pin] = (r, c)
                    match = re.match(r"([A-Za-z]+)(\d+)", pin)
                    if match: self.row_headers[r], self.col_headers[c] = match.groups()

            sorted_unique_nets = sorted(self.net_frequences.keys())
            vdd_idx, vss_idx = 0, 0
            for net in sorted_unique_nets:
                color = DEFAULT_CELL_BG
                if "VDD" in net.upper():
                    color = VDD_PALETTE[vdd_idx % len(VDD_PALETTE)]
                    vdd_idx += 1
                elif "VSS" in net.upper():
                    color = VSS_PALETTE[vss_idx % len(VSS_PALETTE)]
                    vss_idx += 1
                self.net_view_state[net] = {"selected": False, "color": color}
                self.default_net_colors[net] = color

            self.render_grid()
            self.populate_nets_table()
            self.combo_views.clear()
            self.run_drc()
            
            def delayed_fit():
                QApplication.processEvents()
                self.fit_to_screen()
            QTimer.singleShot(300, delayed_fit)
            
            self.log(f"Successfully loaded '{filename}'. Discovered {len(sorted_unique_nets)} distinct nets.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load map:\n{str(e)}")

    def render_grid(self):
        self.scene.clear()
        self.ball_items.clear()
        if not self.grid_data: return
        rows, cols = len(self.grid_data), len(self.grid_data[0])

        for c in range(cols):
            self.scene.addItem(HeaderItem((c+1)*CELL_SIZE, 0, CELL_SIZE, CELL_SIZE, self.col_headers[c], self))
            self.scene.addItem(HeaderItem((c+1)*CELL_SIZE, (rows+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.col_headers[c], self))
        for r in range(rows):
            self.scene.addItem(HeaderItem(0, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.row_headers[r], self))
            self.scene.addItem(HeaderItem((cols+1)*CELL_SIZE, (r+1)*CELL_SIZE, CELL_SIZE, CELL_SIZE, self.row_headers[r], self))

        for r in range(rows):
            for c in range(cols):
                val = self.grid_data[r][c]
                if val:
                    pin_name = f"{self.row_headers[r]}{self.col_headers[c]}"
                    item = BallItem(r, c, val, pin_name, self)
                    self.scene.addItem(item)
                    self.ball_items[(r, c)] = item
                    self.update_cell_color(r, c)

    def update_cell_color(self, r, c):
        item = self.ball_items.get((r, c))
        if not item: return
        
        bg_col = DEFAULT_CELL_BG
        val = self.grid_data[r][c]
        
        if (r, c) in self.manual_colors:
            bg_col = self.manual_colors[(r, c)]
        elif val and val in self.net_view_state and self.net_view_state[val]["color"] != DEFAULT_CELL_BG:
            bg_col = self.net_view_state[val]["color"]
            
        is_chk = val and val in self.net_view_state and self.net_view_state[val]["selected"]
        
        hl_col = None
        if (r, c) in self.active_violation_cells: hl_col = "red"
        elif (r, c) in self.active_waived_cells: hl_col = "yellow"
        elif (r, c) in self.active_passing_cells: hl_col = "#00FF00"
        
        item.update_visuals(bg_col, is_chk, hl_col)

    def populate_nets_table(self):
        self._updating_checks = True
        self.nets_table.setSortingEnabled(False)
        self.nets_table.setRowCount(0)
        if not self.net_view_state: 
            self._updating_checks = False
            return
            
        sorted_nets = sorted(self.net_frequences.keys())
        self.nets_table.setRowCount(len(sorted_nets))

        for idx, net_name in enumerate(sorted_nets):
            state = self.net_view_state[net_name]
            
            chk_item = QTableWidgetItem("")
            chk_item.setData(Qt.ItemDataRole.UserRole, state["selected"])
            self.nets_table.setItem(idx, 0, chk_item)

            name_item = QTableWidgetItem(net_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(net_name)
            self.nets_table.setItem(idx, 1, name_item)

            count_item = NumericItem(str(self.net_frequences.get(net_name, 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setToolTip(str(self.net_frequences.get(net_name, 0)))
            self.nets_table.setItem(idx, 2, count_item)

            color_btn = QPushButton()
            color_btn.setStyleSheet(f"background-color: {state['color']}; border: 1px solid darkgray;")
            color_btn.setMinimumWidth(30)
            color_btn.clicked.connect(lambda checked, net=net_name, btn=color_btn: self.pick_net_color(net, btn))
            
            self.nets_table.setItem(idx, 3, QTableWidgetItem(""))
            self.nets_table.setCellWidget(idx, 3, color_btn)
            
        self.nets_table.setSortingEnabled(True)
        self._updating_checks = False

    def filter_nets_table(self):
        pattern = self.input_regex.text().strip()
        use_regex = self.cb_use_regex.isChecked()
        try:
            if use_regex: regex = re.compile(pattern, re.IGNORECASE)
        except re.error: return 

        for idx in range(self.nets_table.rowCount()):
            net_name_item = self.nets_table.item(idx, 1)
            if net_name_item:
                net_text = net_name_item.text()
                if use_regex: is_visible = bool(regex.fullmatch(net_text)) if pattern else True
                else: is_visible = pattern.upper() in net_text.upper() 
                self.nets_table.setRowHidden(idx, not is_visible)

    def on_net_checkbox_clicked(self, row, col):
        if getattr(self, '_updating_checks', False): return
        if col == 0:
            item = self.nets_table.item(row, 0)
            net_name = self.nets_table.item(row, 1).text()
            current_state = item.data(Qt.ItemDataRole.UserRole)
            new_state = not current_state
            item.setData(Qt.ItemDataRole.UserRole, new_state)
            
            self.net_view_state[net_name]["selected"] = new_state
            self.on_selection_changed()
            for b_item in self.ball_items.values():
                if b_item.net == net_name:
                    self.update_cell_color(b_item.r, b_item.c)

    def pick_net_color(self, net_name, color_btn):
        color = QColorDialog.getColor(QColor(self.net_view_state[net_name]["color"]))
        if color.isValid():
            self.save_state()
            hex_color = color.name()
            self.net_view_state[net_name]["color"] = hex_color
            color_btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
            
            for item in self.ball_items.values():
                if item.net == net_name:
                    self.update_cell_color(item.r, item.c)

    def nets_select_all_visible(self):
        self._updating_checks = True
        self.nets_table.setUpdatesEnabled(False)
        for i in range(self.nets_table.rowCount()):
            if not self.nets_table.isRowHidden(i):
                self.nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, True)
                net_name = self.nets_table.item(i, 1).text()
                self.net_view_state[net_name]["selected"] = True
                
        self.nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.on_selection_changed()
        for item in self.ball_items.values():
            if item.net in self.net_view_state and self.net_view_state[item.net]["selected"]: 
                self.update_cell_color(item.r, item.c)

    def nets_deselect_all(self):
        self._updating_checks = True
        self.nets_table.setUpdatesEnabled(False)
        for i in range(self.nets_table.rowCount()):
            self.nets_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, False)
            net_name = self.nets_table.item(i, 1).text()
            self.net_view_state[net_name]["selected"] = False
            
        self.nets_table.setUpdatesEnabled(True)
        self._updating_checks = False
        self.scene.clearSelection()
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)

    def clear_all_selections(self):
        self.save_state()
        self.nets_deselect_all()
        self.manual_colors.clear()
        
        for net_name in self.net_view_state.keys():
            self.net_view_state[net_name]["color"] = DEFAULT_CELL_BG
            for i in range(self.nets_table.rowCount()):
                if self.nets_table.item(i, 1).text() == net_name:
                    color_btn = self.nets_table.cellWidget(i, 3)
                    color_btn.setStyleSheet(f"background-color: {DEFAULT_CELL_BG}; border: 1px solid darkgray;")
                    
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
        self.log("Cleared all selections and wiped assigned colors.")

    def color_checked_nets(self):
        checked_nets = []
        for i in range(self.nets_table.rowCount()):
            if not self.nets_table.isRowHidden(i):
                if self.nets_table.item(i, 0).data(Qt.ItemDataRole.UserRole):
                    checked_nets.append(self.nets_table.item(i, 1).text())
                    
        valid_items = [i for i in self.scene.selectedItems() if isinstance(i, BallItem)]
                
        if not checked_nets and not valid_items: return
        
        color = QColorDialog.getColor()
        if color.isValid():
            self.save_state()
            hex_color = color.name()
            
            for net_name in checked_nets:
                self.net_view_state[net_name]["color"] = hex_color
                for i in range(self.nets_table.rowCount()):
                    if self.nets_table.item(i, 1).text() == net_name:
                        self.nets_table.cellWidget(i, 3).setStyleSheet(f"background-color: {hex_color}; border: 1px solid darkgray;")
                        break
                        
            for item in self.ball_items.values():
                if item.net in checked_nets:
                    self.update_cell_color(item.r, item.c)
                    
            for item in valid_items:
                self.manual_colors[(item.r, item.c)] = hex_color
                self.update_cell_color(item.r, item.c)

    def reset_default_colors(self):
        self.save_state()
        for net_name in self.net_view_state.keys():
            self.net_view_state[net_name]["color"] = self.default_net_colors.get(net_name, DEFAULT_CELL_BG)
        
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
                
        for i in range(self.nets_table.rowCount()):
            net_name = self.nets_table.item(i, 1).text()
            c_btn = self.nets_table.cellWidget(i, 3)
            c_btn.setStyleSheet(f"background-color: {self.net_view_state[net_name]['color']}; border: 1px solid darkgray;")
        self.log("Colors reset to default VDD/VSS palettes.")

    def on_selection_changed(self):
        native_sel = sum(1 for i in self.scene.selectedItems() if isinstance(i, BallItem))
        net_sel_count = 0
        
        checked_nets = {net for net, state in self.net_view_state.items() if state.get("selected")}
        if checked_nets and self.grid_data:
            for (r, c), item in self.ball_items.items():
                if item.net in checked_nets and not item.isSelected():
                    net_sel_count += 1
                            
        total = native_sel + net_sel_count
        self.lbl_selection.setText(f"<b>Selected Cells:</b> {total}")
    def save_view(self):
        view_name = self.input_view_name.text()
        if not view_name:
            QMessageBox.warning(self, "Warning", "Please enter a View Name.")
            return
        self.saved_views[view_name] = {k: v.copy() for k, v in self.net_view_state.items()}
        if self.combo_views.findText(view_name) == -1: self.combo_views.addItem(view_name)
        self.log(f"Saved custom view '{view_name}'.")
        self.view_counter += 1
        self.input_view_name.setText(f"{self.base_device}_v{self.base_version}_View_{self.view_counter}")

    def load_view(self):
        view_name = self.combo_views.currentText()
        if not view_name or view_name not in self.saved_views: return
        self.clear_all_selections()
        view_data = self.saved_views[view_name]
        for net_name, data in view_data.items():
            if net_name in self.net_view_state: self.net_view_state[net_name] = data.copy()
        
        self.populate_nets_table() 
        for item in self.ball_items.values():
            self.update_cell_color(item.r, item.c)
        self.log(f"Loaded view '{view_name}'.")

    def save_db(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Database", "", "JSON Files (*.json)")
        if not file_path: return
        
        mc_list = [{"r": r, "c": c, "color": color} for (r, c), color in self.manual_colors.items()]
        dc_list = [{"net": k, "color": v} for k, v in getattr(self, 'default_net_colors', {}).items()]
        
        db_data = {
            "current_records": getattr(self, 'current_records', []),
            "current_pin_map": getattr(self, 'current_pin_map', {}),
            "grid_data": self.grid_data, "row_headers": self.row_headers, "col_headers": self.col_headers,
            "pin_to_cell": self.pin_to_cell, "net_view_state": self.net_view_state, "saved_views": self.saved_views,
            "full_pin_data": self.full_pin_data,
            "manual_colors": mc_list,
            "default_colors": dc_list,
            "waived_violations": list(self.waived_violations)
        }
        with open(file_path, 'w') as f: json.dump(db_data, f)
        self.log("Session database saved successfully.")

    def load_db(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Database", "", "JSON Files (*.json)")
        if not file_path: return
        try:
            with open(file_path, 'r') as f: db_data = json.load(f)
            self.current_records = db_data.get("current_records", [])
            self.current_pin_map = db_data.get("current_pin_map", {})
            self.grid_data = db_data.get("grid_data", [])
            self.row_headers = db_data.get("row_headers", [])
            self.col_headers = db_data.get("col_headers", [])
            self.pin_to_cell = db_data.get("pin_to_cell", {})
            self.net_view_state = db_data.get("net_view_state", {})
            self.saved_views = db_data.get("saved_views", {})
            self.full_pin_data = db_data.get("full_pin_data", {})
            self.waived_violations = set(db_data.get("waived_violations", []))
            
            mc_list = db_data.get("manual_colors", [])
            self.manual_colors = {(item["r"], item["c"]): item["color"] for item in mc_list}
            
            dc_list = db_data.get("default_colors", [])
            self.default_net_colors = {item["net"]: item["color"] for item in dc_list}
            
            self.render_grid()
            self.populate_nets_table()
            self.combo_views.clear()
            self.combo_views.addItems(list(self.saved_views.keys()))
            self.run_drc()
            
            def delayed_fit():
                QApplication.processEvents()
                self.fit_to_screen()
            QTimer.singleShot(300, delayed_fit)
            
            self.log("Database session loaded seamlessly.")
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")
    def launch_editor_gui(self):
        if not self.grid_data:
            QMessageBox.warning(self, "Warning", "Please load a map first before launching the Editor.")
            return
        try:
            try:
                is_vis = self.active_editor_dialog.isVisible()
            except RuntimeError:
                is_vis = False
            except AttributeError:
                is_vis = False
                
            if not is_vis:
                self.active_editor_dialog = BallMapEditor(self)
                self.active_editor_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                self.active_editor_dialog.show()
            self.active_editor_dialog.activateWindow()
            self.log("Launched Ball Map Editor.")
        except Exception as e: 
            QMessageBox.critical(self, "Editor Error", f"Failed to launch Editor:\n{str(e)}")

    def launch_diff_gui(self):
        try:
            try:
                is_vis = self.active_diff_dialog.isVisible()
            except RuntimeError:
                is_vis = False
            except AttributeError:
                is_vis = False
                
            if not is_vis:
                self.active_diff_dialog = ComparisonDialog(self, self.debug_mode)
                self.active_diff_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                self.active_diff_dialog.show()
            self.active_diff_dialog.activateWindow()
            self.log("Launched Standalone Diff Interface.")
        except Exception as e: 
            QMessageBox.critical(self, "Comparison Error", f"Failed to launch Diff interface:\n{str(e)}")

if __name__ == '__main__':
    # ONLY apply the AppID trick if running as a raw .py script
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        try:
            myappid = f'eda.ballmapviewer.{__version__}.release_1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    icon_path = os.path.join(base_dir, "BallMapViewer.ico") 
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    # ------------------------------

    parser = argparse.ArgumentParser(description="Ball Map Viewer")
    parser.add_argument("--debug", action="store_true", help="Enable debug telemetry output in the terminal")
    args = parser.parse_args()

    print(f"=======================================")
    print(f"  Initializing Ball Map Viewer v{__version__}  ")
    if args.debug:
        print(f"  [DEBUG MODE ENABLED]  ")
    print(f"=======================================")
    
    viewer = BallMapViewer(debug_mode=args.debug)
    viewer.showMaximized()
    exit_code = app.exec()
    
    print(f"=======================================")
    print(f"  Ball Map Viewer closed successfully. ")
    print(f"=======================================")
    sys.exit(exit_code)

# --- End of Script (Version 2.21.0) ---