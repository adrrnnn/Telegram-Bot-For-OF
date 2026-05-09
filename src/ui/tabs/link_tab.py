"""
Change OF Link Tab
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QGroupBox, QFormLayout, QMessageBox
from src.database import DatabaseManager
from src.config import ConfigManager


class ChangeOFLinkTab(QWidget):
    """Tab for changing OnlyFans link"""
    
    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self._setup_ui()
        self.load_link()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        
        group = QGroupBox("UPDATE ONLYFANS LINK")
        form_layout = QFormLayout()
        
        # Current link
        self.current_label = QLabel("No link set")
        form_layout.addRow("Current Link:", self.current_label)
        
        # New link input
        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("https://onlyfans.com/username")
        form_layout.addRow("New Link:", self.link_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        reset_btn = QPushButton("Reset")
        clear_btn = QPushButton("Clear")
        
        save_btn.clicked.connect(self.save_link)
        reset_btn.clicked.connect(self.load_link)
        clear_btn.clicked.connect(lambda: self.link_input.clear())
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(clear_btn)
        form_layout.addRow("", button_layout)
        
        group.setLayout(form_layout)
        layout.addWidget(group)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def load_link(self):
        """Load current OF link from configuration"""
        try:
            if self.config.bot.of_link:
                self.current_label.setText(self.config.bot.of_link)
                self.link_input.clear()
            else:
                self.current_label.setText("No link set")
        except Exception as e:
            self.current_label.setText("Error loading link")
    
    def save_link(self):
        """Save new OF link to configuration"""
        try:
            new_link = self.link_input.text().strip()
            if new_link:
                # Save to config
                self.config.bot.of_link = new_link
                self.config.save_config()
                
                # Update display
                self.link_input.clear()
                self.current_label.setText(new_link)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save link: {e}")
