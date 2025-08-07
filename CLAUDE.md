# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation
```bash
pip3 install -r requirements.txt
```

### Main Application

#### Interactive Mode (Recommended)
```bash
# Demo mode with interactive prompts
python demo_mode.py

# Full version with interactive prompts
python generate_video_cards.py
```

#### Command Line Mode
```bash
# Full version with video download
python generate_video_cards.py "https://www.youtube.com/watch?v=VIDEO_ID" transcript.vtt --description "Video Title" --keywords intro conclusion demo --cards 4 --output-dir highlights

# Demo mode without video download
python demo_mode.py "https://www.youtube.com/watch?v=VIDEO_ID" transcript.vtt --description "Video Title" --keywords intro conclusion demo --cards 4 --output-dir demo_output
```

### Creating Transcripts from Pasted Text
```bash
# Standalone transcript converter
python transcript_converter.py

# Or create transcripts during interactive mode (recommended)
python demo_mode.py  # Will offer transcript creation option
```

### Testing Dependencies
```bash
python test_imports.py
```

## Architecture Overview

This is a Python-based YouTube highlight generator that processes video transcripts to create static HTML pages with video segments.

### Core Components

**TranscriptParser** - Handles parsing of WebVTT (.vtt) and SRT (.srt) transcript files into structured entries with timing information.

**SegmentFinder** - Identifies interesting segments using keyword-based search. Finds segments containing specified keywords and includes 5 surrounding transcript entries for context. Fills remaining cards by splitting unused content evenly.

**Summarizer/DemoSummarizer** - Text summarization with two modes:
- Full version: Uses Facebook's BART-large-CNN model with fallback to extractive summarization
- Demo version: Simple extractive summarization (first sentence or first 30 words)

**VideoProcessor/DemoThumbnailGenerator** - Handles media processing:
- Full version: Downloads YouTube videos using pytube and extracts frames at precise timestamps using MoviePy
- Demo version: Creates placeholder thumbnails with PIL showing timestamp and text preview

**HTMLGenerator** - Generates responsive static HTML pages with:
- Embedded YouTube player
- Grid layout of highlight cards
- Modern UI with glass morphism design
- Direct links to specific timestamps

### Data Flow

1. Parse transcript file → TranscriptEntry objects with timing
2. Find segments based on keywords → List of (start_index, end_index) tuples
3. For each segment:
   - Extract text and timing from transcript entries
   - Generate summary
   - Create thumbnail (extract frame or generate placeholder)
   - Build YouTube link with timestamp
4. Generate complete HTML page with all segments

### File Structure

- `generate_video_cards.py` - Main application with full video processing
- `demo_mode.py` - Demo version without video download requirements
- `transcript_converter.py` - Utility to create .vtt files from pasted transcript text
- `test_imports.py` - Dependency verification script
- `requirements.txt` - Python dependencies (pytube, moviepy, pillow, numpy)
- `*.vtt` and `*.srt` files - Transcript files for testing
- `*.html` files - Example output pages

### Transcript Creation Features

**transcript_converter.py** supports multiple input formats:
- `0:15 Some text here` (M:SS format)
- `1:23:45 Some text here` (H:MM:SS format)
- `[0:15] Some text here` (bracketed timestamps)
- `0:15 - Some text here` (dash separator)
- `0:15: Some text here` (colon separator)

Automatically estimates end times based on text length and gaps between segments. Creates properly formatted WebVTT files ready for use with the highlight generator.

### Dependencies

**Required**: pytube, moviepy, pillow, numpy
**Optional**: transformers (for AI summarization)

The application gracefully handles missing optional dependencies by falling back to simpler implementations.

### Output Structure

Generated output directory contains:
- `index.html` - Main highlight page
- `video.mp4` - Downloaded video (full version only)  
- `thumbnail_001.png` through `thumbnail_N.png` - Segment thumbnails
- Ready for direct deployment to Netlify or similar static hosts