# ArticleGenerator

**Turn your voice into publish-ready articles — powered by AI, but 100 % your words.**

ArticleGenerator automates the workflow of turning spoken audio recordings into fully formatted blog articles, while keeping the original voice, personality, and tone of the author completely intact. The AI is used strictly as a tool to transcribe, structure, and format — it never invents content, changes the author's opinions, or injects artificial language. The result reads like the author wrote it by hand, because in every meaningful sense, they did.

## Why This Exists

Writing articles takes time. Recording your thoughts into a microphone is fast and natural. The gap between a raw audio recording and a polished blog post is mostly mechanical work — transcription, formatting, SEO metadata, HTML structure. That's the gap this tool fills.

**This is not "ask AI to write an article about something."** The information, the stories, the opinions, the tone — everything comes from the author's own voice. AI handles the tedious parts (transcription, structuring, HTML formatting) so the author can focus on what matters: sharing their knowledge and experience.

### Key Principles

- **Author-first** — The article is built entirely from the author's spoken words. Nothing is invented or embellished.
- **Voice preservation** — Colloquial expressions, personal anecdotes, spontaneous observations, and natural speech patterns are kept, not "cleaned up" into generic content.
- **AI as assistant, not author** — AI transcribes, organizes, and formats. It does not create content, rewrite meaning, or add filler.
- **No artificial SEO fluff** — The output avoids the robotic, overly-optimized tone that plagues AI-generated content.

## How It Works

```
Google Drive (audio files)
        │
        ▼
  Download & group related files
        │
        ▼
  Upload to Gemini for transcription + article generation
  (with strict instructions to preserve the author's voice)
        │
        ▼
  Structured output: title, HTML content, meta description, category
        │
        ▼
  Post as WordPress draft + create Google Doc backup
```

1. **Monitor** — The app polls a Google Drive folder for new audio files (`.mp3`, `.m4a`, `.wav`, etc.).
2. **Group** — Related audio files (e.g. `setas_cantharellus_1.mp3`, `setas_cantharellus_2.mp3`) are automatically grouped and processed together as a single article.
3. **Transcribe & Structure** — Audio is sent to Google Gemini, which transcribes and structures the content into a clean HTML article. The prompt is carefully designed to preserve the author's natural voice and prohibit AI-typical language patterns.
4. **Enrich** — The system automatically assigns a WordPress category, generates an SEO meta description, and injects 1–2 internal links to previously published articles.
5. **Publish** — The finished article is uploaded to WordPress as a draft (ready for final review) and a Google Doc copy is created for reference.
6. **Track** — Every processed file is tracked in a local JSON database to avoid duplicates.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| AI Model | Google Gemini (`gemini-3.8-flash`) |
| Cloud Storage | Google Drive API |
| CMS | WordPress REST API |
| Dependency Management | Poetry |
| Configuration | `.env` + `python-dotenv` |

## Project Structure

```
ArticleGenerator/
├── main.py                  # Entry point — daemon or run-once mode
├── process.py               # Core pipeline: download → generate → publish
├── config.py                # All configuration, prompts, and constants
├── db.py                    # JSON-based file tracking database
├── utils.py                 # Helper functions (file grouping, cleanup, etc.)
├── services/
│   ├── gemini_service.py    # Gemini API integration (transcription + generation)
│   ├── google_drive_service.py  # Google Drive file listing, download, doc creation
│   └── wordpress_service.py     # WordPress draft posting and image upload
├── tests/                   # Test suite
├── pyproject.toml           # Poetry project definition and dependencies
└── .env                     # Environment variables (API keys, credentials)
```

## Setup

### Prerequisites

- Python 3.10 or higher
- [Poetry](https://python-poetry.org/) for dependency management
- A Google Cloud project with Drive and Docs APIs enabled
- A Google Gemini API key
- A WordPress site with REST API access (application password)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ArticleGenerator.git
cd ArticleGenerator

# Install dependencies
poetry install

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys and credentials
```

### Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_SECRET` | Path to your Google OAuth client secret JSON |
| `MODEL_API_KEY` | Google Gemini API key |
| `WORDPRESS_USER` | WordPress username |
| `WORDPRESS_PASSWORD` | WordPress application password |

## Usage

### Daemon Mode (default)

Continuously polls Google Drive for new audio files every 5 minutes:

```bash
poetry run python main.py
```

### Run-Once Mode

Processes any pending files and exits immediately:

```bash
poetry run python main.py --run-once
```

## License

This project is private and not currently licensed for public distribution.
