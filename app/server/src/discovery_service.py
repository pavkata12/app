import socket
import json
import threading
import logging
import time
import netifaces
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class NetworkInterface:
    name: str
    ip: str
    broadcast: str
    netmask: str

class DiscoveryService:
    def __init__(self, port: int = 5000, broadcast_interval: int = 5):
        self.port = port
        self.broadcast_interval = broadcast_interval
        self.running = False
        self.broadcast_thread: Optional[threading.Thread] = None
        self.server_info: Dict = {
            'name': 'Gaming Center Server',
            'port': 5001,  # Main server port
            'version': '1.0.0',
            'status': 'running',
            'features': ['session_management', 'payment_processing', 'remote_control']
        }
        self.network_interfaces: List[NetworkInterface] = []
        self._discover_network_interfaces()

    def _discover_network_interfaces(self):
        """Discover available network interfaces for broadcasting."""
        try:
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr and 'broadcast' in addr and 'netmask' in addr:
                            self.network_interfaces.append(NetworkInterface(
                                name=interface,
                                ip=addr['addr'],
                                broadcast=addr['broadcast'],
                                netmask=addr['netmask']
                            ))
            logger.info(f"Discovered {len(self.network_interfaces)} network interfaces")
        except Exception as e:
            logger.error(f"Error discovering network interfaces: {e}")

    def start(self):
        """Start the discovery service."""
        if self.running:
            return

        self.running = True
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop)
        self.broadcast_thread.daemon = True
        self.broadcast_thread.start()
        logger.info("Discovery service started")

    def stop(self):
        """Stop the discovery service."""
        self.running = False
        if self.broadcast_thread:
            self.broadcast_thread.join(timeout=1.0)
        logger.info("Discovery service stopped")

    def _broadcast_loop(self):
        """Main broadcast loop."""
        sockets = []
        try:
            # Create UDP sockets for each network interface
            for interface in self.network_interfaces:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((interface.ip, 0))  # Bind to specific interface
                    sockets.append((sock, interface))
                    logger.info(f"Created broadcast socket for interface {interface.name}")
                except Exception as e:
                    logger.error(f"Error creating socket for interface {interface.name}: {e}")

            if not sockets:
                logger.error("No valid broadcast interfaces found")
                return

            while self.running:
                try:
                    # Broadcast server information on all interfaces
                    message = json.dumps(self.server_info).encode()
                    for sock, interface in sockets:
                        try:
                            sock.sendto(message, (interface.broadcast, self.port))
                            logger.debug(f"Broadcast sent on interface {interface.name}")
                        except Exception as e:
                            logger.error(f"Error broadcasting on interface {interface.name}: {e}")
                    time.sleep(self.broadcast_interval)
                except Exception as e:
                    logger.error(f"Error in broadcast loop: {e}")
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Error setting up broadcast sockets: {e}")
        finally:
            # Clean up sockets
            for sock, _ in sockets:
                try:
                    sock.close()
                except:
                    pass

    def update_server_info(self, **kwargs):
        """Update server information."""
        self.server_info.update(kwargs)
        logger.debug(f"Updated server information: {self.server_info}")

    def get_server_info(self) -> Dict:
        """Get current server information."""
        return self.server_info.copy()

    def get_network_interfaces(self) -> List[NetworkInterface]:
        """Get list of available network interfaces."""
        return self.network_interfaces.copy() 