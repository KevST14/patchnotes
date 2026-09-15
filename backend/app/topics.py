"""Rule-based topic tagging.

Each topic is a list of keyword patterns matched on word boundaries. A hit in
the headline or in the source's own tags counts double a hit in the summary,
and a story needs a score of at least 2 for a topic to stick — so one passing
mention deep in a summary doesn't tag a story. Deterministic and explainable,
which matters more here than squeezing out the last bit of accuracy.
"""

import re

TOPICS = [
    {
        "id": "ai",
        "label": "AI",
        "keywords": [
            "ai", "a.i.", "artificial intelligence", "llm", "llms", "gpt", r"gpt-\w+", "chatgpt",
            "openai", "anthropic", "claude", "gemini", "copilot", "machine learning", "deep learning",
            "neural", "deepmind", "mistral", "llama", "deepseek", "hugging face", "huggingface",
            "chatbot", "chatbots", "genai", "generative", "midjourney", "sora", "grok", "xai",
            "inference", "transformer", "transformers", "agentic", "ai agent", "ai agents",
            "model weights", "fine-tuning", "fine-tune", "rag", "embeddings", "superintelligence",
            "agi", "perplexity", "qwen", "codex", "mcp", r"sonnet \d(?:\.\d)?", r"opus \d(?:\.\d)?",
            "vibe coding", "vibe-coded", "vibe coded", "ollama", "ai model", "ai models", "ai-generated",
            "ai-powered", "nanochat", "language model", "language models", "openai's", "anthropic's",
        ],
    },
    {
        "id": "security",
        "label": "Security",
        "keywords": [
            "security", "vulnerability", "vulnerabilities", "exploit", "exploited", "exploits",
            r"cve-\d+-\d+", "cve", "ransomware", "malware", "breach", "breached", "data breach",
            "hack", "hacks", "hacked", "hacker", "hackers", "hacking", "phishing", "zero-day", "0-day",
            "backdoor", "spyware", "botnet", "ddos", "infostealer", "stealer", "cisa", "patch tuesday",
            "supply chain attack", "leaked", "leak", "leaks", "attackers", "threat actor", "threat actors",
            "cybersecurity", "cyberattack", "cyber", "encryption", "passkey", "passkeys", "password",
            "passwords", "2fa", "mfa", "authentication", "scam", "scammers", "fraud", "surveillance",
        ],
    },
    {
        "id": "dev",
        "label": "Dev & Open Source",
        "keywords": [
            "programming", "programmer", "programmers", "developer", "developers", "open source",
            "open-source", "github", "gitlab", "git", "rust", "python", "javascript", "typescript",
            "golang", "compiler", "compilers", "kernel", "linux", "api", "apis", "database",
            "databases", "postgres", "postgresql", "sqlite", "mysql", "framework", "react", "vue",
            "svelte", "node.js", "nodejs", "deno", "bun", "npm", "pypi", "crates.io", "c\\+\\+",
            "zig", "haskell", "ocaml", "elixir", "erlang", "lisp", "clojure", "java", "kotlin",
            "swift", "wasm", "webassembly", "llvm", "gcc", "docker", "kubernetes", "terminal",
            "emacs", "vim", "neovim", "vscode", "vs code", "ide", "sdk", "library", "refactor",
            "debugging", "debugger", "algorithm", "algorithms", "software engineering", "code",
            "coding", "devops", "ci", "unix", "bsd", "freebsd", "openbsd", "shell", "bash",
            "regex", "http", "css", "html", "browser engine", "lisp",
        ],
        # Lobsters/GitHub tags that mean "this is a dev story".
        "tags": [
            "programming", "rust", "python", "javascript", "go", "c", "c++", "compilers", "linux",
            "unix", "databases", "devops", "release", "plt", "web", "vcs", "practices", "testing",
            "performance", "api", "osdev", "lisp", "haskell", "ruby", "java", "zig", "elixir",
            "erlang", "nix", "wasm", "typescript", "distributed", "debugging", "editors",
            "networking", "show", "programming-languages", "cli", "library", "framework",
        ],
    },
    {
        "id": "hardware",
        "label": "Hardware & Chips",
        "keywords": [
            "chip", "chips", "chipmaker", "cpu", "cpus", "gpu", "gpus", "semiconductor",
            "semiconductors", "tsmc", "nvidia", "amd", "intel", "arm", "risc-v", "qualcomm",
            "processor", "processors", "ram", "dram", "hbm", "memory chips", "memory prices",
            "memory crunch", "memory shortage", "nand", "ssd", "ssds", "foundry",
            "raspberry pi", "hardware", "motherboard", "fab", "fabs", "silicon", "wafer", "asml",
            "ryzen", "radeon", "geforce", "rtx", "xeon", "epyc", "data center", "datacenter",
            "data centers", "supercomputer", "fpga", "microcontroller", "soldering", "pcb",
        ],
        "tags": ["hardware", "fpga"],
    },
    {
        "id": "gadgets",
        "label": "Gadgets & Apple",
        "keywords": [
            "apple", "iphone", "iphones", "ipad", "ipads", "mac", "macbook", "macos", "ios",
            "ipados", "watchos", "visionos", "vision pro", "airpods", "apple watch", "imac",
            "android", "pixel", "galaxy", "samsung", "oneplus", "smartphone", "smartphones", "phone",
            "phones", "laptop", "laptops", "tablet", "tablets", "headphones", "earbuds",
            "smartwatch", "wearable", "wearables", "kindle", "e-reader", "camera", "tv", "tvs",
            "oled", "smart home", "homepod", "alexa", "echo", "fitbit", "garmin", "oura",
            "gadget", "gadgets", "chromebook", "surface", "meta quest", "headset", "ar glasses",
            "smart glasses", "router",
        ],
        "tags": ["apple", "android", "mobile"],
    },
    {
        "id": "software",
        "label": "Software & Cloud",
        "keywords": [
            "microsoft", "windows", r"windows \d+", "office", "excel", "word", "outlook", "teams",
            "azure", "aws", "amazon web services", "google cloud", "gcp", "cloud", "cloudflare",
            "serverless", "saas", "vmware", "broadcom", "oracle", "salesforce", "adobe",
            "photoshop", "figma", "notion", "slack", "zoom", "operating system", "os", "app",
            "apps", "app store", "software", "update", "chrome os", "chromeos", "edge",
            "kubernetes", "virtualization", "vm", "vms", "self-hosted", "self-hosting", "homelab",
        ],
        "tags": ["windows", "cloud", "virtualization"],
    },
    {
        "id": "science",
        "label": "Science & Space",
        "keywords": [
            "space", "nasa", "spacex", "rocket", "rockets", "launchpad", "starship", "falcon 9",
            "orbit", "orbital", "satellite", "satellites", "moon", "lunar", "mars", "asteroid",
            "telescope", "jwst", "astronomers", "physics", "physicists", "quantum", "biology",
            "scientists", "researchers", "study", "climate", "fusion", "nuclear", "genome",
            "dna", "crispr", "vaccine", "medicine", "medical", "brain", "neuroscience", "species",
            "fossil", "evolution", "chemistry", "mathematics", "math", "mathematician", "ocean",
            "earthquake", "solar", "energy", "battery", "batteries", "blue origin", "esa",
        ],
        "tags": ["science", "math", "space", "physics", "biology"],
    },
    {
        "id": "business",
        "label": "Business & Startups",
        "keywords": [
            "startup", "startups", "funding", "raises", "raised", "series a", "series b",
            "series c", "seed round", "valuation", "valued", "ipo", "acquires", "acquired",
            "acquisition", "acquisitions", "merger", "layoffs", "lays off", "laid off", "earnings",
            "revenue", "profit", "investors", "investor", "venture", "vc", "y combinator", "yc",
            "ceo", "cfo", "founder", "founders", "billion", "shares", "stock", "market cap",
            "subscription", "subscriptions", "pricing", "price hike", "enterprise", "hiring",
            "jobs", "workers", "employees", "unicorn", "bankrupt", "bankruptcy", "shuts down",
        ],
    },
    {
        "id": "policy",
        "label": "Policy & Law",
        "keywords": [
            "regulation", "regulations", "regulator", "regulators", "law", "laws", "lawsuit",
            "lawsuits", "sued", "sues", "court", "judge", "ruling", "ftc", "doj", "fcc", "sec",
            "eu", "european commission", "antitrust", "ban", "bans", "banned", "congress",
            "senate", "senator", "lawmakers", "legislation", "bill", "privacy", "gdpr", "dma",
            "government", "tariff", "tariffs", "export controls", "sanctions", "trump",
            "white house", "copyright", "patent", "patents", "settlement", "fine", "fined",
            "investigation", "probe", "police", "ice", "election", "elections", "censorship",
            "age verification", "uk", "ofcom", "china", "chinese",
        ],
    },
    {
        "id": "gaming",
        "label": "Gaming",
        "keywords": [
            "game", "games", "gaming", "gamer", "gamers", "xbox", "playstation", "ps5", "ps6",
            "nintendo", "switch 2", "steam", "steam deck", "valve", "esports", "console",
            "consoles", "game pass", "epic games", "fortnite", "minecraft", "roblox", "gta",
            "speedrun", "emulator", "emulation", "retro", "indie game",
        ],
        "tags": ["games"],
    },
    {
        "id": "transport",
        "label": "EVs & Transport",
        "keywords": [
            "ev", "evs", "electric vehicle", "electric vehicles", "tesla", "waymo", "robotaxi",
            "robotaxis", "cybercab", "self-driving", "autonomous", "autopilot", "rivian", "lucid",
            "byd", "car", "cars", "automaker", "automakers", "charging", "charger", "drone",
            "drones", "e-bike", "ebike", "aviation", "airline", "airlines", "boeing", "airbus",
            "train", "trains", "uber", "lyft", "zoox", "cruise",
        ],
    },
    {
        "id": "internet",
        "label": "Internet & Social",
        "keywords": [
            "social media", "twitter", "bluesky", "mastodon", "fediverse", "threads", "meta",
            "facebook", "instagram", "whatsapp", "tiktok", "youtube", "reddit", "discord",
            "twitch", "streaming", "netflix", "spotify", "podcast", "podcasts", "web", "website",
            "websites", "browser", "browsers", "chrome", "firefox", "safari", "search engine",
            "google search", "internet", "online", "creator", "creators", "influencer",
            "influencers", "musk", "zuckerberg", "rss", "email", "gmail", "dns", "isp",
            "broadband", "starlink", "wikipedia",
        ],
        "tags": ["web", "browsers"],
    },
    {
        "id": "crypto",
        "label": "Crypto",
        "keywords": [
            "bitcoin", "btc", "crypto", "cryptocurrency", "ethereum", "eth", "blockchain",
            "stablecoin", "stablecoins", "nft", "nfts", "coinbase", "binance", "solana", "defi",
            "web3", "token", "memecoin",
        ],
        "tags": ["cryptocurrencies", "crypto", "blockchain"],
    },
]

