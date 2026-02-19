const { serveHTTP } = require('stremio-addon-sdk');
const addonInterface = require('./addon');

const PORT = process.env.PORT || 7000;

serveHTTP(addonInterface, { port: PORT });

console.log(`
╔═══════════════════════════════════════════════════════╗
║           FlickyStream Stremio Addon                  ║
║                                                       ║
║  Addon URL:  http://127.0.0.1:${PORT}/manifest.json       ║
║                                                       ║
║  Install in Stremio:                                  ║
║  1. Open Stremio                                      ║
║  2. Go to Addons (puzzle icon)                        ║
║  3. Enter the Addon URL above                         ║
║                                                       ║
║  Supports: Movies & TV Series                         ║
║  Source: FlickyStream (VidZee)                         ║
║  Quality: 4K / 1080p / 720p / 480p                    ║
╚═══════════════════════════════════════════════════════╝
`);
