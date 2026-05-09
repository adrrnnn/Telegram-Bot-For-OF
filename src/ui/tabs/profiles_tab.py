"""
Model Profiles Tab - Manage bot personality profiles
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QDialog, QLineEdit, QCheckBox, QFormLayout,
    QMessageBox, QAbstractItemView, QSpinBox, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from src.database import DatabaseManager
from src.config import ConfigManager


class ProfileFormDialog(QDialog):
    """Dialog for adding/editing model profiles"""
    
    def __init__(self, parent=None, db=None, profile_data=None):
        super().__init__(parent)
        self.db = db
        self.profile_data = profile_data
        self.is_edit = profile_data is not None
        
        self.setWindowTitle("Edit Profile" if self.is_edit else "Add New Profile")
        self.setModal(True)
        self.setGeometry(200, 200, 600, 500)
        
        self._setup_ui()
        
        if self.is_edit:
            self._load_profile_data()
    
    def _setup_ui(self):
        layout = QFormLayout()
        
        # Profile Name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Jess, Maya...")
        layout.addRow("Profile Name *", self.name_input)
        
        # Age
        self.age_input = QSpinBox()
        self.age_input.setRange(1, 120)
        layout.addRow("Age *", self.age_input)
        
        # Location
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g., USA, UK, etc.")
        layout.addRow("Location *", self.location_input)
        
        # Ethnicity
        self.ethnicity_input = QLineEdit()
        self.ethnicity_input.setPlaceholderText("e.g., Asian, European, etc.")
        layout.addRow("Ethnicity *", self.ethnicity_input)
        
        # System Prompt
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setPlaceholderText("Custom system instructions for this profile...")
        self.system_prompt_input.setMinimumHeight(100)
        layout.addRow("Custom System Prompt (Optional)", self.system_prompt_input)
        
        # Notes
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Additional notes about this profile...")
        self.notes_input.setMinimumHeight(80)
        layout.addRow("Notes (Optional)", self.notes_input)
        
        # Set as current (only for view)
        if not self.is_edit:
            self.current_checkbox = QCheckBox("Set as current profile")
            self.current_checkbox.setChecked(True)
            layout.addRow("", self.current_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        clear_btn = QPushButton("Clear")
        
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        clear_btn.clicked.connect(self._clear_fields)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(clear_btn)
        layout.addRow("", button_layout)
        
        self.setLayout(layout)
    
    def _load_profile_data(self):
        if self.profile_data:
            self.name_input.setText(self.profile_data.get('name', ''))
            self.age_input.setValue(self.profile_data.get('age', 18))
            self.location_input.setText(self.profile_data.get('location', ''))
            self.ethnicity_input.setText(self.profile_data.get('ethnicity', ''))
            self.system_prompt_input.setText(self.profile_data.get('system_prompt_custom', ''))
            self.notes_input.setText(self.profile_data.get('notes', ''))
    
    def _clear_fields(self):
        self.name_input.clear()
        self.age_input.setValue(18)
        self.location_input.clear()
        self.ethnicity_input.clear()
        self.system_prompt_input.clear()
        self.notes_input.clear()
    
    def _validate_inputs(self) -> bool:
        name = self.name_input.text().strip()
        age = self.age_input.value()
        location = self.location_input.text().strip()
        ethnicity = self.ethnicity_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Validation Error", "Profile name is required")
            return False
        
        if len(name) < 2 or len(name) > 100:
            QMessageBox.warning(self, "Validation Error", "Profile name must be 2-100 characters")
            return False
        
        if age < 1:
            QMessageBox.warning(self, "Validation Error", "Age is required (must be 1 or higher)")
            return False
        
        if not location:
            QMessageBox.warning(self, "Validation Error", "Location is required")
            return False
        
        if not ethnicity:
            QMessageBox.warning(self, "Validation Error", "Ethnicity is required")
            return False
        
        return True
    
    def _save(self):
        if not self._validate_inputs():
            return
        
        try:
            name = self.name_input.text().strip()
            age = self.age_input.value()
            location = self.location_input.text().strip()
            ethnicity = self.ethnicity_input.text().strip()
            system_prompt = self.system_prompt_input.toPlainText().strip()
            notes = self.notes_input.toPlainText().strip()
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_edit and self.profile_data:
                    # Update existing
                    cursor.execute(
                        """UPDATE profiles 
                           SET name = ?, age = ?, location = ?, ethnicity = ?, 
                               system_prompt_custom = ?, notes = ?
                           WHERE id = ?""",
                        (name, age, location, ethnicity, system_prompt or None, 
                         notes or None, self.profile_data['id'])
                    )
                else:
                    # Check for duplicate name
                    cursor.execute("SELECT id FROM profiles WHERE name = ?", (name,))
                    if cursor.fetchone():
                        QMessageBox.warning(self, "Duplicate", "A profile with this name already exists")
                        return
                    
                    # Insert new
                    is_current = self.current_checkbox.isChecked() if not self.is_edit else False
                    if is_current:
                        # Set all others to not current
                        cursor.execute("UPDATE profiles SET is_current = 0")
                    
                    cursor.execute(
                        """INSERT INTO profiles 
                           (name, age, location, ethnicity, system_prompt_custom, notes, is_current, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (name, age, location, ethnicity, system_prompt or None, 
                         notes or None, is_current)
                    )
            
            QMessageBox.information(self, "Success", "Profile saved successfully")
            self.accept()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")


