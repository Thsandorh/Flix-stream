const axios = require('axios');

// Free TMDB API key (v3) - used only for ID conversion
const TMDB_API_KEY = '8d6d91941230817f7807d643736e8a49';
const TMDB_BASE = 'https://api.themoviedb.org/3';

const cache = new Map();

async function imdbToTmdb(imdbId, type) {
    const cacheKey = `${imdbId}_${type}`;
    if (cache.has(cacheKey)) return cache.get(cacheKey);

    try {
        const resp = await axios.get(`${TMDB_BASE}/find/${imdbId}`, {
            params: {
                api_key: TMDB_API_KEY,
                external_source: 'imdb_id'
            },
            timeout: 10000
        });

        let tmdbId = null;

        if (type === 'movie' && resp.data.movie_results && resp.data.movie_results.length > 0) {
            tmdbId = resp.data.movie_results[0].id;
        } else if (type === 'series' && resp.data.tv_results && resp.data.tv_results.length > 0) {
            tmdbId = resp.data.tv_results[0].id;
        }

        if (tmdbId) {
            cache.set(cacheKey, tmdbId);
        }

        return tmdbId;
    } catch (err) {
        console.error(`[TMDB] Failed to convert ${imdbId}: ${err.message}`);
        return null;
    }
}

async function searchTmdb(query, type) {
    try {
        const mediaType = type === 'series' ? 'tv' : 'movie';
        const resp = await axios.get(`${TMDB_BASE}/search/${mediaType}`, {
            params: {
                api_key: TMDB_API_KEY,
                query: query
            },
            timeout: 10000
        });

        if (resp.data.results && resp.data.results.length > 0) {
            return resp.data.results[0].id;
        }
        return null;
    } catch (err) {
        console.error(`[TMDB] Search failed: ${err.message}`);
        return null;
    }
}

module.exports = { imdbToTmdb, searchTmdb };
