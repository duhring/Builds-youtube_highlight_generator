#!/usr/bin/env python3
"""
YouTube Highlight Generator

A tool that accepts a YouTube URL and timed transcript, automatically identifies
segments of interest, summarizes those segments, extracts representative frames,
and generates a static HTML page for hosting on Netlify.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
import logging

# Third-party imports (will be installed via requirements.txt)
try:
    from pytube import YouTube
    from PIL import Image
    import numpy as np
    
    # Import MoviePy VideoFileClip
    from moviepy import VideoFileClip
            
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

# Optional AI imports with fallback
try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    print("Warning: transformers not available. Using fallback summarization.")

@dataclass
class TranscriptEntry:
    """Represents a single caption entry with timing."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Caption text

@dataclass
class Segment:
    """Represents a segment of the video with summary and thumbnail."""
    start_time: float
    end_time: float
    summary: str
    thumbnail_path: str
    youtube_link: str
    transcript_text: str

class TranscriptParser:
    """Handles parsing of WebVTT and SRT transcript files."""
    
    @staticmethod
    def parse_webvtt(file_path: str) -> List[TranscriptEntry]:
        """Parse WebVTT (.vtt) format transcript."""
        entries = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by double newline to get each caption block
        blocks = re.split(r'\n\s*\n', content.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 2:
                continue
                
            # Look for timestamp line (contains -->)
            for i, line in enumerate(lines):
                if '-->' in line:
                    # Parse timestamps
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})', line)
                    if time_match:
                        start_str, end_str = time_match.groups()
                        start_seconds = TranscriptParser._time_to_seconds(start_str)
                        end_seconds = TranscriptParser._time_to_seconds(end_str)
                        
                        # Text is everything after the timestamp line
                        text_lines = lines[i+1:]
                        text = ' '.join(text_lines).strip()
                        
                        if text:
                            entries.append(TranscriptEntry(start_seconds, end_seconds, text))
                    break
        
        return entries
    
    @staticmethod
    def parse_srt(file_path: str) -> List[TranscriptEntry]:
        """Parse SRT (.srt) format transcript."""
        entries = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by double newline to get each caption block
        blocks = re.split(r'\n\s*\n', content.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            # Skip the sequence number (first line)
            # Second line should be timestamps
            time_line = lines[1]
            time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', time_line)
            
            if time_match:
                start_str, end_str = time_match.groups()
                # Convert SRT format (HH:MM:SS,mmm) to seconds
                start_seconds = TranscriptParser._srt_time_to_seconds(start_str)
                end_seconds = TranscriptParser._srt_time_to_seconds(end_str)
                
                # Text is everything from line 3 onwards
                text_lines = lines[2:]
                text = ' '.join(text_lines).strip()
                
                if text:
                    entries.append(TranscriptEntry(start_seconds, end_seconds, text))
        
        return entries
    
    @staticmethod
    def _time_to_seconds(time_str: str) -> float:
        """Convert WebVTT time format (HH:MM:SS.mmm) to seconds."""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1])
        
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    
    @staticmethod
    def _srt_time_to_seconds(time_str: str) -> float:
        """Convert SRT time format (HH:MM:SS,mmm) to seconds."""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split(',')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1])
        
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

