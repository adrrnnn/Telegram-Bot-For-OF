"""Verification waiting screen for PyQt5 GUI."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal, QObject


class VerificationScreenSignals(QObject):
    """Signals for verification screen."""
    verification_complete = pyqtSignal()
    verification_failed = pyqtSignal(str)


def create_verification_screen() -> QWidget:
    """Create waiting for verification screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(20)
    layout.setContentsMargins(40, 40, 40, 40)
    
    # Add stretch at top
    layout.addStretch()
    
    # Title
    title = QLabel("Verification Required")
    title_font = QFont()
    title_font.setPointSize(18)
    title_font.setBold(True)
    title.setFont(title_font)
    title.setAlignment(Qt.AlignCenter)
    layout.addWidget(title)
    
    # Instructions
    instructions = QLabel(
        "A verification code has been sent to your Telegram app.\n\n"
        "Please check your Telegram messages and enter the code\n"
        "when prompted.\n\n"
        "Waiting for verification..."
    )
    instructions_font = QFont()
    instructions_font.setPointSize(11)
    instructions.setFont(instructions_font)
    instructions.setAlignment(Qt.AlignCenter)
    instructions.setStyleSheet("color: #666; line-height: 1.6;")
    layout.addWidget(instructions)
    
    # Progress bar
    progress = QProgressBar()
    progress.setMaximum(0)  # Indeterminate progress
    progress.setStyleSheet("""
        QProgressBar {
            border: 1px solid #ccc;
            border-radius: 4px;
            background-color: #f5f5f5;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #007AFF;
        }
    """)
    layout.addWidget(progress)
    
    # Add stretch at bottom
    layout.addStretch()
    
    return widget
