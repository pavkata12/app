import os
import sys
import winreg
import logging
import subprocess
import json
from typing import List, Optional, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, 
    QMessageBox, QFrame, QGridLayout, QApplication, QComboBox, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtCore import QUrl

logger = logging.getLogger(__name__)

class AppConfig:
    def __init__(self, name: str, path: str, icon: str = None, category: str = "Other"):
        self.name = name
        self.path = path
        self.icon = icon
        self.category = category

class ShellManager:
    def __init__(self):
        self.original_shell = None
        self.is_admin = self._check_admin()
        self.allowed_apps: Dict[str, AppConfig] = {}
        self.kiosk_window = None
        self.is_active = False
        self.screen_timeout = 300  # 5 minutes
        self.screen_timeout_timer = None
        
        if not self.is_admin:
            logger.warning("ShellManager initialized without admin privileges. Kiosk mode will not work.")

    def _check_admin(self) -> bool:
        """Check if running with administrator privileges."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.error(f"Error checking admin privileges: {e}")
            return False

    def load_app_config(self, config_path: str):
        """Load application configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                for app in config['apps']:
                    self.allowed_apps[app['name']] = AppConfig(
                        name=app['name'],
                        path=app['path'],
                        icon=app.get('icon'),
                        category=app.get('category', 'Other')
                    )
            logger.info(f"Loaded {len(self.allowed_apps)} applications from config")
        except Exception as e:
            logger.error(f"Error loading app config: {e}")
            raise

    def start_kiosk_mode(self, allowed_apps: List[str] = None, batch_path: str = None):
        """Start kiosk mode with enhanced security and features."""
        if not self.is_admin:
            logger.error("Administrator privileges required for kiosk mode")
            return False

        try:
            # Store original shell
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon",
                0, winreg.KEY_READ
            )
            self.original_shell = winreg.QueryValueEx(key, "Shell")[0]
            winreg.CloseKey(key)

            # Set our batch file as the shell
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "Shell", 0, winreg.REG_SZ, batch_path)
            winreg.CloseKey(key)

            # Store allowed applications
            if allowed_apps:
                self.allowed_apps = {name: self.allowed_apps[name] for name in allowed_apps if name in self.allowed_apps}
            
            # Create and show kiosk window
            self._create_kiosk_window()
            self.is_active = True

            # Setup security features
            self._setup_security_features()
            
            # Setup screen timeout
            self._setup_screen_timeout()

            logger.info("Kiosk mode started successfully")
            return True
        except Exception as e:
            logger.error(f"Error starting kiosk mode: {e}")
            return False

    def _setup_security_features(self):
        """Setup additional security features."""
        try:
            # Disable task manager
            self._disable_task_manager()
            
            # Disable alt+tab
            self._disable_alt_tab()
            
            # Disable Windows key
            self._disable_windows_key()
            
            # Disable Ctrl+Alt+Delete
            self._disable_ctrl_alt_delete()
            
            # Disable right-click
            self._disable_right_click()
            
            logger.info("Security features setup completed")
        except Exception as e:
            logger.error(f"Error setting up security features: {e}")

    def _setup_screen_timeout(self):
        """Setup screen timeout timer."""
        if self.screen_timeout_timer:
            self.screen_timeout_timer.stop()
        
        self.screen_timeout_timer = QTimer()
        self.screen_timeout_timer.timeout.connect(self._handle_screen_timeout)
        self.screen_timeout_timer.start(self.screen_timeout * 1000)

    def _handle_screen_timeout(self):
        """Handle screen timeout."""
        if self.kiosk_window and self.kiosk_window.isActiveWindow():
            self.kiosk_window.showFullScreen()
            self.kiosk_window.activateWindow()
            self.kiosk_window.raise_()

    def _disable_windows_key(self):
        """Disable Windows key."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoWinKeys", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info("Windows key disabled")
        except Exception as e:
            logger.error(f"Error disabling Windows key: {e}")

    def _disable_ctrl_alt_delete(self):
        """Disable Ctrl+Alt+Delete."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableCAD", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info("Ctrl+Alt+Delete disabled")
        except Exception as e:
            logger.error(f"Error disabling Ctrl+Alt+Delete: {e}")

    def _disable_right_click(self):
        """Disable right-click in kiosk mode."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoViewContextMenu", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info("Right-click disabled")
        except Exception as e:
            logger.error(f"Error disabling right-click: {e}")

    def stop_kiosk_mode(self):
        """Stop kiosk mode and restore original settings."""
        if not self.is_admin:
            logger.error("Administrator privileges required to stop kiosk mode")
            return False

        try:
            # Stop screen timeout timer
            if self.screen_timeout_timer:
                self.screen_timeout_timer.stop()
                self.screen_timeout_timer = None

            # Restore original shell
            if self.original_shell:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon",
                    0, winreg.KEY_WRITE
                )
                winreg.SetValueEx(key, "Shell", 0, winreg.REG_SZ, self.original_shell)
                winreg.CloseKey(key)

            # Close kiosk window
            if self.kiosk_window:
                self.kiosk_window.close()
                self.kiosk_window = None

            # Restore security features
            self._restore_security_features()

            self.is_active = False
            logger.info("Kiosk mode stopped successfully")
            return True
        except Exception as e:
            logger.error(f"Error stopping kiosk mode: {e}")
            return False

    def _restore_security_features(self):
        """Restore all security features to their original state."""
        try:
            self._enable_task_manager()
            self._enable_alt_tab()
            self._enable_windows_key()
            self._enable_ctrl_alt_delete()
            self._enable_right_click()
            logger.info("Security features restored")
        except Exception as e:
            logger.error(f"Error restoring security features: {e}")

    def _enable_windows_key(self):
        """Enable Windows key."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoWinKeys", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Windows key enabled")
        except Exception as e:
            logger.error(f"Error enabling Windows key: {e}")

    def _enable_ctrl_alt_delete(self):
        """Enable Ctrl+Alt+Delete."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableCAD", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Ctrl+Alt+Delete enabled")
        except Exception as e:
            logger.error(f"Error enabling Ctrl+Alt+Delete: {e}")

    def _enable_right_click(self):
        """Enable right-click."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoViewContextMenu", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Right-click enabled")
        except Exception as e:
            logger.error(f"Error enabling right-click: {e}")

    def _create_kiosk_window(self):
        """Create the kiosk mode window."""
        try:
            self.kiosk_window = KioskWindow(self.allowed_apps)
            self.kiosk_window.showFullScreen()
            logger.info("Kiosk window created and shown")
        except Exception as e:
            logger.error(f"Error creating kiosk window: {e}")
            raise

    def _disable_task_manager(self):
        """Disable task manager."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info("Task manager disabled")
        except Exception as e:
            logger.error(f"Error disabling task manager: {e}")

    def _enable_task_manager(self):
        """Enable task manager."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Task manager enabled")
        except Exception as e:
            logger.error(f"Error enabling task manager: {e}")

    def _disable_alt_tab(self):
        """Disable alt+tab functionality."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoAltTab", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info("Alt+Tab disabled")
        except Exception as e:
            logger.error(f"Error disabling alt+tab: {e}")

    def _enable_alt_tab(self):
        """Enable alt+tab functionality."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoAltTab", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Alt+Tab enabled")
        except Exception as e:
            logger.error(f"Error enabling alt+tab: {e}")

