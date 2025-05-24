import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path: str = "database/gaming_center.db"):
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_db()

    def _ensure_db_directory(self) -> None:
        """Ensure the database directory exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_db(self) -> None:
        """Initialize the database with schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r') as f:
            schema = f.read()
        
        with self.get_connection() as conn:
            conn.executescript(schema)

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Computer management
    def add_computer(self, name: str, ip_address: str) -> int:
        """Add a new computer to the database."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO computers (name, ip_address) VALUES (?, ?)",
                (name, ip_address)
            )
            return cursor.lastrowid

    def update_computer_status(self, computer_id: int, status: str) -> None:
        """Update computer status."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE computers SET status = ?, last_seen = datetime('now') WHERE id = ?",
                (status, computer_id)
            )

    def get_computer(self, computer_id: int) -> Optional[Dict[str, Any]]:
        """Get computer by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, ip_address, status, 
                       datetime(last_seen) as last_seen 
                FROM computers WHERE id = ?
            """, (computer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_computer_by_ip(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get computer by IP address."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, ip_address, status, 
                       datetime(last_seen) as last_seen 
                FROM computers WHERE ip_address = ?
            """, (ip_address,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_computers(self) -> List[Dict[str, Any]]:
        """Get all computers."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, ip_address, status, 
                       datetime(last_seen) as last_seen 
                FROM computers ORDER BY name
            """)
            return [dict(row) for row in cursor.fetchall()]

    # Session management
    def start_session(self, computer_id: int, tariff_id: int) -> int:
        """Start a new session."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO sessions (computer_id, tariff_id, start_time) VALUES (?, ?, ?)",
                (computer_id, tariff_id, datetime.now())
            )
            return cursor.lastrowid

    def end_session(self, session_id: int, duration_minutes: int, amount_paid: float) -> None:
        """End a session and record payment."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE sessions 
                SET end_time = ?, duration_minutes = ?, amount_paid = ?, status = 'completed'
                WHERE id = ?
                """,
                (datetime.now(), duration_minutes, amount_paid, session_id)
            )

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT s.*, c.name as computer_name, t.name as tariff_name,
                       datetime(s.start_time) as start_time
                FROM sessions s
                JOIN computers c ON s.computer_id = c.id
                JOIN tariffs t ON s.tariff_id = t.id
                WHERE s.status = 'active'
                """
            )
            sessions = []
            for row in cursor.fetchall():
                session = dict(row)
                session['start_time'] = datetime.fromisoformat(session['start_time'].replace('Z', '+00:00'))
                sessions.append(session)
            return sessions

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get a session by its ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM sessions WHERE id = ?
                """,
                (session_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # Tariff management
    def add_tariff(self, name: str, price_per_hour: float, description: str = "") -> int:
        """Add a new tariff."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO tariffs (name, price_per_hour, description) VALUES (?, ?, ?)",
                (name, price_per_hour, description)
            )
            return cursor.lastrowid

    def get_tariffs(self) -> List[Dict[str, Any]]:
        """Get all active tariffs."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tariffs WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]

    # Reports
    def get_daily_report(self, date: datetime) -> Dict[str, Any]:
        """Get daily report for a specific date."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    COALESCE(COUNT(*), 0) as total_sessions,
                    COALESCE(SUM(duration_minutes), 0) as total_minutes,
                    COALESCE(SUM(amount_paid), 0.0) as total_revenue
                FROM sessions
                WHERE DATE(start_time) = DATE(?)
                """,
                (date,)
            )
            return dict(cursor.fetchone())

    def get_computer_usage_report(self, computer_id: int, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get usage report for a specific computer."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    DATE(start_time) as date,
                    COUNT(*) as sessions_count,
                    SUM(duration_minutes) as total_minutes,
                    SUM(amount_paid) as total_revenue
                FROM sessions
                WHERE computer_id = ? AND start_time BETWEEN ? AND ?
                GROUP BY DATE(start_time)
                ORDER BY date
                """,
                (computer_id, start_date, end_date)
            )
            return [dict(row) for row in cursor.fetchall()]

    def remove_computer(self, computer_id: int) -> bool:
        """Remove a computer from the database."""
        with self.get_connection() as conn:
            try:
                # First check if there are any active sessions
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE computer_id = ? AND status = 'active'",
                    (computer_id,)
                )
                if cursor.fetchone()[0] > 0:
                    return False
                
                # Delete the computer
                conn.execute("DELETE FROM computers WHERE id = ?", (computer_id,))
                return True
            except sqlite3.Error:
                return False

    def remove_session(self, session_id: int) -> bool:
        """Remove a session from the database."""
        with self.get_connection() as conn:
            try:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                return True
            except sqlite3.Error:
                return False

    def add_payment(self, session_id: int, amount: float, payment_method: str) -> int:
        """Add a payment record to the payments table."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO payments (session_id, amount, payment_method) VALUES (?, ?, ?)",
                (session_id, amount, payment_method)
            )
            return cursor.lastrowid 