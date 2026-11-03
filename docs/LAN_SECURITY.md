# LAN access and pairing

iR-Board is intended for a trusted private LAN, not public Internet exposure. HTTP is not encrypted. Pairing controls access to the dashboard and its commands; it does not encrypt traffic or protect against an attacker monitoring the same network.

Remote devices must pair **before reading the dashboard, telemetry or settings, or sending PIT commands**. Unpaired browsers see only a minimal pairing screen. On the computer running iR-Board, open `/connect` or use the desktop window. Scan its QR or enter the displayed six-digit numeric code on the tablet. Codes are single-use and valid for five minutes. The numeric code refreshes automatically after use or expiry. Pairing authorizes that browser for 12 hours or until the server restarts.

The QR credential is in a URL fragment, not a query string. The pairing screen removes it from the address bar before exchanging it. Paired sessions use an HttpOnly, SameSite=Strict cookie. A QR link or six-digit code grants access to whoever redeems it first; do not post it publicly. Refresh QR for another device. The operator's numeric code is never included in responses to remote devices, including already paired devices.

Only the computer running the server can create or view pairing codes. Local access uses loopback or the computer's own interface address and does not require pairing. Spoofed `X-Forwarded-For` and bearer-token headers cannot grant access. The old optional manual access-token configuration has been removed.

Codes are redeemed atomically and guesses are limited to ten attempts per client per minute, with a further global limit of thirty numeric attempts per minute. Sessions and QR credentials are held as hashes in memory; the current numeric code is held in memory so the local operator can see it. Sessions are not carried across server restarts. Expired sessions return the browser to the pairing screen.

The server rejects unknown Host headers, cross-origin command requests and non-JSON bodies. This prevents browser drive-by requests and DNS rebinding from granting pit access. Use the detected LAN IP or `--lan-host` for an intentional DNS alias. The server is a small direct LAN service, not an automatically trusted reverse-proxy endpoint.

Connection handlers have idle timeouts and a 32-thread bound. There are no public file-upload, shell-execution, port-forwarding or remote-update endpoints. SDK strings are escaped in the UI, static routes are explicit and responses use a restrictive content policy, no-store caching and no-referrer. Request targets, cookies, pairing codes and bearer headers are not written to application logs.

To revoke all device sessions, restart iR-Board. Do not expose the HTTP service to the Internet. HTTPS certificate generation, tunnels and SimHub integration are not included in this release.

The desktop launcher offers an explicit **Allow tablet access through Windows Firewall** button. Only its short-lived rule helper requests administrator elevation. The rule allows inbound TCP 8000 for the current executable on Private networks from LocalSubnet. It does not disable the firewall, change the network category or add antivirus exclusions. Re-run setup if the executable path changes. To revoke it, delete the rule named **iR-Board tablet access (Private LAN)** in Windows Defender Firewall with Advanced Security.