class KioskWindow(QWidget):
    logout_requested = Signal()
    app_launched = Signal(str)  # Signal when an app is launched

    def __init__(self, allowed_apps: Dict[str, AppConfig] = None):
        super().__init__()
        self.allowed_apps = allowed_apps or {}
        self.current_category = None
        self.setup_ui()
        self.setup_timer()
        logger.info("KioskWindow initialized")

    def setup_ui(self):
        """Setup the kiosk window UI with improved layout and features."""
        try:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            main_layout = QVBoxLayout(self)
            
            # Top bar with logout button, time, and category selector
            top_bar = QHBoxLayout()
            
            # Logout button
            logout_btn = QPushButton("Logout")
            logout_btn.setFixedSize(100, 30)
            logout_btn.clicked.connect(self._handle_logout)
            top_bar.addWidget(logout_btn)
            
            # Time display
            self.time_label = QLabel()
            self.time_label.setAlignment(Qt.AlignCenter)
            self.time_label.setStyleSheet("font-size: 16px; font-weight: bold;")
            top_bar.addWidget(self.time_label)
            
            # Category selector
            self.category_combo = QComboBox()
            self.category_combo.setFixedSize(150, 30)
            self.category_combo.currentTextChanged.connect(self._change_category)
            top_bar.addWidget(self.category_combo)
            
            # Add top bar to main layout
            main_layout.addLayout(top_bar)
            
            # Add a separator line
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            separator.setStyleSheet("background-color: #4b4b4b;")
            main_layout.addWidget(separator)
            
            # Create stacked widget for different category views
            self.stacked_widget = QStackedWidget()
            main_layout.addWidget(self.stacked_widget)
            
            # Create pages for each category
            self.category_pages = {}
            self._setup_category_pages()
            
            # Set stylesheet for modern look
            self.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #3b3b3b;
                    border: none;
                    border-radius: 5px;
                    padding: 10px;
                    color: #ffffff;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #4b4b4b;
                }
                QPushButton:pressed {
                    background-color: #5b5b5b;
                }
                QLabel {
                    color: #ffffff;
                    font-size: 14px;
                }
                QComboBox {
                    background-color: #3b3b3b;
                    border: none;
                    border-radius: 5px;
                    padding: 5px;
                    color: #ffffff;
                    font-size: 14px;
                }
                QComboBox:hover {
                    background-color: #4b4b4b;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
            """)
            
            logger.info("Kiosk window UI setup completed")
        except Exception as e:
            logger.error(f"Error setting up kiosk window UI: {e}")
            raise

    def _setup_category_pages(self):
        """Setup pages for each category."""
        # Get unique categories
        categories = set(app.category for app in self.allowed_apps.values())
        categories.add("All")  # Add "All" category
        
        # Create a page for each category
        for category in categories:
            page = QWidget()
            layout = QGridLayout(page)
            
            # Add apps for this category
            row, col = 0, 0
            max_cols = 4
            
            for app_name, app_config in self.allowed_apps.items():
                if category == "All" or app_config.category == category:
                    app_btn = self._create_app_button(app_name, app_config)
                    layout.addWidget(app_btn, row, col)
                    
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
            
            # Add the page to stacked widget
            self.stacked_widget.addWidget(page)
            self.category_pages[category] = page
            
            # Add category to combo box
            self.category_combo.addItem(category)
        
        # Set default category
        self.category_combo.setCurrentText("All")

    def _create_app_button(self, app_name: str, app_config: AppConfig) -> QPushButton:
        """Create an application button with icon and tooltip."""
        app_btn = QPushButton(app_name)
        app_btn.setFixedSize(150, 150)
        app_btn.setToolTip(f"Category: {app_config.category}")
        
        # Set icon if available
        if app_config.icon and os.path.exists(app_config.icon):
            icon = QIcon(app_config.icon)
            app_btn.setIcon(icon)
            app_btn.setIconSize(QSize(64, 64))
        
        app_btn.clicked.connect(lambda checked, name=app_name: self._launch_app(name))
        return app_btn

    def _change_category(self, category: str):
        """Change the current category view."""
        if category in self.category_pages:
            self.current_category = category
            self.stacked_widget.setCurrentWidget(self.category_pages[category])
            logger.info(f"Changed to category: {category}")

    def update_time(self, remaining_seconds: int = 0):
        """Update time remaining display with improved formatting."""
        try:
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            seconds = remaining_seconds % 60
            
            # Format time with different colors based on remaining time
            if remaining_seconds < 300:  # Less than 5 minutes
                color = "#ff4444"  # Red
            elif remaining_seconds < 900:  # Less than 15 minutes
                color = "#ffaa00"  # Orange
            else:
                color = "#44ff44"  # Green
            
            self.time_label.setText(
                f'<span style="color: {color}">'
                f'Time Remaining: {hours:02d}:{minutes:02d}:{seconds:02d}'
                f'</span>'
            )
        except Exception as e:
            logger.error(f"Error updating time display: {e}")

    def _handle_logout(self):
        """Handle logout button click."""
        reply = QMessageBox.question(
            self,
            "Confirm Logout",
            "Are you sure you want to end your session?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            logger.info("Logout confirmed by user")
            self.logout_requested.emit()

    def _launch_app(self, app_name: str):
        """Launch an application with error handling."""
        try:
            if app_name in self.allowed_apps:
                app_config = self.allowed_apps[app_name]
                subprocess.Popen(app_config.path)
                self.app_launched.emit(app_name)
                logger.info(f"Launched application: {app_name}")
            else:
                logger.warning(f"Attempted to launch unauthorized application: {app_name}")
        except Exception as e:
            logger.error(f"Error launching application {app_name}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to launch {app_name}: {str(e)}")

    def keyPressEvent(self, event):
        """Handle key press events."""
        # Block all key combinations except Alt+F4
        if event.key() == Qt.Key_Escape:
            event.ignore()
        elif event.key() == Qt.Key_F11:
            event.ignore()
        elif event.key() == Qt.Key_Alt:
            event.ignore()
        else:
            super().keyPressEvent(event) 