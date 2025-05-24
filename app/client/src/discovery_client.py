import socket
import json
import threading
import logging
import time
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import netifaces

logger = logging.getLogger(__name__)

@dataclass
class ServerInfo:
    name: str
    port: int
    version: str
    status: str
    last_seen: datetime
    address: str
    features: List[str]
    latency: Optional[float] = None

class DiscoveryClient:
    def __init__(self, broadcast_port: int = 5000):
        self.broadcast_port = broadcast_port
        self.running = False
        self.discovery_thread: Optional[threading.Thread] = None
        self.servers: Dict[str, ServerInfo] = {}
        self.on_server_found: Optional[Callable[[ServerInfo], None]] = None
        self.on_server_lost: Optional[Callable[[ServerInfo], None]] = None
        self.server_timeout = 15  # Seconds before considering a server lost
        self.required_features: Set[str] = set()
        self.version_constraint: Optional[str] = None
        self.latency_check_interval = 30  # Check latency every 30 seconds
        self.latency_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the discovery client."""
        if self.running:
            return

        self.running = True
        self.discovery_thread = threading.Thread(target=self._discovery_loop)
        self.discovery_thread.daemon = True
        self.discovery_thread.start()
        
        # Start server timeout checker
        self.timeout_thread = threading.Thread(target=self._check_timeouts)
        self.timeout_thread.daemon = True
        self.timeout_thread.start()
        
        # Start latency checker
        self.latency_thread = threading.Thread(target=self._check_latency)
        self.latency_thread.daemon = True
        self.latency_thread.start()
        
        logger.info("Discovery client started")

    def stop(self):
        """Stop the discovery client."""
        self.running = False
        if self.discovery_thread:
            self.discovery_thread.join(timeout=1.0)
        if self.timeout_thread:
            self.timeout_thread.join(timeout=1.0)
        if self.latency_thread:
            self.latency_thread.join(timeout=1.0)
        logger.info("Discovery client stopped")

    def _discovery_loop(self):
        """Main discovery loop."""
        try:
            # Create UDP socket for receiving broadcasts
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', self.broadcast_port))
            
            while self.running:
                try:
                    # Receive server broadcast
                    data, addr = sock.recvfrom(1024)
                    server_info = json.loads(data.decode())
                    
                    # Check if server meets requirements
                    if self._meets_requirements(server_info):
                        # Update server information
                        self._update_server_info(server_info, addr[0])
                except Exception as e:
                    logger.error(f"Error in discovery loop: {e}")
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Error setting up discovery socket: {e}")
        finally:
            try:
                sock.close()
            except:
                pass

    def _meets_requirements(self, info: dict) -> bool:
        """Check if server meets the requirements."""
        # Check version constraint
        if self.version_constraint:
            try:
                from packaging import version
                if not version.parse(info['version']) >= version.parse(self.version_constraint):
                    return False
            except Exception as e:
                logger.error(f"Error checking version constraint: {e}")
                return False

        # Check required features
        if self.required_features:
            server_features = set(info.get('features', []))
            if not self.required_features.issubset(server_features):
                return False

        return True

    def _update_server_info(self, info: dict, address: str):
        """Update information about a discovered server."""
        server_id = f"{address}:{info['port']}"
        now = datetime.now()
        
        # Check if this is a new server
        is_new = server_id not in self.servers
        
        # Update server information
        self.servers[server_id] = ServerInfo(
            name=info['name'],
            port=info['port'],
            version=info['version'],
            status=info['status'],
            last_seen=now,
            address=address,
            features=info.get('features', []),
            latency=None
        )
        
        # Notify about new server
        if is_new and self.on_server_found:
            self.on_server_found(self.servers[server_id])
            
        logger.debug(f"Updated server information for {server_id}")

    def _check_timeouts(self):
        """Check for timed-out servers."""
        while self.running:
            try:
                now = datetime.now()
                timed_out = []
                
                # Check each server
                for server_id, server in self.servers.items():
                    if now - server.last_seen > timedelta(seconds=self.server_timeout):
                        timed_out.append(server_id)
                        if self.on_server_lost:
                            self.on_server_lost(server)
                
                # Remove timed-out servers
                for server_id in timed_out:
                    del self.servers[server_id]
                    logger.info(f"Server {server_id} timed out")
                
                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Error checking server timeouts: {e}")
                time.sleep(1)

    def _check_latency(self):
        """Check latency to all servers periodically."""
        while self.running:
            try:
                for server_id, server in self.servers.items():
                    try:
                        start_time = time.time()
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1.0)
                        sock.connect((server.address, server.port))
                        sock.close()
                        latency = (time.time() - start_time) * 1000  # Convert to milliseconds
                        server.latency = latency
                        logger.debug(f"Latency to {server_id}: {latency:.2f}ms")
                    except Exception as e:
                        logger.debug(f"Error checking latency to {server_id}: {e}")
                        server.latency = None
                time.sleep(self.latency_check_interval)
            except Exception as e:
                logger.error(f"Error in latency check loop: {e}")
                time.sleep(1)

    def get_available_servers(self) -> List[ServerInfo]:
        """Get list of currently available servers."""
        return list(self.servers.values())

    def get_best_server(self) -> Optional[ServerInfo]:
        """Get the best available server based on latency and status."""
        available_servers = [s for s in self.servers.values() 
                           if s.status == 'running' and s.latency is not None]
        if not available_servers:
            return None
        return min(available_servers, key=lambda s: s.latency)

    def set_server_found_callback(self, callback: Callable[[ServerInfo], None]):
        """Set callback for when a new server is discovered."""
        self.on_server_found = callback

    def set_server_lost_callback(self, callback: Callable[[ServerInfo], None]):
        """Set callback for when a server is lost."""
        self.on_server_lost = callback

    def set_required_features(self, features: List[str]):
        """Set required features for servers."""
        self.required_features = set(features)

    def set_version_constraint(self, version: str):
        """Set minimum required server version."""
        self.version_constraint = version 