class SegmentFinder:
    """Identifies interesting segments in the transcript based on keywords."""
    
    @staticmethod
    def search_keywords(transcript: List[TranscriptEntry], keywords: List[str], num_cards: int) -> List[Tuple[int, int]]:
        """
        Find segments based on keywords.
        Returns list of (start_index, end_index) tuples into the transcript.
        """
        segments = []
        used_indices = set()
        
        # First, find segments based on keywords
        for keyword in keywords:
            if len(segments) >= num_cards:
                break
                
            # Search for keyword in transcript
            for i, entry in enumerate(transcript):
                if keyword.lower() in entry.text.lower() and i not in used_indices:
                    # Found keyword, create segment starting from this entry
                    start_idx = i
                    # Take this entry plus next 5 entries (or until end)
                    end_idx = min(i + 5, len(transcript) - 1)
                    
                    # Mark these indices as used
                    for idx in range(start_idx, end_idx + 1):
                        used_indices.add(idx)
                    
                    segments.append((start_idx, end_idx))
                    break
        
        # If we need more segments, split remaining entries evenly
        remaining_needed = num_cards - len(segments)
        if remaining_needed > 0:
            # Find unused entries
            unused_indices = [i for i in range(len(transcript)) if i not in used_indices]
            
            if unused_indices:
                # Split unused entries into segments
                segment_size = len(unused_indices) // remaining_needed
                if segment_size == 0:
                    segment_size = 1
                
                for i in range(remaining_needed):
                    start_pos = i * segment_size
                    if start_pos >= len(unused_indices):
                        break
                    
                    end_pos = min((i + 1) * segment_size - 1, len(unused_indices) - 1)
                    start_idx = unused_indices[start_pos]
                    end_idx = unused_indices[end_pos]
                    
                    segments.append((start_idx, end_idx))
        
        return segments[:num_cards]

class Summarizer:
    """Handles text summarization with AI model fallback."""
    
    def __init__(self):
        self.summarizer = None
        if HAS_TRANSFORMERS:
            try:
                print("Loading summarization model...")
                self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
                print("Model loaded successfully.")
            except Exception as e:
                print(f"Failed to load summarization model: {e}")
                print("Using fallback summarization.")
    
    def summarize(self, text: str, max_length: int = 50) -> str:
        """
        Summarize text using AI model or fallback to extractive method.
        """
        if not text.strip():
            return "No content available."
        
        # Clean the text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If text is already short, return as-is
        if len(text.split()) <= 10:
            return text
        
        # Try AI summarization first
        if self.summarizer:
            try:
                # BART works better with longer texts
                if len(text.split()) >= 10:
                    result = self.summarizer(text, max_length=max_length, min_length=10, do_sample=False)
                    if result and len(result) > 0:
                        summary = result[0]['summary_text'].strip()
                        if summary:
                            return summary
            except Exception as e:
                print(f"AI summarization failed: {e}")
        
        # Fallback to extractive summarization
        return self._extractive_summary(text)
    
    def _extractive_summary(self, text: str) -> str:
        """Simple extractive summary - first sentence or first 30 words."""
        sentences = re.split(r'[.!?]+', text)
        if sentences and len(sentences[0].strip()) > 0:
            return sentences[0].strip() + "."
        
        # If no sentences, take first 30 words
        words = text.split()
        if len(words) > 30:
            return ' '.join(words[:30]) + "..."
        
        return text

