import os


# Config
# For a production addon, these should be moved to environment variables.
TMDB_TOKEN = os.environ.get(
    "TMDB_TOKEN",
    "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0YzY4ZTRjYjBhMDM4OTk0MTliNmVmYTZiOGJjOGJiZSIsIm5iZiI6MTcyNzUwNjM2NS40NDQxNjUsInN1YiI6IjY2NWQ5YmMwYTVlMDU0MzUwMTQ5MWUwNSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.8OL7WQIZGWr9tRfmSkRFIsaf1Wy0ksrOGDCB4KcocW4",
)
MASTER_KEY = "b3f2a9d4c6e1f8a7b"

MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.1.1",
    "name": "Flix-Streams",
    "description": "Stream movies, series, anime, and live TV with provider controls and Wyzie subtitle integration.",
    "logo": "/static/icon.png",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt", "tmdb", "aniways", "kitsu", "famelack"],
    "catalogs": [],
    "behaviorHints": {
        "configurable": True,
        "configurationRequired": False,
    },
}

SERVERS = [
    {"id": "1", "name": "Duke"},
    {"id": "2", "name": "Glory"},
    {"id": "4", "name": "Atlas"},
    {"id": "5", "name": "Drag"},
    {"id": "6", "name": "Achilles"},
    {"id": "9", "name": "Hindi"},
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://player.vidzee.wtf/",
    "Origin": "https://player.vidzee.wtf",
}

AUTOEMBED_SERVERS = [
    {"id": "2", "name": "Glory"},
    {"id": "3", "name": "Server 3"},
    {"id": "7", "name": "Server 7"},
    {"id": "9", "name": "Hindi"},
]

AUTOEMBED_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": "https://test.autoembed.cc/",
    "Origin": "https://test.autoembed.cc",
}

VIXSRC_BASE_URL = "https://vixsrc.to"
VIXSRC_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": f"{VIXSRC_BASE_URL}/",
    "Origin": VIXSRC_BASE_URL,
}

ANIWAYS_API_BASE = "https://api.aniways.xyz"
ANIWAYS_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": "https://aniways.xyz/",
    "Origin": "https://aniways.xyz",
}
KITSU_API_BASE = "https://kitsu.io/api/edge"
WYZIE_API_BASE = "https://sub.wyzie.ru"
WYZIE_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": f"{WYZIE_API_BASE}/",
    "Origin": WYZIE_API_BASE,
}

PROVIDER_CACHE_TTL = int(os.environ.get("PROVIDER_CACHE_TTL", "45"))
PROVIDER_CACHE_MAXSIZE = int(os.environ.get("PROVIDER_CACHE_MAXSIZE", "2048"))

LANG_MAP = {
    "English": "eng",
    "French": "fre",
    "German": "ger",
    "Spanish": "spa",
    "Italian": "ita",
    "Portuguese": "por",
    "Portuguese (BR)": "pob",
    "Hungarian": "hun",
    "Russian": "rus",
    "Ukrainian": "ukr",
    "Dutch": "nld",
    "Polish": "pol",
    "Romanian": "rum",
    "Czech": "cze",
    "Greek": "gre",
    "Turkish": "tur",
    "Arabic": "ara",
    "Hebrew": "heb",
    "Japanese": "jpn",
    "Korean": "kor",
    "Chinese": "chi",
    "Chinese (traditional)": "chi",
    "Vietnamese": "vie",
    "Thai": "tha",
    "Indonesian": "ind",
    "Swedish": "swe",
    "Norwegian": "nor",
    "Danish": "dan",
    "Finnish": "fin",
    "Slovak": "slo",
    "Slovenian": "slv",
    "Croatian": "hrv",
    "Serbian": "srp",
    "Bulgarian": "bul",
    "Estonian": "est",
    "Latvian": "lav",
    "Lithuanian": "lit",
    "Malay": "may",
    "Persian": "per",
    "Albanian": "sqi",
    "Macedonian": "mkd",
    "Bosnian": "bos",
}
