# -*- coding: utf-8 -*-
"""صفحه نمودارهای تعاملی."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QLabel, QScrollArea,
                               QVBoxLayout, QWidget)

from ..charts import build_all


class _ChartCard(QFrame):
    def __init__(self, title: str, chart: QWidget):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 10)
        lay.setSpacing(8)
        h = QLabel(title)
        h.setObjectName("h3")
        lay.addWidget(h)
        chart.setLayoutDirection(Qt.LeftToRight)
        lay.addWidget(chart)


class ChartsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll)

        self.content = QWidget()
        self.scroll.setWidget(self.content)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self._placeholder()

    def _placeholder(self):
        w = QLabel("پس از تکمیل تحلیل، نمودارها اینجا نمایش داده می‌شوند.")
        w.setObjectName("faint")
        w.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(w, 0, 0, 1, 2)

    def set_results(self, r):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = build_all(r)
        for i, (title, widget) in enumerate(items):
            self.grid.addWidget(_ChartCard(title, widget), i // 2, i % 2)
        self.grid.setRowStretch(self.grid.rowCount(), 1)
