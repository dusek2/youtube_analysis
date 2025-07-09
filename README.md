# Testing OpenAI Codex on this Project

# youtube_analysis
Analyzes youtube channel and recommends next content ideas.

## Fetching Channel Data

Use `fetch_youtube_data.py` to download video metadata and transcripts for a YouTube channel. The script requires a YouTube Data API key provided via the `YOUTUBE_API_KEY` environment variable.

The script now outputs progress messages using Python's built‑in logging module so you can see what step is running.

### Installation

```bash
pip install -r requirements.txt
```

### Usage

```bash
python fetch_youtube_data.py --handle @KamFIT24 --start 2023-01-01 --end 2023-12-31
```

The output will be stored in the `output/` folder with a `videos.csv` file and a `transcripts/` directory containing individual transcript files.
