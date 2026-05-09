"""Telegram verification code dialog for PyQt5 GUI."""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


class VerificationCodeDialog(QDialog):
    """Dialog for entering Telegram verification code."""

    def __init__(self, parent=None, telegram_prompt_excerpt: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Telegram Verification")
        self.setGeometry(300, 300, 400, 200)
        self.setModal(True)
        self.code = None

        self._setup_ui(telegram_prompt_excerpt)
        self._apply_styling()

    def _setup_ui(self, telegram_prompt_excerpt: str = ""):
        """Build the dialog UI layout."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Verification Code Required")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Instructions
        if telegram_prompt_excerpt.strip():
            body = (
                f"Telegram:\n{telegram_prompt_excerpt.strip()}\n\n"
                "Enter the numeric code from your Telegram app:"
            )
        else:
            body = (
                "A verification code has been sent to your Telegram app.\n"
                "Enter the code below (usually 5 digits):"
            )
        instructions = QLabel(body)
        instructions.setStyleSheet("color: #666; margin: 10px 0;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Code input
        code_label = QLabel("Verification Code *")
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g., 12345")
        self.code_input.setMaxLength(8)
        self.code_input.setAlignment(Qt.AlignCenter)
        code_font = QFont()
        code_font.setPointSize(16)
        code_font.setBold(True)
        self.code_input.setFont(code_font)
        self.code_input.setStyleSheet("""
            QLineEdit {
                padding: 15px;
                font-size: 24px;
                letter-spacing: 5px;
            }
        """)
        
        layout.addWidget(code_label)
        layout.addWidget(self.code_input)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        verify_btn = QPushButton("Verify")
        verify_btn.clicked.connect(self._verify_code)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(verify_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Focus code input on show
        self.code_input.setFocus()
    
    def _apply_styling(self):
        """Apply modern PyQt5 styling."""
        stylesheet = """
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
            QLineEdit {
                padding: 10px;
                border: 2px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
                background-color: #f0f8ff;
            }
            QPushButton {
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """
        self.setStyleSheet(stylesheet)
    
    def _verify_code(self):
        """Verify and save the code."""
        code = self.code_input.text().strip()

        if not code or not code.isdigit() or not (5 <= len(code) <= 8):
            self.code_input.setFocus()
            return

        self.code = code
        self.accept()
    
    def get_code(self) -> str:
        """Get the entered verification code."""
        return self.code


class TwoFactorDialog(QDialog):
    """Dialog for entering a Telegram 2FA / cloud password."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Two-Step Verification")
        self.setGeometry(300, 300, 400, 200)
        self.setModal(True)
        self.password = None
        self._setup_ui()
        self._apply_styling()

    def _setup_ui(self):
        layout = QVBoxLayout()

        title = QLabel("Two-Step Verification (2FA)")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        instructions = QLabel(
            "Your Telegram account has two-step verification enabled.\n"
            "Enter your cloud password to continue:"
        )
        instructions.setStyleSheet("color: #666; margin: 10px 0;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Cloud password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._submit)
        layout.addWidget(self.password_input)

        layout.addStretch()

        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self._submit)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(submit_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.password_input.setFocus()

    def _apply_styling(self):
        self.setStyleSheet("""
            QDialog { background-color: #f5f5f5; }
            QLabel { color: #333; }
            QLineEdit {
                padding: 10px;
                border: 2px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QLineEdit:focus { border: 2px solid #2196F3; background-color: #f0f8ff; }
            QPushButton {
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:pressed { background-color: #1565C0; }
        """)

    def _submit(self):
        pw = self.password_input.text().strip()
        if not pw:
            self.password_input.setFocus()
            return
        self.password = pw
        self.accept()

    def get_password(self) -> str:
        return self.password
