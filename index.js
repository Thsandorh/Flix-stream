const express = require('express');
const axios = require('axios');
const { decryptKey, decryptLink } = require('./utils');

const app = express();
const PORT = process.env.PORT || 7000;

const TMDB_TOKEN = process.env.TMDB_TOKEN;

const MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.0.0",
    "name": "FlickyStream Addon (Node)",
    "description": "Stream movies and TV shows from FlickyStream (VidZee).",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": []
};

const SERVERS = [
    {id: "0", name: "Nflix"},
    {id: "1", name: "Duke"},
    {id: "2", name: "Glory"},
    {id: "4", name: "Atlas"},
    {id: "5", name: "Drag"},
    {id: "6", name: "Achilles"},
    {id: "9", name: "Hindi"},
];

async function getTMDBId(imdbId) {
    const url = `https://api.themoviedb.org/3/find/${imdbId}?external_source=imdb_id`;
    try {
        const response = await axios.get(url, {
            headers: { Authorization: `Bearer ${TMDB_TOKEN}` },
            timeout: 5000
        });
        const data = response.data;
        if (data.movie_results && data.movie_results.length > 0) return data.movie_results[0].id;
        if (data.tv_results && data.tv_results.length > 0) return data.tv_results[0].id;
    } catch (e) {
        console.error('TMDB Mapping error:', e.message);
    }
    return null;
}

async function getDecryptionKey() {
    try {
        const response = await axios.get("https://core.vidzee.wtf/api-key", { timeout: 5000 });
        return decryptKey(response.data.trim());
    } catch (e) {
        console.error('API Key fetch error:', e.message);
        return null;
    }
}

async function fetchServerStreams(tmdbId, server, season, episode, decryptionKey) {
    let apiUrl = `https://player.vidzee.wtf/api/server?id=${tmdbId}&sr=${server.id}`;
    if (season && episode) {
        apiUrl += `&ss=${season}&ep=${episode}`;
    }

    try {
        const response = await axios.get(apiUrl, { timeout: 5000 });
        const data = response.data;
        const streams = [];
        if (data.url) {
            for (const u of data.url) {
                const decryptedUrl = decryptLink(u.link, decryptionKey);
                if (decryptedUrl) {
                    streams.push({
                        name: `Flicky - ${server.name}`,
                        title: `${u.lang || 'English'} ${u.message || ''}\n${u.name || ''}`,
                        url: decryptedUrl
                    });
                }
            }
        }
        return streams;
    } catch (e) {
        return [];
    }
}

app.get('/manifest.json', (req, res) => {
    res.json(MANIFEST);
});

app.get('/stream/:type/:id.json', async (req, res) => {
    const { type, id } = req.params;
    const parts = id.split(':');
    const imdbId = parts[0];
    const season = parts[1];
    const episode = parts[2];

    const tmdbId = await getTMDBId(imdbId);
    if (!tmdbId) return res.json({ streams: [] });

    const decryptionKey = await getDecryptionKey();
    if (!decryptionKey) return res.json({ streams: [] });

    const streamPromises = SERVERS.map(server =>
        fetchServerStreams(tmdbId, server, season, episode, decryptionKey)
    );

    const results = await Promise.all(streamPromises);
    const allStreams = results.flat();

    res.json({ streams: allStreams });
});

app.listen(PORT, () => {
    console.log(`Addon running at http://localhost:${PORT}`);
});