class VideoProcessor:
    """Handles video download and frame extraction."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def download_video(self, youtube_url: str) -> str:
        """Download YouTube video and return local file path."""
        try:
            print(f"Downloading video from: {youtube_url}")
            yt = YouTube(youtube_url)
            
            # Get the highest quality MP4 stream
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            
            if not stream:
                # If no progressive stream, get adaptive stream
                stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc().first()
            
            if not stream:
                raise Exception("No suitable video stream found")
            
            # Download to output directory
            video_path = stream.download(output_path=str(self.output_dir), filename="video.mp4")
            print(f"Video downloaded: {video_path}")
            return video_path
            
        except Exception as e:
            print(f"Error downloading video: {e}")
            raise
    
    def extract_frame(self, video_path: str, timestamp: float, output_filename: str) -> str:
        """Extract frame at given timestamp and save as PNG."""
        try:
            # Load video
            clip = VideoFileClip(video_path)
            
            # Ensure timestamp is within video duration
            timestamp = min(timestamp, clip.duration - 1)
            timestamp = max(timestamp, 0)
            
            # Extract frame
            frame = clip.get_frame(timestamp)
            
            # Convert to PIL Image and save
            image = Image.fromarray(frame)
            output_path = self.output_dir / output_filename
            image.save(output_path, "PNG")
            
            clip.close()
            print(f"Frame extracted: {output_path}")
            return str(output_path)
            
        except Exception as e:
            print(f"Error extracting frame at {timestamp}s: {e}")
            # Return placeholder or raise
            raise

class HTMLGenerator:
    """Generates the static HTML page with embedded video and cards."""
    
    @staticmethod
    def generate_page(youtube_url: str, segments: List[Segment], output_dir: str, description: str = ""):
        """Generate complete HTML page with CSS and JavaScript."""
        
        video_id = HTMLGenerator._extract_video_id(youtube_url)
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Highlights - {description}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }}
        h1 {{ text-align: center; font-size: 2.5rem; margin-bottom: 10px; }}
        .description {{ text-align: center; color: #666; margin-bottom: 30px; font-size: 1.1rem; }}
        .video-container {{
            position: relative;
            width: 100%;
            padding-bottom: 56.25%;
            margin-bottom: 40px;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}
        #player {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
        }}
        .highlights-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
        }}
        .highlight-card {{
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }}
        .highlight-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
        }}
        .card-thumbnail {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            cursor: pointer;
        }}
        .card-content {{ padding: 20px; }}
        .card-summary {{ font-size: 1rem; line-height: 1.6; margin-bottom: 15px; }}
        .card-timestamp {{ color: #666; font-size: 0.9rem; font-weight: 500; margin-bottom: 15px; }}
        .transcript-toggle {{
            font-weight: 500;
            color: #667eea;
            cursor: pointer;
            display: inline-block;
            margin-top: 10px;
            border-bottom: 1px solid transparent;
            transition: border-bottom 0.2s ease;
        }}
        .transcript-toggle:hover {{ border-bottom: 1px solid #667eea; }}
        .transcript-content {{
            display: none;
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            font-size: 0.9rem;
            line-height: 1.5;
            max-height: 150px;
            overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Highlights</h1>
        {f'<p class="description">{description}</p>' if description else ''}
        
        <div class="video-container">
            <div id="player"></div>
        </div>
        
        <div class="highlights-grid">
"""
        
        for i, segment in enumerate(segments):
            thumbnail_filename = Path(segment.thumbnail_path).name
            start_minutes = int(segment.start_time // 60)
            start_seconds = int(segment.start_time % 60)
            
            html_content += f"""
            <div class="highlight-card">
                <img src="{thumbnail_filename}" alt="Thumbnail for segment starting at {start_minutes:02d}:{start_seconds:02d}"
                     class="card-thumbnail" onclick="seekTo({int(segment.start_time)})">
                <div class="card-content">
                    <p class="card-timestamp">Starts at: {start_minutes:02d}:{start_seconds:02d}</p>
                    <p class="card-summary">{segment.summary}</p>
                    <div class="transcript-toggle" onclick="toggleTranscript('transcript-{i}')">
                        Show Transcript
                    </div>
                    <div class="transcript-content" id="transcript-{i}">
                        <p>{segment.transcript_text}</p>
                    </div>
                </div>
            </div>
"""
        
        html_content += """
        </div>
    </div>

    <script>
        var player;
        function onYouTubeIframeAPIReady() {{
            player = new YT.Player('player', {{
                height: '100%',
                width: '100%',
                videoId: '{video_id}',
                playerVars: {{
                    'playsinline': 1
                }},
                events: {{
                    'onReady': onPlayerReady
                }}
            }});
        }}

        function onPlayerReady(event) {{
            // Player is ready
        }}

        function seekTo(seconds) {{
            if (player && typeof player.seekTo === 'function') {{
                player.seekTo(seconds, true);
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }}

        function toggleTranscript(id) {{
            var element = document.getElementById(id);
            var toggle = element.previousElementSibling;
            if (element.style.display === "none" || element.style.display === "") {{
                element.style.display = "block";
                toggle.textContent = "Hide Transcript";
            }} else {{
                element.style.display = "none";
                toggle.textContent = "Show Transcript";
            }}
        }}
    </script>
    <script src="https://www.youtube.com/iframe_api"></script>
</body>
</html>
"""
        
        # Write HTML file
        output_path = Path(output_dir) / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"HTML page generated: {output_path}")
        return str(output_path)
    
    @staticmethod
    def _extract_video_id(youtube_url: str) -> str:
        """Extract video ID from YouTube URL."""
        parsed_url = urlparse(youtube_url)
        
        if parsed_url.hostname == 'youtu.be':
            return parsed_url.path[1:]
        
        if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query)['v'][0]
            if parsed_url.path[:7] == '/embed/':
                return parsed_url.path.split('/')[2]
            if parsed_url.path[:3] == '/v/':
                return parsed_url.path.split('/')[2]
        
        raise ValueError(f"Cannot extract video ID from URL: {youtube_url}")

