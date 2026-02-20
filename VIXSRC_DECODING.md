# VixSrc.to API Decoding Report

## Summary
The `vixsrc.to` streaming API is protected by a multi-layered obfuscation system known as **ZFG / Jomtingi**. The site does not expose a public API endpoint for video sources. Instead, it relies on client-side JavaScript to dynamically generate requests, verify the browser environment (e.g., checking for sandboxing), and load content via an ad network integration.

## Decryption Logic
The core configuration is hidden in a massive JavaScript object literal using a custom **ROT14** cipher.

- **Cipher:** ROT14 (Shift +14) on `[a-z]` and `[A-Z]`.
- **Signature:** The object is identified by the key `x` with value `AzOxuow` (decodes to `OnClick`).

## Extracted Logic
The provided `vixsrc_integration.py` script performs the following:
1.  Fetches the embed page.
2.  Locates the obfuscated configuration object.
3.  Decodes all keys and values using ROT14.
4.  Constructs the **Ad Verification URL** (e.g., `https://jomtingi.net/apu.php?zoneid=...`).

## Limitations
A direct `.m3u8` link **cannot** be extracted purely via Python/Requests for the following reasons:
1.  **Dynamic Domain Generation:** The script generates a random domain (using `Math.random()`) to fetch the next stage script (`tag.min.js`).
2.  **Browser Verification:** The script explicitly checks for "Sandboxed iframe" and other browser features. If these checks fail (which they do in a simple HTTP client), the player loading sequence is aborted.
3.  **Ad Network Gating:** The content delivery appears to be tied to the successful execution of the `jomtingi.net` script, which is currently blocked or requires a specific Referer/Session.

## Recommendation
To fully integrate `vixsrc.to` into a scraper:
1.  Use **Playwright** or **Puppeteer** to render the page.
2.  The browser will automatically handle the ROT14 decoding and script execution.
3.  Intercept network traffic (XHR/Fetch) matching `.m3u8` or the ad verification URL identified by the `vixsrc_integration.py` tool.

## Tool Usage
```bash
python3 vixsrc_integration.py [TMDB_ID]
```
Example:
```bash
python3 vixsrc_integration.py 27205
```
This will output the decoded configuration and the next-step URL for analysis.
