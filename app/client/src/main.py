import sys
import os
import json
import ctypes
import hashlib
import base64
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QMessageBox, QDialog, QFormLayout, QDialogButtonBox, QComboBox, QDoubleSpinBox, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QGroupBox, QCheckBox, QColor
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QIcon, QFont, QColor
import time
import logging
import secrets

# Add the src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_manager import NetworkManager
from system_locker import SystemLocker
from shell_manager import ShellManager
from config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DEFAULT_SERVER_IP, DEFAULT_SERVER_PORT,
    DATETIME_FORMAT
)
from discovery_client import DiscoveryClient, ServerInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_admin():
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_as_admin():
    """Restart the program with administrator privileges."""
    try:
        if not is_admin():
            logger.info("Restarting with administrator privileges...")
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit()
    except Exception as e:
        logger.error(f"Error restarting as admin: {e}")
        return False
    return True

class StatusUpdater(QObject):
    status_changed = Signal(str)
    session_started = Signal(int, int)  # session_id, duration
    session_ended = Signal(bool)  # force_end

class SessionManager:
    def __init__(self):
        self.session_key = None
        self.fernet = None
        self.session_id = None
        self.session_start = None
        self.session_duration = None
        self.last_activity = None
        self.inactivity_timeout = 300  # 5 minutes
        self.inactivity_timer = None
        
    def generate_session_key(self):
        """Generate a new session key using PBKDF2."""
        salt = secrets.token_bytes(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secrets.token_bytes(32)))
        self.fernet = Fernet(key)
        return key
        
    def start_session(self, session_id: int, duration: int):
        """Start a new session with encryption and inactivity monitoring."""
        self.session_id = session_id
        self.session_start = datetime.now()
        self.session_duration = duration
        self.last_activity = datetime.now()
        self.session_key = self.generate_session_key()
        
        # Setup inactivity timer
        self._setup_inactivity_timer()
        
        return self.session_key
        
    def _setup_inactivity_timer(self):
        """Setup timer to monitor user inactivity."""
        if self.inactivity_timer:
            self.inactivity_timer.stop()
        
        self.inactivity_timer = QTimer()
        self.inactivity_timer.timeout.connect(self._check_inactivity)
        self.inactivity_timer.start(60000)  # Check every minute
        
    def _check_inactivity(self):
        """Check for user inactivity and handle accordingly."""
        if not self.last_activity:
            return
            
        inactive_time = (datetime.now() - self.last_activity).total_seconds()
        if inactive_time >= self.inactivity_timeout:
            logger.warning(f"User inactive for {inactive_time} seconds")
            self._handle_inactivity()
            
    def _handle_inactivity(self):
        """Handle user inactivity."""
        # Reset last activity to prevent multiple notifications
        self.last_activity = datetime.now()
        
        # Notify the user
        QMessageBox.warning(
            None,
            "Inactivity Warning",
            "You have been inactive for a while. Your session will be ended if no activity is detected.",
            QMessageBox.Ok
        )
        
    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
        
    def encrypt_message(self, message: dict) -> str:
        """Encrypt a message using the session key."""
        if not self.fernet:
            raise ValueError("No active session")
        return self.fernet.encrypt(json.dumps(message).encode()).decode()
        
    def decrypt_message(self, encrypted_message: str) -> dict:
        """Decrypt a message using the session key."""
        if not self.fernet:
            raise ValueError("No active session")
        return json.loads(self.fernet.decrypt(encrypted_message.encode()).decode())
        
    def get_session_info(self) -> dict:
        """Get current session information."""
        if not self.session_start:
            return None
        return {
            'session_id': self.session_id,
            'start_time': self.session_start.isoformat(),
            'duration': self.session_duration,
            'remaining': self.get_remaining_time(),
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }
        
    def get_remaining_time(self) -> int:
        """Get remaining session time in seconds."""
        if not self.session_start:
            return 0
        elapsed = (datetime.now() - self.session_start).total_seconds()
        remaining = (self.session_duration * 3600) - elapsed
        return max(0, int(remaining))
        
    def end_session(self):
        """End the current session and cleanup."""
        if self.inactivity_timer:
            self.inactivity_timer.stop()
            self.inactivity_timer = None
            
        self.session_key = None
        self.fernet = None
        self.session_id = None
        self.session_start = None
        self.session_duration = None
        self.last_activity = None

