"""Central application settings.

Every threshold lives here so behaviour can be tuned without editing logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"

# Category rules: keyword -> weight. A keyword counts once, however often it appears.
# Multi-word phrases are matched as whole word sequences. Weights: 3-4 = strong signal
# (app/site names, distinctive phrases), 2 = good, 1 = weak/generic. A category needs
# category_min_score points AND a lead of category_min_margin over the runner-up.
CATEGORY_RULES: dict[str, dict[str, int]] = {
    "Programming": {
        "python": 2, "javascript": 2, "typescript": 2, "java": 1, "github": 2,
        "traceback": 3, "stack trace": 3, "syntax error": 3, "modulenotfounderror": 3,
        "module not found": 3, "null pointer": 3, "pull request": 3, "stack overflow": 3,
        "visual studio code": 3, "vs code": 3, "powershell": 3, "command prompt": 2,
        "pip install": 3, "npm": 2, "docker": 2, "kubernetes": 2, "venv": 2,
        "requirements txt": 2, "source code": 2, "localhost": 2, "unit test": 2,
        "streamlit": 2, "scripting": 2, "pytest": 2,
        "exception": 1, "except": 1, "def": 1, "import": 1, "function": 1,
        "class": 1, "variable": 1, "compile": 1, "debug": 1, "git": 1, "commit": 1,
        "repository": 1, "terminal": 1, "code": 1, "sql": 1, "database": 1,
        "schema": 1, "api": 1, "print": 1, "html": 1, "css": 1, "error": 1,
        "automation": 1, "json": 1,
    },
    "AI Chat": {
        "chatgpt": 3, "claude": 3, "gemini": 3, "copilot": 3, "deepseek": 3,
        "perplexity": 3, "openai": 3, "message chatgpt": 4, "ask anything": 3,
        "ai assistant": 3, "new chat": 2, "regenerate": 2, "prompt": 2, "gpt": 2,
        "llm": 2, "anthropic": 2, "grok": 2,
        "model": 1, "tokens": 1, "response": 1,
    },
    "Education": {
        "assignment": 2, "lecture": 2, "syllabus": 2, "exam": 2, "quiz": 2,
        "homework": 2, "semester": 2, "university": 2, "professor": 2,
        "tutorial": 2, "lesson": 2, "textbook": 2, "theorem": 2, "bibliography": 2,
        "scholarship": 2, "gpa": 2, "lecture notes": 3, "past paper": 3,
        "research paper": 2, "khan academy": 3, "coursera": 3, "udemy": 3,
        "wikipedia": 2,
        "chapter": 1, "course": 1, "lab": 1, "notes": 1, "submit": 1, "deadline": 1,
        "study": 1, "student": 1, "students": 1, "learning": 1, "definition": 1,
        "abstract": 1, "slides": 1, "grade": 1, "marks": 1,
        # Certification plus completion context is evidence; "certificate" alone is not.
        "certification": 1, "successfully completed": 2,
        "certificate of completion": 4, "completed a course": 3,
        "training program": 4, "professional certification": 4,
        "online course": 3, "examination": 3,
        "academic assignment": 3, "course completion": 4,
    },
    "Work": {
        "meeting": 2, "agenda": 2, "jira": 2, "quarterly": 2, "sprint": 2,
        "stakeholder": 2, "deliverable": 2, "kpi": 2, "roadmap": 2, "okr": 2,
        "standup": 2, "confluence": 2, "asana": 2, "trello": 2, "linkedin": 2,
        "resume": 2, "microsoft teams": 3, "google meet": 3, "meeting notes": 3,
        "action items": 3, "job application": 3,
        "client": 1, "project": 1, "slack": 1, "report": 1, "proposal": 1,
        "budget": 1, "zoom": 1, "deadline": 1, "calendar": 1, "schedule": 1,
        "revenue": 1, "contract": 1, "hiring": 1, "interview": 1, "notion": 1,
    },
    "Communication": {
        "gmail": 3, "outlook": 3, "search mail": 3, "reply all": 3, "snoozed": 3,
        "whatsapp": 3, "telegram": 3, "discord": 3,
        "inbox": 2, "compose": 2, "drafts": 2, "starred": 2, "unread": 2,
        "mark as read": 2, "bcc": 2, "messenger": 2, "slack": 2, "last seen": 2,
        "voice message": 2, "direct message": 2, "group chat": 2,
        "reply": 1, "forward": 1, "subject": 1, "chat": 1, "message": 1,
        "messages": 1, "attachment": 1, "typing": 1,
    },
    "Web Search": {
        "people also ask": 4, "related searches": 4, "google search": 3,
        "search results": 3, "safesearch": 3, "duckduckgo": 3, "featured snippet": 3,
        "images videos": 2, "videos maps": 2, "maps news": 2, "web results": 2,
        "bing": 2, "sponsored": 2,
        "ai overview": 3, "ai mode": 2, "people also search for": 4, "search tools": 2,
        "all images": 2, "all news": 2, "google": 2,
        "searches": 1,
    },
    "Shopping": {
        "add to cart": 4, "cash on delivery": 4, "amazon": 3, "daraz": 3, "ebay": 3,
        "aliexpress": 3, "shein": 3, "buy now": 3, "free delivery": 3,
        "order summary": 3, "order placed": 3, "track order": 3,
        "cart": 2, "checkout": 2, "in stock": 2, "out of stock": 2, "discount": 2,
        "coupon": 2, "wishlist": 2, "shipping": 2, "your order": 2,
        "delivery": 1, "price": 1, "sale": 1, "reviews": 1, "order": 1, "receipt": 1,
    },
    "Finance": {
        "bank statement": 4, "credit card": 3, "debit card": 3, "tax return": 3,
        "payment successful": 3, "transaction id": 3, "amount paid": 3,
        "easypaisa": 3, "jazzcash": 3, "paypal": 3, "binance": 3, "iban": 3,
        "bank": 2, "transaction": 2, "transactions": 2, "withdrawal": 2,
        "withdraw": 2, "loan": 2, "stripe": 2, "crypto": 2, "bitcoin": 2,
        "portfolio": 2, "dividend": 2, "account number": 2, "invoice": 2,
        "total amount": 2,
        "balance": 1, "transfer": 1, "payment": 1, "deposit": 1, "tax": 1,
        "interest": 1, "stock": 1, "receipt": 1,
    },
    "Travel": {
        "boarding pass": 4, "itinerary": 3, "airbnb": 3, "tripadvisor": 3,
        "booking com": 3, "careem": 3, "layover": 3,
        "flight": 2, "flights": 2, "hotel": 2, "airline": 2, "airport": 2,
        "departure": 2, "arrival": 2, "passport": 2, "visa": 2, "resort": 2,
        "reservation": 2, "baggage": 2, "uber": 2, "google maps": 2,
        "estimated arrival": 2,
        "booking": 1, "check in": 1, "check out": 1, "ticket": 1, "directions": 1,
        "route": 1, "trip": 1, "travel": 1, "pickup": 1,
    },
    "Entertainment": {
        "youtube": 3, "netflix": 3, "spotify": 3, "prime video": 3, "tiktok": 3,
        "watch later": 3,
        "twitch": 2, "instagram": 2, "reddit": 2, "twitter": 2, "facebook": 2,
        "playlist": 2, "episode": 2, "trailer": 2, "subscribers": 2, "followers": 2,
        "reels": 3, "gameplay": 2,
        # Video / music pages
        "coke studio": 3, "official video": 3, "music video": 3,
        "up next": 2, "autoplay": 2, "shorts": 2, "lyrics": 2,
        "subscribe": 1, "likes": 1, "movie": 1, "song": 1, "album": 1, "season": 1,
        "game": 1, "steam": 1,
    },
    "Design": {
        "figma": 3, "canva": 3, "dribbble": 3, "behance": 3, "photoshop": 3,
        "illustrator": 3, "artboard": 3, "wireframe": 3, "mockup": 3,
        "color palette": 3, "design system": 3, "ui design": 3,
        "typography": 2, "prototype": 2, "adobe": 2,
        "ux": 1, "layout": 1, "font": 1, "gradient": 1, "icon": 1, "dashboard": 1,
        "sidebar": 1, "component": 1, "layers": 1, "inspiration": 1,
    },
    "Health": {
        "presenting illness": 4, "history of presenting illness": 4, "blood pressure": 3,
        "chief complaint": 3, "past medical history": 3, "history taking": 3,
        "symptoms": 2, "diagnosis": 2, "treatment": 2, "medication": 2, "illness": 2,
        "patient": 2, "disease": 2, "hospital": 2, "clinical": 2, "diabetes": 2,
        "prescription": 3, "doctor": 1, "nutrition": 1, "diet": 1, "fitness": 1,
    },
    "System & Files": {
        "file explorer": 3, "this pc": 3, "quick access": 3, "date modified": 3,
        "recycle bin": 3, "file folder": 3, "task manager": 3, "control panel": 3,
        "device manager": 3, "windows settings": 3, "disk cleanup": 3,
        "new folder": 2, "downloads": 2, "bluetooth": 2, "wifi": 2, "onedrive": 2,
        "documents": 1, "desktop": 1, "pictures": 1, "videos": 1, "libraries": 1,
        "storage": 1, "settings": 1, "properties": 1, "windows": 1, "folder": 1,
    },
    "Personal": {
        # "prescription" lives in Health only: a duplicate weight here created ties
        # that dropped medical screenshots into Uncategorized.
        "recipe": 2, "ingredients": 2, "birthday": 2, "appointment": 2, "workout": 2,
        "journal": 2, "diary": 2, "wedding": 2, "to do list": 2,
        "happy birthday": 3, "prep time": 3, "shopping list": 3,
        "family": 1, "health": 1, "doctor": 1, "reminder": 1, "habit": 1, "photos": 1,
    },
}

# Structural signals that plain keywords cannot capture: (label, regex, weight).
# Regexes run case-insensitively, per line, on the cleaned OCR text. Each counts once.
CATEGORY_PATTERNS: dict[str, list[tuple[str, str, int]]] = {
    "Programming": [
        ("def name(", r"\bdef\s+\w+\s*\(", 3),
        ("class Name", r"\bclass\s+\w+\s*[(:]", 2),
        ("import statement", r"^\s*(?:from\s+[\w.]+\s+)?import\s+[\w.*]+", 2),
        ("traceback header", r"traceback \(most recent call last\)", 4),
        ("source file name", r"\b\w+\.(?:py|js|ts|tsx|jsx|java|cpp|cs|go|rs|php|rb)\b", 2),
        ("shell prompt", r"^\s*(?:>>>|ps [a-z]:\\|\$ )", 2),
        ("dev command", r"\b(?:npm|pip3?|git|docker|pytest)\s+(?:install|run|commit|push|pull|build|test|clone)\b", 3),
    ],
    "Web Search": [
        ("'About N results'", r"\babout\s+[\d,.]+\s+results\b", 4),
        ("result timing", r"\bresults?\s*\(\s*[\d.]+\s*seconds?\s*\)", 3),
        ("search tab bar", r"\ball\b.{0,20}\b(?:images|videos|news|maps|shopping)\b", 3),
        ("title starts with Google", r"^google\s+\w+", 2),
    ],
    "Finance": [
        ("currency amount", r"\b(?:rs\.?|pkr|usd|eur)\s?\d[\d,]*(?:\.\d{2})?|[$€£]\s?\d[\d,]*(?:\.\d{2})?", 1),
    ],
    "Shopping": [
        ("currency amount", r"\b(?:rs\.?|pkr|usd)\s?\d[\d,]*(?:\.\d{2})?", 1),
    ],
    "Communication": [
        ("email header", r"^(?:from|to|subject|cc|bcc)\s*:", 2),
    ],
    "Travel": [
        ("flight number", r"\bflight\s+[a-z]{2}\s?\d{2,4}\b", 3),
    ],
    "Education": [
        ("chapter / unit / lesson N", r"\b(?:chapter|unit|lesson|week|module)\s+\d+\b", 2),
    ],
    "Entertainment": [
        ("views / followers count", r"\b\d+(?:[.,]\d+)?\s?[km]?\s+(?:views|subscribers|followers|likes)\b", 3),
    ],
    "System & Files": [
        ("file names with extensions", r"\b[\w\-]+\.(?:png|jpe?g|pdf|docx?|xlsx?|pptx?|zip|rar|exe|mp4|mp3|txt|csv)\b", 2),
    ],
}

# Example sentences describing what each category looks like. The semantic classifier compares the
# meaning of the OCR text with these; more varied examples = better coverage. Write some of them in
# "screen text" style (short labels and phrases), because that is what OCR actually produces.
# There is deliberately NO "Uncategorized" entry: UI-heavy OCR always resembles a generic class and
# it would swallow real categories. Uncategorized is the result when nothing is clearly best.
CATEGORY_DESCRIPTIONS: dict[str, list[str]] = {
    "Programming": [
        "Python code in a code editor with functions, imports and variables.",
        "A terminal or command prompt showing commands, logs and error messages with a stack trace.",
        "A GitHub repository, pull request or Stack Overflow question about fixing a programming bug.",
    ],
    "AI Chat": [
        "A conversation with an AI chatbot such as ChatGPT, Claude or Gemini with a prompt and a long answer.",
        "New chat, ask anything, message the assistant, regenerate response, copy, like, dislike.",
    ],
    "Education": [
        "An encyclopedia or article explaining a topic such as science, history, geography, religion or nature.",
        "Lecture slides, textbook pages, study notes, assignments, exams and course material.",
        "A tutorial, lesson or certificate of completion for an online course.",
        "A question and answer explaining how something works or giving facts about a subject.",
        "How-to guides and explainer articles: how to learn a language, ways to save water, tips and steps.",
    ],
    "Health": [
        "Medical information about symptoms, diseases, illness history, diagnosis, treatment and medication.",
        "A clinical note, patient history, prescription, lab report or doctor appointment.",
        "Fitness, nutrition, diet and healthy lifestyle advice.",
        "History of presenting illness, chief complaint, past medical history, examination findings, management plan.",
    ],
    "Work": [
        "Meeting agenda, project plan, sprint board or task tracker for a team.",
        "A business report, spreadsheet, proposal, budget or client document.",
        "A job application, resume, LinkedIn profile or workplace deadline.",
    ],
    "Communication": [
        "An email inbox with messages, compose and reply buttons, Gmail or Outlook.",
        "A chat conversation with messages from friends or colleagues on WhatsApp, Telegram, Slack or Discord.",
    ],
    "Web Search": [
        "A Google or Bing search results page with a list of links, snippets and tabs for images, videos and news.",
        "A web browser search box with suggestions, related searches and people also ask questions.",
    ],
    "Shopping": [
        "An online store product page with price, add to cart button, reviews and delivery information.",
        "An order confirmation, shopping cart or delivery tracking page.",
    ],
    "Finance": [
        "A bank statement or mobile wallet showing transactions, balances and payments.",
        "An invoice, tax document, loan, credit card bill or investment portfolio.",
        "Cryptocurrency or stock trading prices and charts.",
    ],
    "Travel": [
        "A flight booking, boarding pass, hotel reservation or trip itinerary.",
        "A map with directions, a ride-hailing trip or tourist destination information.",
    ],
    "Entertainment": [
        "A YouTube, Netflix or Spotify page showing videos, movies, music or playlists.",
        "A social media feed such as Instagram, TikTok, Reddit or Twitter with posts, likes and followers.",
        "A video game, gameplay or streaming channel.",
        "Official music video, Coke Studio, 2.1M views, subscribe, comments, up next, autoplay, Shorts.",
    ],
    "Design": [
        "A user interface design in Figma or Canva with mockups, wireframes and layouts.",
        "A color palette, typography, logo or graphic design inspiration board.",
    ],
    "System & Files": [
        "A file explorer window listing folders and files with name, date modified, type and size columns.",
        "Windows settings, control panel, task manager, device manager or a downloads folder.",
        "Quick access, this PC, desktop, documents, pictures, downloads, new folder, recycle bin.",
    ],
    "Personal": [
        "A cooking recipe with ingredients and preparation steps.",
        "Personal life notes: birthdays, family, to-do lists, journals, wedding or hobbies.",
    ],
}

# Prompts for the vision layer (CLIP). Short, concrete, "a screenshot of ..." phrasing works best.
IMAGE_DESCRIPTIONS: dict[str, list[str]] = {
    "Programming": [
        "a screenshot of source code in a code editor",
        "a screenshot of a terminal window with commands and error messages",
        "a screenshot of a GitHub repository page",
    ],
    "AI Chat": [
        "a screenshot of a ChatGPT conversation",
        "a screenshot of an AI chatbot answering a prompt",
    ],
    "Education": [
        "a screenshot of lecture slides or a textbook page",
        "a screenshot of an encyclopedia article on Wikipedia",
        "a screenshot of an online course or tutorial",
    ],
    "Health": [
        "a screenshot of a medical document or patient notes",
        "a screenshot of a health or fitness app",
    ],
    "Work": [
        "a screenshot of a spreadsheet or business report",
        "a screenshot of a project board with tasks",
        "a screenshot of a video meeting",
    ],
    "Communication": [
        "a screenshot of an email inbox",
        "a screenshot of a WhatsApp chat conversation",
    ],
    "Web Search": [
        "a screenshot of Google search results",
        "a screenshot of a Google search results page with blue links",
        "a screenshot of a dark mode Google search with an AI overview",
        "a screenshot of a search engine page with a search bar and a list of results",
    ],
    "Shopping": [
        "a screenshot of an online store product page",
        "a screenshot of a shopping cart",
    ],
    "Finance": [
        "a screenshot of a banking app with transactions",
        "a screenshot of a stock or crypto price chart",
    ],
    "Travel": [
        "a screenshot of a map with directions",
        "a screenshot of a flight or hotel booking",
    ],
    "Entertainment": [
        "a screenshot of a YouTube video page",
        "a screenshot of a movie or music streaming app",
        "a screenshot of a social media feed",
        "a screenshot of a video game",
    ],
    "Design": [
        "a screenshot of Figma or a graphic design tool",
        "a screenshot of a poster or logo design",
    ],
    "System & Files": [
        "a screenshot of Windows File Explorer showing folders and files",
        "a screenshot of the Windows settings or control panel",
        "a screenshot of a computer desktop with icons",
    ],
    "Personal": [
        "a screenshot of a cooking recipe",
        "a screenshot of a birthday message or personal photo",
    ],
}


@dataclass(frozen=True)
class Settings:
    # --- File support & detection ---
    supported_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
    screenshot_name_patterns: tuple[str, ...] = (
        "Screenshot*", "Screen Shot*", "Snip*", "Capture*",
    )

    # --- Folders ---
    default_destination: Path = PROJECT_ROOT / "organized_screenshots"
    database_path: Path = PROJECT_ROOT / "data" / "screenshots.db"

    # --- Categories ---
    categories: dict[str, dict[str, int]] = field(default_factory=lambda: CATEGORY_RULES)
    category_patterns: dict[str, list[tuple[str, str, int]]] = field(default_factory=lambda: CATEGORY_PATTERNS)
    category_descriptions: dict[str, list[str]] = field(default_factory=lambda: CATEGORY_DESCRIPTIONS)
    image_descriptions: dict[str, list[str]] = field(default_factory=lambda: IMAGE_DESCRIPTIONS)
    category_min_score: int = 3       # evidence needed to pick a category (rules-only / rescue path)
    category_min_margin: int = 2      # lead needed over the runner-up (rules-only / rescue path)
    uncategorized_name: str = "Uncategorized"

    # Keyword evidence this strong (score AND lead) decides on its own, before meaning is consulted.
    rules_decisive_score: int = 6
    rules_decisive_margin: int = 3

    # --- Meaning-based classification (text) ---
    # Needs `pip install fastembed`; downloads a ~130 MB model once, then runs offline.
    # If the package or model is unavailable, the keyword rules are used instead.
    semantic_enabled: bool = True
    semantic_min_similarity: float = 0.40    # absolute floor for the winning category
    semantic_min_margin: float = 0.02        # required lead over the runner-up (after keyword bonus)
    semantic_temperature: float = 0.02       # softmax sharpness for confidence; lower = more decisive
    semantic_min_prob: float = 0.35          # winner must hold at least this share of the probability mass
    keyword_bonus_per_point: float = 0.015   # each keyword/pattern point adds this to its category
    keyword_bonus_cap: int = 8               # ...up to this many points

    # --- Vision-based classification (the screenshot itself, CLIP) ---
    # Same package (fastembed); downloads two CLIP models once (a few hundred MB), then runs offline.
    # Used when the text layers are unsure. Raise image_min_prob if it mislabels; lower it to label more.
    image_enabled: bool = True
    image_min_prob: float = 0.55             # winner's share of the probability mass
    image_min_similarity: float = 0.20       # raw CLIP cosine floor; below this nothing really fits

    # --- OCR ---
    tesseract_cmd: str | None = None      # Set a full path here if auto-detect fails
    ocr_language: str = "eng"
    ocr_psm: int = 3                      # Tesseract page segmentation mode
    ocr_min_width: int = 1600             # Upscale narrower images to this width
    ocr_min_word_confidence: float = 30.0
    ocr_small_text_height: float = 16.0
    ocr_retry_scale: float = 2.0
    ocr_fallback_psm: int = 11
    ocr_timeout: float = 60.0  # total budget across OCR attempts

    # --- Reliability gates ---
    min_text_chars: int = 8               # Fewer letters/digits than this = unreadable
    min_mean_confidence: float = 50.0     # Whole-image OCR confidence gate
    min_line_confidence: float = 50.0     # Per-line gate for title candidates
    min_title_score: float = 3.0          # Best heading must reach this score

    # --- Filenames ---
    max_title_words: int = 6
    max_filename_length: int = 80         # Includes date and extension
    fallback_title: str = "Screenshot"