const { addonBuilder } = require('stremio-addon-sdk');
const { imdbToTmdb } = require('./tmdb');
const { getVidZeeStreams, toStremioStreams } = require('./vidzee');

const manifest = {
    id: 'community.flickystream',
    version: '1.0.0',
    name: 'FlickyStream',
    description: 'Stream movies and TV shows via FlickyStream / VidZee. Supports 4K, 1080p, 720p.',
    logo: 'https://flickystream.ru/favicon.ico',
    catalogs: [],
    resources: ['stream'],
    types: ['movie', 'series'],
    idPrefixes: ['tt'],
    behaviorHints: {
        adult: false,
        configurable: false
    }
};

const builder = new addonBuilder(manifest);

builder.defineStreamHandler(async ({ type, id }) => {
    console.log(`[FlickyStream] Stream request: type=${type}, id=${id}`);

    try {
        let tmdbId = null;
        let seasonNum = null;
        let episodeNum = null;

        // Parse the ID - Stremio sends IMDB IDs
        // Movies: "tt1234567"
        // Series: "tt1234567:1:1" (imdbId:season:episode)
        const parts = id.split(':');
        const imdbId = parts[0];

        if (type === 'series' && parts.length >= 3) {
            seasonNum = parseInt(parts[1]);
            episodeNum = parseInt(parts[2]);
        }

        // Convert IMDB ID to TMDB ID
        tmdbId = await imdbToTmdb(imdbId, type);

        if (!tmdbId) {
            console.log(`[FlickyStream] Could not find TMDB ID for ${imdbId}`);
            return { streams: [] };
        }

        console.log(`[FlickyStream] TMDB ID: ${tmdbId} for ${imdbId}`);

        // Fetch streams from VidZee (FlickyStream's backend)
        const vidZeeStreams = await getVidZeeStreams(tmdbId, type, seasonNum, episodeNum);

        if (vidZeeStreams.length === 0) {
            console.log(`[FlickyStream] No streams found for TMDB:${tmdbId}`);
            return { streams: [] };
        }

        // Convert to Stremio format
        const stremioStreams = toStremioStreams(vidZeeStreams);

        console.log(`[FlickyStream] Returning ${stremioStreams.length} streams`);
        return { streams: stremioStreams };

    } catch (err) {
        console.error(`[FlickyStream] Error: ${err.message}`);
        return { streams: [] };
    }
});

module.exports = builder.getInterface();
