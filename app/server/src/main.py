import sys
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QSpinBox,
    QComboBox, QMessageBox, QTabWidget, QLineEdit, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QIcon, QFont
import time
import logging
import socket
import threading

from database.db_manager import DatabaseManager
from network.network_manager import NetworkManager
from config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DEFAULT_SESSION_DURATION, MAX_SESSION_DURATION,
    CURRENCY_SYMBOL, DATETIME_FORMAT
)
from discovery_service import DiscoveryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatusUpdater(QObject):
    """Helper class to handle status updates in the main thread."""
    status_update = Signal(str, str)  # client_ip, status

class GamingCenterServer(QMainWindow):
    def __init__(self, host: str = '0.0.0.0', port: int = 5001):
        super().__init__()
        self.host = host
        self.port = port
        self.running = False
        self.server = None
        self.discovery_service = DiscoveryService()
        self.db = DatabaseManager()
        self.network = NetworkManager()
        self.status_updater = StatusUpdater()
        self.status_updater.status_update.connect(self._handle_status_update)
        self.setup_ui()
        self.setup_network_handlers()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)  # Update every second

    def setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Computers tab
        computers_tab = QWidget()
        computers_layout = QVBoxLayout(computers_tab)
        
        # Computers table
        self.computers_table = QTableWidget()
        self.computers_table.setColumnCount(6)
        self.computers_table.setHorizontalHeaderLabels([
            "ID", "Name", "IP Address", "Status", "Last Seen", "Actions"
        ])
        computers_layout.addWidget(self.computers_table)

        # Add computer controls
        add_computer_layout = QHBoxLayout()
        self.computer_name_input = QLineEdit()
        self.computer_name_input.setPlaceholderText("Computer Name")
        self.computer_ip_input = QLineEdit()
        self.computer_ip_input.setPlaceholderText("IP Address")
        add_computer_btn = QPushButton("Add Computer")
        add_computer_btn.clicked.connect(self.add_computer)
        
        add_computer_layout.addWidget(self.computer_name_input)
        add_computer_layout.addWidget(self.computer_ip_input)
        add_computer_layout.addWidget(add_computer_btn)
        computers_layout.addLayout(add_computer_layout)

        tabs.addTab(computers_tab, "Computers")

        # Sessions tab
        sessions_tab = QWidget()
        sessions_layout = QVBoxLayout(sessions_tab)
        
        # Active sessions table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(7)
        self.sessions_table.setHorizontalHeaderLabels([
            "Computer", "Tariff", "Start Time", "Duration", "Status", "End Session", "Remove"
        ])
        sessions_layout.addWidget(self.sessions_table)

        # Start session controls
        start_session_layout = QHBoxLayout()
        self.session_computer_combo = QComboBox()
        self.session_tariff_combo = QComboBox()
        self.session_duration_spin = QSpinBox()
        self.session_duration_spin.setRange(1, MAX_SESSION_DURATION)
        self.session_duration_spin.setValue(DEFAULT_SESSION_DURATION)
        self.session_duration_spin.setSuffix(" hours")
        start_session_btn = QPushButton("Start Session")
        start_session_btn.clicked.connect(self.start_session)
        
        start_session_layout.addWidget(QLabel("Computer:"))
        start_session_layout.addWidget(self.session_computer_combo)
        start_session_layout.addWidget(QLabel("Tariff:"))
        start_session_layout.addWidget(self.session_tariff_combo)
        start_session_layout.addWidget(QLabel("Duration:"))
        start_session_layout.addWidget(self.session_duration_spin)
        start_session_layout.addWidget(start_session_btn)
        sessions_layout.addLayout(start_session_layout)

        tabs.addTab(sessions_tab, "Sessions")

        # Tariffs tab
        tariffs_tab = QWidget()
        tariffs_layout = QVBoxLayout(tariffs_tab)
        
        # Tariffs table
        self.tariffs_table = QTableWidget()
        self.tariffs_table.setColumnCount(4)
        self.tariffs_table.setHorizontalHeaderLabels([
            "Name", f"Price/Hour ({CURRENCY_SYMBOL})", "Description", "Status"
        ])
        tariffs_layout.addWidget(self.tariffs_table)

        # Add tariff controls
        add_tariff_layout = QHBoxLayout()
        self.tariff_name_input = QLineEdit()
        self.tariff_name_input.setPlaceholderText("Tariff Name")
        self.tariff_price_input = QDoubleSpinBox()
        self.tariff_price_input.setRange(0, 1000)
        self.tariff_price_input.setDecimals(2)
        self.tariff_price_input.setSuffix(f" {CURRENCY_SYMBOL}")
        self.tariff_desc_input = QLineEdit()
        self.tariff_desc_input.setPlaceholderText("Description")
        add_tariff_btn = QPushButton("Add Tariff")
        add_tariff_btn.clicked.connect(self.add_tariff)
        
        add_tariff_layout.addWidget(self.tariff_name_input)
        add_tariff_layout.addWidget(self.tariff_price_input)
        add_tariff_layout.addWidget(self.tariff_desc_input)
        add_tariff_layout.addWidget(add_tariff_btn)
        tariffs_layout.addLayout(add_tariff_layout)

        tabs.addTab(tariffs_tab, "Tariffs")

        # Reports tab
        reports_tab = QWidget()
        reports_layout = QVBoxLayout(reports_tab)
        
        # Daily report
        daily_report_layout = QVBoxLayout()
        daily_report_layout.addWidget(QLabel("Daily Report"))
        self.daily_report_table = QTableWidget()
        self.daily_report_table.setColumnCount(3)
        self.daily_report_table.setHorizontalHeaderLabels([
            "Total Sessions", "Total Minutes", f"Total Revenue ({CURRENCY_SYMBOL})"
        ])
        daily_report_layout.addWidget(self.daily_report_table)
        reports_layout.addLayout(daily_report_layout)

        tabs.addTab(reports_tab, "Reports")

        # Initial data load
        self.load_computers()
        self.load_tariffs()
        self.load_sessions()
        self.update_daily_report()

    def setup_network_handlers(self):
        """Setup network message handlers."""
        self.network.register_handler("status_update", self.handle_status_update)
        self.network.register_handler("session_end", self.handle_session_end)

    @Slot()
    def add_computer(self):
        """Add a new computer."""
        name = self.computer_name_input.text().strip()
        ip = self.computer_ip_input.text().strip()
        
        if not name or not ip:
            QMessageBox.warning(self, "Error", "Please enter both name and IP address")
            return
        
        try:
            self.db.add_computer(name, ip)
            self.load_computers()
            self.computer_name_input.clear()
            self.computer_ip_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add computer: {str(e)}")

    @Slot()
    def add_tariff(self):
        """Add a new tariff."""
        name = self.tariff_name_input.text().strip()
        price = self.tariff_price_input.value()
        description = self.tariff_desc_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a tariff name")
            return
        
        try:
            self.db.add_tariff(name, price, description)
            self.load_tariffs()
            self.tariff_name_input.clear()
            self.tariff_price_input.setValue(0)
            self.tariff_desc_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add tariff: {str(e)}")

    @Slot()
    def start_session(self):
        """Start a new session."""
        computer_id = self.session_computer_combo.currentData()
        tariff_id = self.session_tariff_combo.currentData()
        duration = self.session_duration_spin.value()
        
        if not computer_id or not tariff_id:
            QMessageBox.warning(self, "Error", "Please select both computer and tariff")
            return
        
        try:
            session_id = self.db.start_session(computer_id, tariff_id)
            self.network.send_message(
                self.get_computer_ip(computer_id),
                {
                    "type": "start_session",
                    "session_id": session_id,
                    "duration": duration
                }
            )
            self.load_sessions()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start session: {str(e)}")

    def load_computers(self):
        """Load computers into the table."""
        try:
            computers = self.db.get_all_computers()
            self.computers_table.setRowCount(len(computers))
            
            for i, computer in enumerate(computers):
                self.computers_table.setItem(i, 0, QTableWidgetItem(str(computer['id'])))
                self.computers_table.setItem(i, 1, QTableWidgetItem(computer['name']))
                self.computers_table.setItem(i, 2, QTableWidgetItem(computer['ip_address']))
                
                # Get current status from network manager
                current_status = self.network.get_client_status(computer['ip_address'])
                self.computers_table.setItem(i, 3, QTableWidgetItem(current_status))
                
                # Handle last_seen timestamp
                last_seen = computer['last_seen']
                if last_seen:
                    try:
                        if isinstance(last_seen, str):
                            last_seen = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        last_seen_str = last_seen.strftime(DATETIME_FORMAT)
                    except:
                        last_seen_str = "Invalid Date"
                else:
                    last_seen_str = "Never"
                
                self.computers_table.setItem(i, 4, QTableWidgetItem(last_seen_str))
                
                # Add remove button
                remove_btn = QPushButton("Remove")
                remove_btn.clicked.connect(lambda checked, c=computer: self.remove_computer(c['id']))
                self.computers_table.setCellWidget(i, 5, remove_btn)
            
            # Preserve current selection in the combo box
            current_id = self.session_computer_combo.currentData()
            self.session_computer_combo.clear()
            for computer in computers:
                self.session_computer_combo.addItem(computer['name'], computer['id'])
            # Restore previous selection if possible
            if current_id is not None:
                index = self.session_computer_combo.findData(current_id)
                if index != -1:
                    self.session_computer_combo.setCurrentIndex(index)
        except Exception as e:
            logger.error(f"Error loading computers: {e}")

    def load_tariffs(self):
        """Load tariffs into the table."""
        tariffs = self.db.get_tariffs()
        self.tariffs_table.setRowCount(len(tariffs))
        
        for i, tariff in enumerate(tariffs):
            self.tariffs_table.setItem(i, 0, QTableWidgetItem(tariff['name']))
            self.tariffs_table.setItem(i, 1, QTableWidgetItem(f"{tariff['price_per_hour']:.2f} {CURRENCY_SYMBOL}"))
            self.tariffs_table.setItem(i, 2, QTableWidgetItem(tariff['description']))
            self.tariffs_table.setItem(i, 3, QTableWidgetItem(
                "Active" if tariff['is_active'] else "Inactive"
            ))
        
        # Update tariff combo box
        self.session_tariff_combo.clear()
        for tariff in tariffs:
            self.session_tariff_combo.addItem(tariff['name'], tariff['id'])

    def load_sessions(self):
        """Load active sessions into the table."""
        sessions = self.db.get_active_sessions()
        self.sessions_table.setRowCount(len(sessions))
        
        for i, session in enumerate(sessions):
            self.sessions_table.setItem(i, 0, QTableWidgetItem(session['computer_name']))
            self.sessions_table.setItem(i, 1, QTableWidgetItem(session['tariff_name']))
            self.sessions_table.setItem(i, 2, QTableWidgetItem(
                session['start_time'].strftime(DATETIME_FORMAT)
            ))
            
            duration = (datetime.now() - session['start_time']).total_seconds() / 60
            self.sessions_table.setItem(i, 3, QTableWidgetItem(f"{int(duration)} minutes"))
            self.sessions_table.setItem(i, 4, QTableWidgetItem(session['status']))
            
            # End session button
            end_btn = QPushButton("End Session")
            end_btn.clicked.connect(lambda checked, s=session: self.end_session(s['id']))
            self.sessions_table.setCellWidget(i, 5, end_btn)
            
            # Remove session button
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda checked, s=session: self.remove_session(s['id']))
            self.sessions_table.setCellWidget(i, 6, remove_btn)

    def update_daily_report(self):
        """Update the daily report."""
        report = self.db.get_daily_report(datetime.now())
        self.daily_report_table.setRowCount(1)
        
        self.daily_report_table.setItem(0, 0, QTableWidgetItem(str(report.get('total_sessions', 0))))
        self.daily_report_table.setItem(0, 1, QTableWidgetItem(str(report.get('total_minutes', 0))))
        self.daily_report_table.setItem(0, 2, QTableWidgetItem(f"{report.get('total_revenue', 0.0):.2f} {CURRENCY_SYMBOL}"))

    def update_status(self):
        """Update the status of all tables."""
        self.load_computers()
        self.load_sessions()
        self.update_daily_report()

    def handle_status_update(self, message: Dict[str, Any], client_ip: str):
        """Handle status update from client in network thread."""
        try:
            self.status_updater.status_update.emit(client_ip, message['status'])
        except Exception as e:
            logger.error(f"Error handling status update: {e}")

    @Slot(str, str)
    def _handle_status_update(self, client_ip: str, status: str):
        """Handle status update in main thread."""
        try:
            computer = self.db.get_computer_by_ip(client_ip)
            if computer:
                self.db.update_computer_status(computer['id'], status)
                self.load_computers()  # Refresh the display
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    def handle_session_end(self, message: Dict[str, Any], client_ip: str):
        """Handle session end notification from client."""
        session_id = message['session_id']
        duration = message['duration']
        amount = message.get('amount', 0)
        payment_method = message.get('payment_method', 'Unknown')
        self.db.end_session(session_id, duration, amount)
        self.db.add_payment(session_id, amount, payment_method)

    def get_computer_ip(self, computer_id: int) -> Optional[str]:
        """Get computer IP address by ID."""
        computer = self.db.get_computer(computer_id)
        return computer['ip_address'] if computer else None

    def remove_computer(self, computer_id: int):
        """Remove a computer."""
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            "Are you sure you want to remove this computer?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Get computer IP before removal
            computer = self.db.get_computer(computer_id)
            if not computer:
                QMessageBox.warning(self, "Error", "Computer not found")
                return

            # Try to notify client about removal, but continue even if it fails
            try:
                self.network.send_message(
                    computer['ip_address'],
                    {"type": "computer_removed"}
                )
            except:
                pass  # Ignore notification errors

            # Remove the computer from database
            if self.db.remove_computer(computer_id):
                self.load_computers()
                QMessageBox.information(self, "Success", "Computer removed successfully")
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Could not remove computer. Make sure there are no active sessions."
                )

    def remove_session(self, session_id: int):
        """Remove a session."""
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            "Are you sure you want to remove this session?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.db.remove_session(session_id):
                self.load_sessions()
                QMessageBox.information(self, "Success", "Session removed successfully")
            else:
                QMessageBox.warning(self, "Error", "Could not remove session")

    def end_session(self, session_id: int):
        """End a session."""
        reply = QMessageBox.question(
            self,
            "Confirm End Session",
            "Are you sure you want to end this session?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Get session details before ending
                session = self.db.get_session(session_id)
                if not session:
                    QMessageBox.warning(self, "Error", "Session not found")
                    return

                # Get computer IP
                computer = self.db.get_computer(session['computer_id'])
                if not computer:
                    QMessageBox.warning(self, "Error", "Computer not found")
                    return

                # Notify client about session end
                if self.network.send_message(
                    computer['ip_address'],
                    {
                        "type": "end_session",
                        "session_id": session_id,
                        "force_end": True
                    }
                ):
                    # Wait a moment for client to process
                    time.sleep(1)
                    
                    # End session in database
                    self.db.end_session(session_id, 0, 0)  # Duration and amount will be calculated
                    self.load_sessions()
                    QMessageBox.information(self, "Success", "Session ended successfully")
                else:
                    QMessageBox.warning(self, "Error", "Could not notify client. The computer might be offline.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not end session: {str(e)}")

    def closeEvent(self, event):
        """Handle window close event."""
        self.network.close()
        event.accept()

    def start(self):
        """Start the server."""
        try:
            # Start discovery service
            self.discovery_service.start()
            
            # Update discovery service with server info
            self.discovery_service.update_server_info(
                name=f"Gaming Center Server ({self.host}:{self.port})",
                port=self.port,
                status="running"
            )
            
            # Start main server
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            self.running = True
            
            logger.info(f"Server started on {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server.accept()
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        except Exception as e:
            logger.error(f"Error starting server: {e}")
            self.stop()

    def stop(self):
        """Stop the server."""
        self.running = False
        if self.server:
            try:
                self.server.close()
            except:
                pass
        self.discovery_service.stop()
        logger.info("Server stopped")

    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle client connection."""
        try:
            logger.info(f"New connection from {address}")
            // ... existing client handling code ...
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass

def main():
    app = QApplication(sys.argv)
    window = GamingCenterServer()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 