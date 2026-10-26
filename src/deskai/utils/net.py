"""
Race-Free Ephemeral Loopback Socket Allocator & Host Verification Helpers.
"""
import socket


def bind_ephemeral_loopback_socket() -> tuple[socket.socket, int]:
    """
    Binds a listening loopback socket on an ephemeral port.
    Returns the open socket object and the allocated port number.
    The socket remains bound and open so another process cannot steal the port.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    return sock, port


def is_valid_loopback_host(host_header: str | None, port: int) -> bool:
    """
    Validates Host header strictly against 127.0.0.1:{port} or localhost:{port}.
    Prevents DNS rebinding and cross-site request attacks.
    """
    if not host_header:
        return False
    return host_header in [f"127.0.0.1:{port}", f"localhost:{port}"]
