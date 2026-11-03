"""Local-only connection information and QR generation. No external QR service."""
import io
import ipaddress
import re
import socket


def connection_info(host, port, lan_host=None, scheme='http'):
    loopback = host in ('127.0.0.1', 'localhost', '::1')
    addresses = []
    if lan_host:
        if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?', lan_host):
            raise ValueError('LAN host must be an IPv4 address or DNS hostname, without a scheme or port')
        addresses.append(lan_host)
    elif host not in ('0.0.0.0', '::') and not loopback:
        addresses.append(host)
    elif not loopback:
        # A Linux hostname often resolves only to 127.0.1.1. Ask the routing
        # table which local address it would use; UDP connect sends no packet.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                route.connect(('192.0.2.1', 9))
                ip = ipaddress.ip_address(route.getsockname()[0])
                if not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified:
                    addresses.append(str(ip))
        except OSError:
            pass
        try:
            for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = ipaddress.ip_address(result[4][0])
                if not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified:
                    addresses.append(str(ip))
        except OSError:
            pass
    addresses = list(dict.fromkeys(addresses))
    urls = [f'{scheme}://{address}:{port}/' for address in addresses]
    return dict(urls=urls, local_url=f'{scheme}://127.0.0.1:{port}/', lan_enabled=not loopback,
                message='Choose the network shared with your tablet.' if urls else
                'No LAN address detected. Restart with --lan-host YOUR-COMPUTER-IP.' if not loopback else
                'This server listens on localhost only. Restart with --host 0.0.0.0 for tablet access.')


def qr_svg(url):
    import qrcode
    from qrcode.image.svg import SvgPathImage
    image = qrcode.make(url, image_factory=SvgPathImage, border=4, box_size=8)
    output = io.BytesIO()
    image.save(output)
    # White background is important for camera scanning in the dark dashboard.
    return output.getvalue().replace(b'<svg ', b'<svg style="background:white" ', 1)