class GamingCenterClient(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Initialize session manager
        self.session_manager = SessionManager()
        
        # Check for admin privileges
        if not is_admin():
            reply = QMessageBox.question(
                self,
                "Administrator Privileges Required",
                "This application requires administrator privileges to run properly. Would you like to restart with administrator privileges?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                run_as_admin()
            else:
                QMessageBox.warning(
                    self,
                    "Limited Functionality",
                    "The application will run with limited functionality. Some features may not work properly."
                )
        
        self.network = NetworkManager()
        self.system_locker = SystemLocker()
        self.shell_manager = ShellManager()
        self.current_session = None
        self.status_updater = StatusUpdater()
        self.discovery_client = DiscoveryClient()
        self.discovery_client.set_server_found_callback(self._on_server_found)
        self.discovery_client.set_server_lost_callback(self._on_server_lost)
        
        # Connect signals
        self.status_updater.status_changed.connect(self.update_status_label)
        self.status_updater.session_started.connect(self.start_session)
        self.status_updater.session_ended.connect(self.end_session)
        
        self.setup_ui()
        self.load_config()
        self.setup_network_handlers()
        self.connect_to_server()
        
        # Setup activity monitoring
        self.setup_activity_monitoring()

    def setup_activity_monitoring(self):
        """Setup monitoring for user activity."""
        # Monitor mouse movement
        self.setMouseTracking(True)
        
        # Monitor keyboard events
        self.installEventFilter(self)
        
    def eventFilter(self, obj, event):
        """Filter events to detect user activity."""
        if event.type() in (event.MouseButtonPress, event.KeyPress):
            if self.session_manager:
                self.session_manager.update_activity()
        return super().eventFilter(obj, event)
        
    def mouseMoveEvent(self, event):
        """Handle mouse movement events."""
        if self.session_manager:
            self.session_manager.update_activity()
        super().mouseMoveEvent(event)

    def setup_network_handlers(self):
        """Setup network message handlers."""
        self.network.register_handler("start_session", self.handle_start_session)
        self.network.register_handler("end_session", self.handle_end_session)
        self.network.register_handler("computer_removed", self.handle_computer_removed)
        self.network.register_handler("connection_lost", self.handle_connection_lost)

    def handle_start_session(self, message):
        """Handle session start message from server."""
        try:
            session_id = message['session_id']
            duration = message['duration']
            logger.info(f"Starting session {session_id} for {duration} hours")
            
            # Start encrypted session
            session_key = self.session_manager.start_session(session_id, duration)
            
            # Send encrypted acknowledgment
            ack_message = {
                'type': 'session_started',
                'session_id': session_id,
                'session_key': session_key.decode()
            }
            self.network.send_message(self.session_manager.encrypt_message(ack_message))
            
            self.status_updater.session_started.emit(session_id, duration)
        except Exception as e:
            logger.error(f"Error handling start session: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to start session: {str(e)}"
            )

    def handle_end_session(self, message):
        """Handle session end message from server."""
        try:
            force_end = message.get('force_end', False)
            logger.info(f"Ending session (force: {force_end})")
            self.status_updater.session_ended.emit(force_end)
        except Exception as e:
            logger.error(f"Error handling end session: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to end session: {str(e)}"
            )

    def handle_computer_removed(self, message):
        """Handle computer removed message from server."""
        QMessageBox.information(self, "Computer Removed", "This computer has been removed from the system. The application will now close.")
        self.close()

    def handle_connection_lost(self, message):
        """Handle connection lost message."""
        self.status_label.setText("Connection lost - attempting to reconnect...")
        QTimer.singleShot(5000, self.reconnect_to_server)

    def reconnect_to_server(self):
        """Attempt to reconnect to the server."""
        if not self.network.is_connected():
            self.connect_to_server()

    def update_status_label(self, status):
        """Update the status label in the UI thread."""
        self.status_label.setText(status)

    def setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Server connection controls
        server_layout = QHBoxLayout()
        self.server_ip_input = QLineEdit()
        self.server_ip_input.setPlaceholderText("Server IP Address")
        self.server_port_input = QLineEdit()
        self.server_port_input.setPlaceholderText("Server Port")
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_to_server)
        
        server_layout.addWidget(QLabel("Server IP:"))
        server_layout.addWidget(self.server_ip_input)
        server_layout.addWidget(QLabel("Port:"))
        server_layout.addWidget(self.server_port_input)
        server_layout.addWidget(connect_btn)
        layout.addLayout(server_layout)

        # Status label
        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Session info
        self.session_label = QLabel("No active session")
        self.session_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.session_label)

        # Time remaining
        self.time_label = QLabel("")
        self.time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.time_label)

        # End session button
        self.end_session_btn = QPushButton("End Session")
        self.end_session_btn.clicked.connect(self.end_session)
        self.end_session_btn.setEnabled(False)
        layout.addWidget(self.end_session_btn)

        # Setup update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)  # Update every second

    def load_config(self):
        """Load configuration from file."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.server_ip_input.setText(config.get('server_ip', DEFAULT_SERVER_IP))
                    self.server_port_input.setText(str(config.get('server_port', DEFAULT_SERVER_PORT)))
            else:
                self.server_ip_input.setText(DEFAULT_SERVER_IP)
                self.server_port_input.setText(str(DEFAULT_SERVER_PORT))
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.server_ip_input.setText(DEFAULT_SERVER_IP)
            self.server_port_input.setText(str(DEFAULT_SERVER_PORT))

    def save_config(self):
        """Save configuration to file."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            config = {
                'server_ip': self.server_ip_input.text(),
                'server_port': int(self.server_port_input.text())
            }
            with open(config_path, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def connect_to_server(self):
        """Connect to the server."""
        try:
            server_ip = self.server_ip_input.text()
            server_port = int(self.server_port_input.text())
            
            if self.network.connect(server_ip, server_port):
                self.status_updater.status_changed.emit("Connected to server")
                self.save_config()
            else:
                self.status_updater.status_changed.emit("Failed to connect to server")
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.status_updater.status_changed.emit("Error connecting to server")

    def update_status(self):
        """Update the status display."""
        if self.current_session:
            remaining = self.current_session['end_time'] - datetime.now()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                seconds = int(remaining.total_seconds() % 60)
                self.time_label.setText(f"Time remaining: {hours:02d}:{minutes:02d}:{seconds:02d}")
                
                # Update kiosk window time display
                if self.shell_manager.kiosk_window:
                    self.shell_manager.kiosk_window.update_time(int(remaining.total_seconds()))
            else:
                self.end_session()

    def start_session(self, session_id: int, duration: int):
        """Start a new session with enhanced security."""
        try:
            self.current_session = {
                'id': session_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(hours=duration)
            }
            self.session_label.setText(f"Session {session_id} active")
            self.time_label.setText(f"Duration: {duration} hours")
            self.end_session_btn.setEnabled(True)
            
            # Start system lockdown
            self.system_locker.start_monitoring()
            
            # Load application configuration
            config_path = os.path.join(os.path.dirname(__file__), 'apps_config.json')
            self.shell_manager.load_app_config(config_path)
            
            # Hide the main window before starting kiosk mode
            self.hide()
            
            # Get the full path to the Python executable
            python_exe = sys.executable
            script_path = os.path.abspath(__file__)
            
            logger.info(f"Starting kiosk mode with Python: {python_exe}")
            logger.info(f"Script path: {script_path}")
            
            # Create a batch file to run the script
            batch_path = os.path.join(os.path.dirname(script_path), "run_kiosk.bat")
            with open(batch_path, "w") as f:
                f.write(f'@echo off\n"{python_exe}" "{script_path}" --kiosk-mode\n')
            
            if not self.shell_manager.start_kiosk_mode(None, batch_path):
                logger.error("Failed to start kiosk mode")
                self.show()  # Show main window if kiosk mode fails
                QMessageBox.warning(
                    self,
                    "Kiosk Mode Error",
                    "Failed to start kiosk mode. The application will continue with limited functionality."
                )
            else:
                # Connect logout signal
                if self.shell_manager.kiosk_window:
                    self.shell_manager.kiosk_window.logout_requested.connect(self.end_session)
            
            logger.info(f"Session {session_id} started successfully")
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            self.show()  # Show main window if there's an error
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to start session: {str(e)}"
            )

    def end_session(self, force_end=False):
        """End the current session with proper cleanup."""
        if self.current_session:
            try:
                # Show the main window before showing payment dialog
                self.show()
                
                duration = int((datetime.now() - self.current_session['start_time']).total_seconds() / 60)
                # Show payment dialog
                default_amount = self.calculate_default_amount(duration)
                payment_dialog = PaymentDialog(default_amount, self)
                if payment_dialog.exec() == QDialog.Accepted:
                    amount, method = payment_dialog.get_payment()
                    self.network.send_message({
                        'type': 'session_end',
                        'session_id': self.current_session['id'],
                        'duration': duration,
                        'amount': amount,
                        'payment_method': method
                    })
                else:
                    return  # User cancelled payment dialog
            except Exception as e:
                logger.error(f"Error ending session: {e}")
            finally:
                # Stop system lockdown
                self.system_locker.stop_monitoring()
                
                # Stop kiosk mode
                if not self.shell_manager.stop_kiosk_mode():
                    logger.error("Failed to stop kiosk mode")
                
                # End session and cleanup
                self.session_manager.end_session()
                
                self.current_session = None
                self.session_label.setText("No active session")
                self.time_label.setText("")
                self.end_session_btn.setEnabled(False)
                logger.info("Session ended")
                if force_end:
                    QMessageBox.information(self, "Session Ended", "Your session has been ended by the administrator.")

    def calculate_default_amount(self, duration_minutes: int) -> float:
        # Placeholder: you may want to fetch the tariff from the server or store it locally
        # For now, assume a fixed rate (e.g., 2.00 per hour)
        rate_per_minute = 2.00 / 60
        return round(duration_minutes * rate_per_minute, 2)

    def closeEvent(self, event):
        """Handle window close event."""
        if self.current_session:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "There is an active session. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.end_session()
                event.accept()
            else:
                event.ignore()
        else:
            # Make sure to stop kiosk mode if it's active
            if self.shell_manager.is_active:
                self.shell_manager.stop_kiosk_mode()
            event.accept()

    def start(self):
        """Start the client application."""
        try:
            # Start discovery client
            self.discovery_client.start()
            
            # Start network client
            self.network.start()
            
            # Show server selection dialog
            self._show_server_selection()
            
            # Start the application
            self.exec_()
        except Exception as e:
            logger.error(f"Error starting client: {e}")
            self.show_error("Error", f"Failed to start client: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        try:
            self.discovery_client.stop()
            self.network.stop()
            self.shell_manager.stop_kiosk_mode()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def _show_server_selection(self):
        """Show server selection dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Server")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        
        # Server list
        server_list = QTableWidget()
        server_list.setColumnCount(5)
        server_list.setHorizontalHeaderLabels([
            "Server Name", "Address", "Version", "Status", "Latency"
        ])
        server_list.setSelectionBehavior(QTableWidget.SelectRows)
        server_list.setSelectionMode(QTableWidget.SingleSelection)
        server_list.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("Available Servers:"))
        layout.addWidget(server_list)
        
        # Server details
        details_group = QGroupBox("Server Details")
        details_layout = QVBoxLayout()
        self.features_label = QLabel("Features: None")
        self.version_label = QLabel("Version: None")
        details_layout.addWidget(self.features_label)
        details_layout.addWidget(self.version_label)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Auto-connect checkbox
        self.auto_connect_cb = QCheckBox("Auto-connect to best server")
        self.auto_connect_cb.setChecked(True)
        button_layout.addWidget(self.auto_connect_cb)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: self._update_server_list(server_list))
        button_layout.addWidget(refresh_btn)
        
        # Connect button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(lambda: self._connect_to_selected_server(server_list, dialog))
        button_layout.addWidget(connect_btn)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Set up server list selection handler
        server_list.itemSelectionChanged.connect(
            lambda: self._update_server_details(server_list)
        )
        
        # Initial server list update
        self._update_server_list(server_list)
        
        # Auto-connect if enabled
        if self.auto_connect_cb.isChecked():
            best_server = self.discovery_client.get_best_server()
            if best_server:
                self._connect_to_server(best_server, dialog)
                return
        
        # Show dialog
        dialog.exec_()

    def _update_server_list(self, server_list: QTableWidget):
        """Update the server list widget."""
        server_list.setRowCount(0)
        for server in self.discovery_client.get_available_servers():
            row = server_list.rowCount()
            server_list.insertRow(row)
            
            # Server name
            name_item = QTableWidgetItem(server.name)
            name_item.setData(Qt.UserRole, server)
            server_list.setItem(row, 0, name_item)
            
            # Address
            server_list.setItem(row, 1, QTableWidgetItem(f"{server.address}:{server.port}"))
            
            # Version
            server_list.setItem(row, 2, QTableWidgetItem(server.version))
            
            # Status
            status_item = QTableWidgetItem(server.status)
            status_item.setForeground(
                QColor("green") if server.status == "running" else QColor("red")
            )
            server_list.setItem(row, 3, status_item)
            
            # Latency
            latency_text = f"{server.latency:.1f}ms" if server.latency else "N/A"
            latency_item = QTableWidgetItem(latency_text)
            if server.latency:
                latency_item.setForeground(
                    QColor("green") if server.latency < 100 else
                    QColor("orange") if server.latency < 300 else
                    QColor("red")
                )
            server_list.setItem(row, 4, latency_item)
        
        server_list.resizeColumnsToContents()

    def _update_server_details(self, server_list: QTableWidget):
        """Update the server details section."""
        selected_items = server_list.selectedItems()
        if not selected_items:
            self.features_label.setText("Features: None")
            self.version_label.setText("Version: None")
            return
            
        server = selected_items[0].data(Qt.UserRole)
        self.features_label.setText(f"Features: {', '.join(server.features)}")
        self.version_label.setText(f"Version: {server.version}")

    def _connect_to_selected_server(self, server_list: QTableWidget, dialog: QDialog):
        """Connect to the selected server."""
        selected_items = server_list.selectedItems()
        if not selected_items:
            self.show_error("Error", "Please select a server")
            return
            
        server = selected_items[0].data(Qt.UserRole)
        self._connect_to_server(server, dialog)

    def _connect_to_server(self, server: ServerInfo, dialog: QDialog):
        """Connect to a specific server."""
        try:
            if self.network.connect(server.address, server.port):
                dialog.accept()
            else:
                self.show_error("Connection Error", f"Failed to connect to server: {server.name}")
        except Exception as e:
            self.show_error("Connection Error", f"Failed to connect to server: {e}")

    def _on_server_found(self, server: ServerInfo):
        """Handle new server discovery."""
        logger.info(f"Discovered server: {server.name} ({server.address}:{server.port})")
        # Update UI if server selection dialog is open
        for widget in self.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.windowTitle() == "Select Server":
                for child in widget.findChildren(QListWidget):
                    self._update_server_list(child)
                break

    def _on_server_lost(self, server: ServerInfo):
        """Handle server loss."""
        logger.info(f"Lost server: {server.name} ({server.address}:{server.port})")
        # Update UI if server selection dialog is open
        for widget in self.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.windowTitle() == "Select Server":
                for child in widget.findChildren(QListWidget):
                    self._update_server_list(child)
                break

class PaymentDialog(QDialog):
    def __init__(self, default_amount: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Payment")
        layout = QFormLayout(self)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 10000)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(default_amount)
        layout.addRow("Amount:", self.amount_input)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Cash", "Card", "Other"])
        layout.addRow("Payment Method:", self.method_combo)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_payment(self):
        return self.amount_input.value(), self.method_combo.currentText()

def main():
    app = QApplication(sys.argv)
    
    # Check if we're running in kiosk mode
    if "--kiosk-mode" in sys.argv:
        logger.info("Starting in kiosk mode")
        window = KioskWindow([
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Steam\\Steam.exe",
            "C:\\Windows\\System32\\notepad.exe",
            "C:\\Windows\\System32\\calc.exe",
        ])
        window.showFullScreen()
    else:
        logger.info("Starting in normal mode")
        window = GamingCenterClient()
        window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 