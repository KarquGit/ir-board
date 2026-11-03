# Windows release trust and antivirus

iR-Board does not disable antivirus, add exclusions, hide processes, install a driver, inject code into the game or require administrator privileges for normal operation. The optional Private-LAN firewall helper requests elevation for its rule change only. It reads the simulator's documented shared-memory SDK and sends explicit pit-service broadcasts only after authorization.

No implementation can guarantee that every antivirus or SmartScreen version will accept a new binary. Code-signing proves publisher identity and file integrity; it does not certify that code is harmless or create instant reputation.

## Packaging and publication policy

- The application uses PyInstaller **one-directory** packaging, without UPX, obfuscation or per-launch unpacking into a temporary executable directory.
- The launcher carries stable product/file version metadata and an **asInvoker** Windows manifest. The installer runs per user with `PrivilegesRequired=lowest`.
- GitHub actions are pinned to exact commit hashes. The build job cannot edit repository contents; publication has a separate minimal job.
- Runtime requirements and build tools are version-pinned. `pip-audit` checks runtime dependency advisories before packaging.
- The application and installer are currently unsigned. Windows may show an unknown-publisher or SmartScreen warning.
- The release includes the final installer SHA-256.

A checksum protects against file corruption only when obtained from a trusted source; it is not a substitute for a valid publisher signature. Pipeline changes do not retroactively sign previously published files.

## If a vendor reports a detection

Stop distributing the affected binary until the finding is investigated. Check the build provenance, dependencies and installer checksum. A verified false positive can be submitted by the publisher to the security vendor's official review process. Do not ask users to disable protection or create exclusions.

## Automatic updates

The packaged app records its originating GitHub repository and release tag during the build. At startup and every six hours it checks that repository's public Releases over HTTPS. Stable installations select only newer stable versions; preview installations can also receive newer previews. It downloads only the expected Windows setup filename and accompanying SHA-256 file from that same repository and tag. Missing assets, invalid checksums, unsupported tags and oversized downloads are rejected. The checksum is checked again immediately before starting setup.

Downloads are automatic; installation uses the normal interactive setup after the user agrees to close the application. The updater never silently interrupts telemetry or bypasses UAC, antivirus or SmartScreen. The cache stays under the legacy user-data directory. A SHA-256 file from the same trusted repository protects integrity, not against a compromised publisher account; unsigned updates retain their unknown-publisher limitation. Updates require public accessible release assets and Internet access. No GitHub token is bundled.
