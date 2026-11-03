const $ = (s) => document.querySelector(s);
async function start() {
  try {
    const response = await fetch("/api/connection");
    if (!response.ok) throw Error("Connection information is unavailable.");
    const info = await response.json();
    $("#connection-message").textContent = info.message;
    function operatorInfo(value) {
      if (value.manual_pairing) {
        $("#manual-pairing").hidden = false;
        $("#manual-code").textContent = value.manual_pairing.code;
        $("#manual-code-expiry").textContent = `Single use · expires in ${value.manual_pairing.expires_in} seconds. A new code appears after use or expiry.`;
      }
    }
    operatorInfo(info);
    if (info.manual_pairing) setInterval(async () => {
      try {
        const response = await fetch('/api/connection', {signal:AbortSignal.timeout(3000)});
        if (response.ok) operatorInfo(await response.json());
      } catch { /* Keep the last display, visibly marked unavailable until the next poll. */
        $("#manual-code").textContent = '—';
        $("#manual-code-expiry").textContent = 'Connection lost. Check the desktop window for the current code.';
      }
    }, 1000);
    const select = $("#connection-address");
    for (const url of info.urls) {
      const option = document.createElement("option");
      option.value = url;
      option.textContent = url;
      select.append(option);
    }
    if (!info.urls.length) {
      $("#connection-error").textContent = info.message;
      $(".connect-address-label").hidden = true;
      $(".qr-frame").hidden = true;
      $("#refresh-qr").hidden = true;
      $("#connection-link").hidden = true;
      $("#connection-instructions").textContent = info.lan_enabled ?
        'A tablet address could not be detected. Choose your PC’s LAN address with --lan-host and restart the server.' :
        'This server is available only on this computer. Restart with --host 0.0.0.0 to enable tablet access and its QR.';
      $("#manual-pairing-instructions").textContent = 'This code can be used on the tablet once LAN access is enabled.';
      return;
    }
    async function update() {
      const url = select.value;
      // The visible/manual address never contains a pairing credential.
      $("#connection-link").textContent = url;
      $("#connection-link").href = url;
      if (info.qr_available !== false)
        $("#connection-qr").src = "/qr.svg?url=" + encodeURIComponent(url);
      $("#connection-qr").hidden = false;
      if (!info.pairing_available) {
        $(".qr-frame").hidden = true;
        $("#refresh-qr").disabled = true;
        $("#connection-message").textContent = info.message + " This device is paired. New devices need a QR or code from the server computer.";
      } else {
        try {
          const response = await fetch("/api/pairing", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
          });
          const pair = await response.json();
          if (!response.ok)
            throw Error(pair.error || "Could not create pairing QR");
          $("#connection-qr").src = pair.qr_image;
          $("#connection-message").textContent =
            "Scan this single-use QR or enter the six-digit code on the tablet. Pairing expires after 12 hours or when the server restarts. Use a trusted private LAN; HTTP does not encrypt traffic.";
        } catch (error) {
          $("#connection-error").textContent = error.message;
        }
      }
    }
    select.onchange = update;
    $("#refresh-qr").onclick = update;
    await update();
    $("#connection-qr").onerror = () => {
      $("#connection-error").textContent =
        "QR code unavailable. Open the address on the tablet and enter the six-digit code shown above.";
    };
  } catch (error) {
    $("#connection-error").textContent = error.message;
  }
}
start();