TOPICS_BY_ID = {t["id"]: t for t in TOPICS}


def _compile(keywords: list[str]) -> re.Pattern:
    alternation = "|".join(sorted(keywords, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alternation})(?![\w-])", re.IGNORECASE)


_PATTERNS = {t["id"]: _compile(t["keywords"]) for t in TOPICS}
_TAGS = {t["id"]: {tag.lower() for tag in t.get("tags", [])} for t in TOPICS}


def classify(title: str, summary: str = "", source_tags: list[str] | None = None) -> list[str]:
    """Return topic ids for a story, strongest first."""
    tags = {t.lower() for t in (source_tags or [])}
    scores: dict[str, int] = {}
    for topic_id, pattern in _PATTERNS.items():
        score = 2 * len(pattern.findall(title)) + len(pattern.findall(summary or ""))
        score += 2 * len(tags & _TAGS[topic_id])
        # Source tags can also be free-form categories ("Artificial Intelligence").
        score += 2 * sum(1 for tag in tags if pattern.fullmatch(tag))
        if score >= 2:
            scores[topic_id] = score
    return sorted(scores, key=lambda t: (-scores[t], [x["id"] for x in TOPICS].index(t)))


def public_topics() -> list[dict]:
    return [{"id": t["id"], "label": t["label"]} for t in TOPICS]
