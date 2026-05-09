"""Simple Telegram phone number setup dialog for PyQt5 GUI."""

import webbrowser
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QMessageBox, QScrollArea
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


class TelegramSetupDialog(QDialog):
    """Modal dialog for Telegram API credentials and phone setup - Pyrogram authentication."""
    
    def __init__(self, parent=None, db=None, config=None):
        super().__init__(parent)
        self.db = db
        self.config = config
        self.setWindowTitle("Telegram Bot Setup")
        self.setGeometry(200, 100, 550, 650)
        self.setModal(True)
        
        self._setup_ui()
        self._apply_styling()
    
    def _setup_ui(self):
        """Build the dialog UI layout."""
        main_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Welcome! Let's set up your Telegram Bot")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Enter your Telegram API credentials and phone number")
        subtitle.setStyleSheet("color: #666; margin-bottom: 15px;")
        main_layout.addWidget(subtitle)
        
        # === API CREDENTIALS SECTION ===
        api_group = QGroupBox("Telegram API Credentials")
        api_layout = QVBoxLayout()
        
        # Legal warning
        warning_text = QLabel(
            "⚠️ WARNING: Users will NOT know this is automated.\n"
            "Keep these credentials secure!"
        )
        warning_text.setStyleSheet("color: #d32f2f; font-weight: bold; margin-bottom: 10px;")
        warning_text.setWordWrap(True)
        api_layout.addWidget(warning_text)
        
        # Get Credentials Button
        get_creds_btn = QPushButton("📱 Get Credentials from Telegram")
        get_creds_btn.clicked.connect(self._open_telegram_credentials)
        get_creds_btn.setStyleSheet("""
            QPushButton {
                padding: 12px;
                background-color: #0088cc;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            QPushButton:hover {
                background-color: #0077b3;
            }
        """)
        api_layout.addWidget(get_creds_btn)
        
        # API ID
        api_id_label = QLabel("API ID *")
        self.api_id_input = QLineEdit()
        self.api_id_input.setPlaceholderText("e.g., 37161634")
        api_layout.addWidget(api_id_label)
        api_layout.addWidget(self.api_id_input)
        
        # API Hash
        api_hash_label = QLabel("API Hash *")
        self.api_hash_input = QLineEdit()
        self.api_hash_input.setPlaceholderText("e.g., dd43e88e5fe584c2b86ec3c54ed22265")
        api_layout.addWidget(api_hash_label)
        api_layout.addWidget(self.api_hash_input)
        
        api_group.setLayout(api_layout)
        main_layout.addWidget(api_group)
        
        # === ACCOUNT DETAILS SECTION ===
        account_group = QGroupBox("Account Details")
        account_layout = QVBoxLayout()
        
        # Account Name
        name_label = QLabel("Account Name *")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Personal, Work, Bot Testing")
        account_layout.addWidget(name_label)
        account_layout.addWidget(self.name_input)
        
        # Phone
        phone_label = QLabel("Phone Number *")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+1 234 567 8900")
        account_layout.addWidget(phone_label)
        account_layout.addWidget(self.phone_input)
        
        account_group.setLayout(account_layout)
        main_layout.addWidget(account_group)
        
        # Info text
        info_text = QLabel(
            "You'll receive a verification code via Telegram after clicking Next.\n"
            "This is the same phone number you use to log into Telegram."
        )
        info_text.setStyleSheet("color: #555; margin: 10px 0;")
        info_text.setWordWrap(True)
        main_layout.addWidget(info_text)
        
        main_layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self._save)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(next_btn)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def _open_telegram_credentials(self):
        """Open Telegram credentials page in browser."""
        webbrowser.open("https://my.telegram.org/apps")
        QMessageBox.information(
            self,
            "Getting Credentials",
            "A browser window has opened to my.telegram.org/apps\n\n"
            "1. Log in with your Telegram account\n"
            "2. Click 'Create New Application'\n"
            "3. Fill in the details\n"
            "4. Copy the API ID and API Hash\n"
            "5. Paste them into the fields above"
        )
    
    def _apply_styling(self):
        """Apply modern PyQt5 styling."""
        stylesheet = """
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLineEdit {
                padding: 10px;
                border: 1px solid #ccc;
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
    
    def _validate_inputs(self) -> bool:
        """Validate all required inputs."""
        # Check account name
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Account name is required")
            return False
        
        # Check API ID
        api_id_text = self.api_id_input.text().strip()
        if not api_id_text:
            QMessageBox.warning(self, "Validation Error", "API ID is required")
            return False
        
        try:
            int(api_id_text)
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "API ID must be a number")
            return False
        
        # Check API Hash
        if not self.api_hash_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "API Hash is required")
            return False
        
        if len(self.api_hash_input.text().strip()) != 32:
            QMessageBox.warning(
                self, 
                "Validation Error", 
                "API Hash must be exactly 32 characters"
            )
            return False
        
        # Validate phone
        return self._validate_phone(self.phone_input.text().strip())
    
    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            QMessageBox.warning(self, "Validation Error", "Phone number is required")
            return False
        
        # Extract digits only
        phone_digits = ''.join(c for c in phone if c.isdigit())
        
        # Check length (typically 10-15 digits)
        if len(phone_digits) < 10 or len(phone_digits) > 15:
            QMessageBox.warning(self, "Validation Error", 
                              "Phone number must have 10-15 digits\n\n"
                              "Examples:\n"
                              "  +1 234 567 8900\n"
                              "  +44 20 7946 0958")
            return False
        
        return True
    
    def _save(self):
        """Save all credentials (API ID, API Hash, phone, account name) to config."""
        if not self._validate_inputs():
            return
        
        name = self.name_input.text().strip()
        api_id_text = self.api_id_input.text().strip()
        api_hash_text = self.api_hash_input.text().strip()
        phone = self.phone_input.text().strip()
        
        try:
            # Clean phone number
            phone_digits = ''.join(c for c in phone if c.isdigit())
            phone = '+' + phone_digits

            # Save to database first so duplicate checks run before touching config
            if self.db:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()

                        # Check for duplicate phone
                        cursor.execute("SELECT id FROM accounts WHERE phone = ?", (phone,))
                        if cursor.fetchone():
                            QMessageBox.warning(self, "Account Exists",
                                              "This phone number is already registered")
                            return

                        # Check for duplicate name
                        cursor.execute("SELECT id FROM accounts WHERE name = ?", (name,))
                        if cursor.fetchone():
                            QMessageBox.warning(self, "Name Exists",
                                              "An account with this name already exists")
                            return

                        # Deactivate any existing active account before marking this one active
                        cursor.execute(
                            "UPDATE accounts SET is_active = 0 WHERE account_type = 'telegram'"
                        )

                        # Insert new account
                        cursor.execute(
                            """INSERT INTO accounts
                               (account_type, name, phone, api_id, api_hash, is_active, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                            ('telegram', name, phone, api_id_text, api_hash_text, 1)
                        )
                except Exception as db_error:
                    QMessageBox.critical(self, "Error", f"Failed to save account: {db_error}")
                    return

            # Config saved only after DB succeeds
            if self.config:
                from src.config import TelegramConfig
                self.config.telegram = TelegramConfig(
                    api_id=int(api_id_text),
                    api_hash=api_hash_text,
                    phone_number=phone
                )
                self.config.save_config()
            
            QMessageBox.information(self, "Great!", 
                                  f"Account '{name}' ({phone}) configured successfully!\n\n"
                                  "The bot will now initialize and request verification.")
            self.accept()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save credentials: {e}")