def main():
    parser = argparse.ArgumentParser(description='Generate YouTube highlight page')
    parser.add_argument('youtube_url', help='YouTube video URL')
    parser.add_argument('transcript_file', help='Path to transcript file (.vtt or .srt)')
    parser.add_argument('--description', default='', help='Description for the page')
    parser.add_argument('--keywords', nargs='*', default=[], help='Keywords to search for segments')
    parser.add_argument('--cards', type=int, default=4, help='Number of highlight cards to generate')
    parser.add_argument('--output-dir', default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        print("🎬 YouTube Highlight Generator")
        print("=" * 50)
        
        # Parse transcript
        print("📝 Parsing transcript...")
        transcript_path = args.transcript_file
        file_ext = Path(transcript_path).suffix.lower()
        
        if file_ext == '.vtt':
            transcript = TranscriptParser.parse_webvtt(transcript_path)
        elif file_ext == '.srt':
            transcript = TranscriptParser.parse_srt(transcript_path)
        else:
            raise ValueError(f"Unsupported transcript format: {file_ext}. Use .vtt or .srt")
        
        print(f"   Loaded {len(transcript)} transcript entries")
        
        # Find segments
        print("🔍 Finding interesting segments...")
        segment_finder = SegmentFinder()
        segment_indices = segment_finder.search_keywords(transcript, args.keywords, args.cards)
        print(f"   Found {len(segment_indices)} segments")
        
        # Initialize components
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        summarizer = Summarizer()
        video_processor = VideoProcessor(args.output_dir)
        
        # Download video
        print("⬇️  Downloading video...")
        video_path = video_processor.download_video(args.youtube_url)
        
        # Process segments
        print("🎯 Processing segments...")
        segments = []
        
        for i, (start_idx, end_idx) in enumerate(segment_indices):
            print(f"   Processing segment {i+1}/{len(segment_indices)}...")
            
            # Get segment text and timing
            segment_entries = transcript[start_idx:end_idx+1]
            segment_text = ' '.join([entry.text for entry in segment_entries])
            start_time = segment_entries[0].start
            end_time = segment_entries[-1].end
            
            # Summarize segment
            summary = summarizer.summarize(segment_text, max_length=60)
            
            # Extract frame at middle of segment
            mid_time = (start_time + end_time) / 2
            thumbnail_filename = f"thumbnail_{i+1:03d}.png"
            thumbnail_path = video_processor.extract_frame(video_path, mid_time, thumbnail_filename)
            
            # Create YouTube link with timestamp
            video_id = HTMLGenerator._extract_video_id(args.youtube_url)
            youtube_link = f"https://www.youtube.com/watch?v={video_id}&t={int(start_time)}s"
            
            segment = Segment(
                start_time=start_time,
                end_time=end_time,
                summary=summary,
                thumbnail_path=thumbnail_path,
                youtube_link=youtube_link,
                transcript_text=segment_text
            )
            segments.append(segment)
        
        # Generate HTML page
        print("🌐 Generating HTML page...")
        html_path = HTMLGenerator.generate_page(
            args.youtube_url, 
            segments, 
            args.output_dir, 
            args.description
        )
        
        print("\n✅ Generation complete!")
        print(f"📁 Output directory: {output_dir.absolute()}")
        print(f"🌐 HTML file: {html_path}")
        print(f"🖼️  Thumbnails: {len(segments)} images generated")
        print("\n🚀 Ready to deploy to Netlify!")
        print(f"   1. Drag and drop the '{args.output_dir}' folder to Netlify")
        print("   2. Or push to Git and connect to Netlify")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logging.exception("Full error details:")
        sys.exit(1)

if __name__ == "__main__":
    main()