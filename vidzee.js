const axios = require('axios');
const CryptoJS = require('crypto-js');

const VIDZEE_API = 'https://player.vidzee.wtf/api/server';
const VIDZEE_REFERER = 'https://player.vidzee.wtf/';
const STREAM_REFERER = 'https://core.vidzee.wtf/';
const SERVER_COUNT = 10;
const REQUEST_TIMEOUT = 8000;

/**
 * Decode encrypted VidZee token
 * Format: base64(iv_base64:cipher_base64)
 * Key: "qrincywincyspider" padded to 32 bytes
 */
function decodeVidZeeToken(encodedToken) {
    try {
        const decoded = Buffer.from(encodedToken, 'base64').toString('utf-8');

        if (decoded.startsWith('http://') || decoded.startsWith('https://')) {
            return decoded;
        }

        const parts = decoded.split(':');
        if (parts.length < 2) return null;

        const ivBase64 = parts[0];
        const cipherBase64 = parts.slice(1).join(':');

        const keyStr = 'qrincywincyspider';
        const keyPadded = keyStr + '\0'.repeat(32 - keyStr.length);

        const key = CryptoJS.enc.Utf8.parse(keyPadded);
        const iv = CryptoJS.enc.Base64.parse(ivBase64);

        const decrypted = CryptoJS.AES.decrypt(
            cipherBase64,
            key,
            {
                iv: iv,
                mode: CryptoJS.mode.CBC,
                padding: CryptoJS.pad.Pkcs7
            }
        );

        const result = decrypted.toString(CryptoJS.enc.Utf8);

        if (result && (result.startsWith('http://') || result.startsWith('https://'))) {
            return result;
        }

        return null;
    } catch (err) {
        return null;
    }
}

/**
 * Parse quality from URL or filename
 */
function parseQuality(url, serverNum) {
    if (!url) return `Server ${serverNum}`;
    const lower = url.toLowerCase();
    if (lower.includes('2160') || lower.includes('4k')) return '4K';
    if (lower.includes('1080')) return '1080p';
    if (lower.includes('720')) return '720p';
    if (lower.includes('480')) return '480p';
    if (lower.includes('360')) return '360p';
    return `Server ${serverNum}`;
}

/**
 * Parse language from URL or filename
 */
function parseLanguage(url) {
    if (!url) return '';
    const lower = url.toLowerCase();
    if (lower.includes('hun') || lower.includes('magyar')) return ' HUN';
    if (lower.includes('eng')) return ' ENG';
    if (lower.includes('multi')) return ' MULTI';
    return '';
}

/**
 * Fetch streams from a single VidZee server
 */