class ModelProfilesTab(QWidget):
    """Tab for managing model profiles"""
    
    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self._setup_ui()
        self.load_profiles()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        
        # Current Profile Section
        current_group = QGroupBox("Current Profile")
        current_layout = QVBoxLayout()
        
        self.current_profile_label = QLabel("Profile: ---")
        self.current_info_label = QLabel("Info: ---")

        current_layout.addWidget(self.current_profile_label)
        current_layout.addWidget(self.current_info_label)
        
        button_layout = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        view_btn = QPushButton("View Details")
        edit_btn.clicked.connect(self._edit_current_profile)
        view_btn.clicked.connect(self._view_profile_details)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(view_btn)
        button_layout.addStretch()
        current_layout.addLayout(button_layout)
        
        current_group.setLayout(current_layout)
        layout.addWidget(current_group)
        
        # Search and Filter
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name...")
        self.search_input.textChanged.connect(self._filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Profiles Table
        table_group = QGroupBox("All Profiles")
        table_layout = QVBoxLayout()
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Active", "Name", "Info", "Uses", "Actions"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 150)
        
        table_layout.addWidget(self.table)
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)
        
        # Add button
        add_btn = QPushButton("+ Add New Profile")
        add_btn.clicked.connect(self._add_profile)
        layout.addWidget(add_btn)
        
        self.setLayout(layout)
    
    def load_profiles(self):
        try:
            # Clear search
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, name, response_tone, age, location, ethnicity, 
                              is_current, usage_count, system_prompt_custom, max_daily_interactions 
                       FROM profiles 
                       ORDER BY is_current DESC, created_at DESC"""
                )
                profiles = cursor.fetchall()
                
                # Get current profile
                cursor.execute(
                    """SELECT name, age, location 
                       FROM profiles 
                       WHERE is_current = 1 LIMIT 1"""
                )
                current = cursor.fetchone()

            if current:
                profile_name, age, location = current
                age_str = f", {age} years old" if age else ""
                location_str = f" from {location}" if location else ""
                self.current_profile_label.setText(f"Profile: {profile_name}")
                self.current_info_label.setText(f"Info: {profile_name}{age_str}{location_str}")
            else:
                self.current_profile_label.setText("Profile: Not Set")
                self.current_info_label.setText("Info: No profile selected")
            
            # Populate table
            self.table.setRowCount(len(profiles))
            for row, (pid, name, tone, age, location, ethnicity, is_current, usage, prompt, max_daily) in enumerate(profiles):
                # Active indicator
                active_item = QTableWidgetItem("✓ Active" if is_current else "")
                active_item.setData(Qt.UserRole, pid)
                if is_current:
                    active_item.setBackground(QColor("#C8E6C9"))

                # Name
                name_item = QTableWidgetItem(name)

                # Info
                info_parts = []
                if age:
                    info_parts.append(f"{age}y")
                if location:
                    info_parts.append(location[:20])
                info_text = ", ".join(info_parts) if info_parts else "---"
                info_item = QTableWidgetItem(info_text)

                # Usage count
                usage_item = QTableWidgetItem(str(usage or 0))

                # Actions
                actions_widget = QWidget()
                actions_layout = QHBoxLayout()

                select_btn = QPushButton("Select")
                edit_btn = QPushButton("Edit")
                delete_btn = QPushButton("Delete")

                select_btn.clicked.connect(lambda checked, pid=pid: self._set_current_profile(pid))
                edit_btn.clicked.connect(lambda checked, pid=pid: self._edit_profile(pid))
                delete_btn.clicked.connect(lambda checked, pid=pid: self._delete_profile(pid))

                actions_layout.addWidget(select_btn)
                actions_layout.addWidget(edit_btn)
                actions_layout.addWidget(delete_btn)
                actions_layout.setContentsMargins(0, 0, 0, 0)
                actions_widget.setLayout(actions_layout)

                # Add to table
                self.table.setItem(row, 0, active_item)
                self.table.setItem(row, 1, name_item)
                self.table.setItem(row, 2, info_item)
                self.table.setItem(row, 3, usage_item)
                self.table.setCellWidget(row, 4, actions_widget)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load profiles: {e}")
    
    def _filter_table(self, search_text: str):
        """Filter table by search text"""
        search_text = search_text.lower().strip()

        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            info_item = self.table.item(row, 2)

            if name_item:
                name = name_item.text().lower()
                info = info_item.text().lower() if info_item else ""

                if search_text in name or search_text in info:
                    self.table.showRow(row)
                else:
                    self.table.hideRow(row)
            else:
                self.table.showRow(row)
    
    def _add_profile(self):
        dialog = ProfileFormDialog(self, self.db)
        if dialog.exec_() == QDialog.Accepted:
            self.load_profiles()
    
    def _edit_profile(self, profile_id: int):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, name, response_tone, age, location, ethnicity,
                              system_prompt_custom, notes, max_daily_interactions
                       FROM profiles WHERE id = ?""",
                    (profile_id,)
                )
                row = cursor.fetchone()
            
            if row:
                profile_data = {
                    'id': row[0],
                    'name': row[1],
                    'response_tone': row[2],
                    'age': row[3],
                    'location': row[4],
                    'ethnicity': row[5],
                    'system_prompt_custom': row[6],
                    'notes': row[7],
                    'max_daily_interactions': row[8],
                }
                dialog = ProfileFormDialog(self, self.db, profile_data)
                if dialog.exec_() == QDialog.Accepted:
                    self.load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to edit profile: {e}")
    
    def _delete_profile(self, profile_id: int):
        reply = QMessageBox.question(self, "Confirm Delete", "Delete this profile?",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
                
                self.load_profiles()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete profile: {e}")
    
    def _set_current_profile(self, profile_id: int):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE profiles SET is_current = 0")
                cursor.execute("UPDATE profiles SET is_current = 1 WHERE id = ?", (profile_id,))
            
            self.load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set profile: {e}")
    
    def _edit_current_profile(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, name, response_tone, age, location, ethnicity,
                              system_prompt_custom, notes, max_daily_interactions
                       FROM profiles WHERE is_current = 1 LIMIT 1"""
                )
                row = cursor.fetchone()
            
            if row:
                profile_data = {
                    'id': row[0],
                    'name': row[1],
                    'response_tone': row[2],
                    'age': row[3],
                    'location': row[4],
                    'ethnicity': row[5],
                    'system_prompt_custom': row[6],
                    'notes': row[7],
                    'max_daily_interactions': row[8],
                }
                dialog = ProfileFormDialog(self, self.db, profile_data)
                if dialog.exec_() == QDialog.Accepted:
                    self.load_profiles()
            else:
                QMessageBox.warning(self, "No Profile", "Please select a profile first")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to edit profile: {e}")
    
    def _view_profile_details(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT name, age, location, ethnicity,
                              system_prompt_custom, notes, max_daily_interactions, usage_count
                       FROM profiles WHERE is_current = 1 LIMIT 1"""
                )
                row = cursor.fetchone()

            if row:
                name, age, location, ethnicity, prompt, notes, max_daily, usage = row
                details = f"""
Profile: {name}
Age: {age if age else 'Not specified'}
Location: {location if location else 'Not specified'}
Ethnicity: {ethnicity if ethnicity else 'Not specified'}

Max Daily Interactions: {max_daily}
Times Used: {usage or 0}

System Prompt:
{prompt if prompt else '(Using default prompt)'}

Notes:
{notes if notes else '(No notes)'}
                """
                QMessageBox.information(self, "Profile Details", details)
            else:
                QMessageBox.warning(self, "No Profile", "Please select a profile first")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load profile details: {e}")
