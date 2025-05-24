import socket
import json
import threading
from typing import Dict, Any, Callable, Optional, Iterator
from zeroconf import ServiceBrowser, Zeroconf, ServiceListener
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkManager(ServiceListener):
    def __init__(self, port: int = 5000):
        self.port = port
        self.clients: Dict[str, socket.socket] = {}
        self.client_status: Dict[str, str] = {}  # Track client status
        self.message_handlers: Dict[str, Callable] = {}
        self.zeroconf = Zeroconf()
        self._setup_service_discovery()
        self._start_server()

    def __iter__(self) -> Iterator[str]:
        """Make the class iterable by yielding service names."""
        yield self.service_name

    def _setup_service_discovery(self) -> None:
        """Setup Zeroconf service discovery."""
        self.service_name = "_gamingcenter._tcp.local."
        self.browser = ServiceBrowser(self.zeroconf, self.service_name, self)

    def _start_server(self) -> None:
        """Start the TCP server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(5)
        
        # Start accepting connections in a separate thread
        threading.Thread(target=self._accept_connections, daemon=True).start()

    def _accept_connections(self) -> None:
        """Accept incoming client connections."""
        while True:
            try:
                if not hasattr(self, 'server_socket') or self.server_socket._closed:
                    break
                    
                client_socket, address = self.server_socket.accept()
                client_ip = address[0]
                logger.info(f"New client connected from {client_ip}")
                
                # Start a new thread to handle client communication
                threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_ip),
                    daemon=True
                ).start()
            except Exception as e:
                if not hasattr(self, 'server_socket') or self.server_socket._closed:
                    break
                logger.error(f"Error accepting connection: {e}")
                time.sleep(1)  # Add delay to prevent CPU spinning

    def _handle_client(self, client_socket: socket.socket, client_ip: str) -> None:
        """Handle communication with a client."""
        try:
            self.clients[client_ip] = client_socket
            self.client_status[client_ip] = "online"
            logger.info(f"Client {client_ip} status: online")
            
            while True:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    
                    message = json.loads(data.decode('utf-8'))
                    self._process_message(message, client_ip)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from client {client_ip}")
                    break
                except ConnectionResetError:
                    logger.error(f"Connection reset by client {client_ip}")
                    break
                except Exception as e:
                    logger.error(f"Error handling client {client_ip}: {e}")
                    break
        except Exception as e:
            logger.error(f"Error in client handler for {client_ip}: {e}")
        finally:
            self._remove_client(client_ip)

    def _process_message(self, message: Dict[str, Any], client_ip: str) -> None:
        """Process incoming messages from clients."""
        message_type = message.get('type')
        if message_type in self.message_handlers:
            try:
                self.message_handlers[message_type](message, client_ip)
            except Exception as e:
                logger.error(f"Error processing message {message_type}: {e}")

    def _remove_client(self, client_ip: str) -> None:
        """Remove a disconnected client."""
        if client_ip in self.clients:
            try:
                self.clients[client_ip].close()
            except:
                pass
            del self.clients[client_ip]
            self.client_status[client_ip] = "offline"
            logger.info(f"Client {client_ip} status: offline")

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self.message_handlers[message_type] = handler

    def send_message(self, client_ip: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific client."""
        if client_ip not in self.clients:
            logger.warning(f"Client {client_ip} not connected")
            return False
        
        try:
            self.clients[client_ip].sendall(
                (json.dumps(message) + '\n').encode('utf-8')
            )
            return True
        except Exception as e:
            logger.error(f"Error sending message to {client_ip}: {e}")
            self._remove_client(client_ip)
            return False

    def broadcast_message(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        for client_ip in list(self.clients.keys()):
            self.send_message(client_ip, message)

    def get_connected_clients(self) -> list:
        """Get list of connected client IPs."""
        return list(self.clients.keys())

    def close(self) -> None:
        """Close all connections and cleanup."""
        try:
            for client_ip in list(self.clients.keys()):
                self._remove_client(client_ip)
            if hasattr(self, 'server_socket'):
                self.server_socket.close()
            if hasattr(self, 'zeroconf'):
                self.zeroconf.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_client_status(self, client_ip: str) -> str:
        """Get the status of a client."""
        return self.client_status.get(client_ip, "offline")

    # ServiceListener interface implementation
    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        """Handle service addition."""
        info = zeroconf.get_service_info(type, name)
        if info:
            logger.info(f"Service added: {name}")

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        """Handle service removal."""
        logger.info(f"Service removed: {name}")

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        """Handle service update."""
        info = zeroconf.get_service_info(type, name)
        if info:
            logger.info(f"Service updated: {name}") 