async function fetchServer(tmdbId, mediaType, serverNum, seasonNum, episodeNum) {
    try {
        let url = `${VIDZEE_API}?id=${tmdbId}&sr=${serverNum}`;
        if (mediaType === 'tv' && seasonNum && episodeNum) {
            url += `&ss=${seasonNum}&ep=${episodeNum}`;
        }

        const embedType = mediaType === 'tv' ? 'tv' : 'movie';
        let refererUrl = `https://player.vidzee.wtf/embed/${embedType}/${tmdbId}`;
        if (mediaType === 'tv' && seasonNum && episodeNum) {
            refererUrl += `/${seasonNum}/${episodeNum}`;
        }

        const resp = await axios.get(url, {
            headers: {
                'Referer': refererUrl,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://player.vidzee.wtf'
            },
            timeout: REQUEST_TIMEOUT
        });

        const data = resp.data;
        if (!data) return [];

        const streams = [];

        // Handle "url" field (array of stream objects)
        if (data.url && Array.isArray(data.url)) {
            for (const item of data.url) {
                let streamUrl = item.link || item.url || item.file || item;
                if (typeof streamUrl === 'string') {
                    // Try decoding if it looks encrypted
                    const decoded = decodeVidZeeToken(streamUrl);
                    if (decoded) streamUrl = decoded;

                    const quality = item.quality || item.label || parseQuality(streamUrl, serverNum);
                    const lang = item.lang || parseLanguage(streamUrl);

                    streams.push({
                        url: streamUrl,
                        quality: quality,
                        lang: lang,
                        server: serverNum
                    });
                }
            }
        }

        // Handle "link" field (single stream)
        if (data.link) {
            let streamUrl = data.link;
            if (typeof streamUrl === 'string') {
                const decoded = decodeVidZeeToken(streamUrl);
                if (decoded) streamUrl = decoded;

                streams.push({
                    url: streamUrl,
                    quality: data.quality || parseQuality(streamUrl, serverNum),
                    lang: data.lang || parseLanguage(streamUrl),
                    server: serverNum
                });
            }
        }

        // Handle direct "file" or "source" field
        if (data.file || data.source) {
            let streamUrl = data.file || data.source;
            if (typeof streamUrl === 'string') {
                const decoded = decodeVidZeeToken(streamUrl);
                if (decoded) streamUrl = decoded;

                streams.push({
                    url: streamUrl,
                    quality: data.quality || parseQuality(streamUrl, serverNum),
                    lang: parseLanguage(streamUrl),
                    server: serverNum
                });
            }
        }

        // Handle encrypted data field
        if (data.data && typeof data.data === 'string') {
            const decoded = decodeVidZeeToken(data.data);
            if (decoded) {
                streams.push({
                    url: decoded,
                    quality: parseQuality(decoded, serverNum),
                    lang: parseLanguage(decoded),
                    server: serverNum
                });
            }
        }

        return streams;
    } catch (err) {
        // Server might not respond or have content - this is normal
        return [];
    }
}

/**
 * Get all VidZee streams for a given TMDB ID
 */
async function getVidZeeStreams(tmdbId, mediaType, seasonNum, episodeNum) {
    const type = mediaType === 'series' ? 'tv' : 'movie';

    console.log(`[VidZee] Fetching streams for TMDB:${tmdbId} type:${type}${seasonNum ? ` S${seasonNum}E${episodeNum}` : ''}`);

    // Query all servers in parallel
    const serverPromises = [];
    for (let sr = 1; sr <= SERVER_COUNT; sr++) {
        serverPromises.push(fetchServer(tmdbId, type, sr, seasonNum, episodeNum));
    }

    const results = await Promise.allSettled(serverPromises);
    const allStreams = [];
    const seenUrls = new Set();

    for (const result of results) {
        if (result.status === 'fulfilled' && result.value) {
            for (const stream of result.value) {
                if (stream.url && !seenUrls.has(stream.url)) {
                    seenUrls.add(stream.url);
                    allStreams.push(stream);
                }
            }
        }
    }

    console.log(`[VidZee] Found ${allStreams.length} unique streams`);
    return allStreams;
}

/**
 * Convert VidZee streams to Stremio stream format
 */
function toStremioStreams(vidZeeStreams) {
    return vidZeeStreams.map(stream => {
        const title = `FlickyStream | ${stream.quality}${stream.lang} | Server ${stream.server}`;

        const stremioStream = {
            name: 'FlickyStream',
            title: title,
            behaviorHints: {
                notWebReady: true,
                bingeGroup: 'flickystream'
            }
        };

        // Determine stream type based on URL
        if (stream.url.includes('.m3u8')) {
            stremioStream.url = stream.url;
            stremioStream.behaviorHints.proxyHeaders = {
                request: {
                    'Referer': STREAM_REFERER,
                    'Origin': STREAM_REFERER,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            };
        } else if (stream.url.includes('.mp4') || stream.url.includes('.mkv') || stream.url.includes('.avi')) {
            stremioStream.url = stream.url;
            stremioStream.behaviorHints.proxyHeaders = {
                request: {
                    'Referer': STREAM_REFERER,
                    'Origin': STREAM_REFERER,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            };
        } else {
            // Generic URL - might be a redirect or direct stream
            stremioStream.url = stream.url;
            stremioStream.behaviorHints.proxyHeaders = {
                request: {
                    'Referer': STREAM_REFERER,
                    'Origin': STREAM_REFERER,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            };
        }

        return stremioStream;
    });
}

module.exports = { getVidZeeStreams, toStremioStreams, decodeVidZeeToken };
