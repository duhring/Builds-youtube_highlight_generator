#!/usr/bin/env python3
"""
Demo version of YouTube Highlight Generator that works without video download.
Perfect for testing the transcript parsing and HTML generation.
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
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Import transcript converter functions
try:
    from transcript_converter import parse_pasted_transcript, create_vtt_file
    HAS_TRANSCRIPT_CONVERTER = True
except ImportError:
    HAS_TRANSCRIPT_CONVERTER = False

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
    def _time_to_seconds(time_str: str) -> float:
        """Convert WebVTT time format (HH:MM:SS.mmm) to seconds."""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1])
        
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

class SegmentFinder:
    """Identifies interesting segments in the transcript based on keywords."""
    
    @staticmethod
    def search_keywords(transcript: List[TranscriptEntry], keywords: List[str], num_cards: int) -> List[Tuple[int, int]]:
        """Find segments based on keywords."""
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

class DemoSummarizer:
    """Demo summarizer using simple extractive method."""
    
    def summarize(self, text: str, max_length: int = 50) -> str:
        """Simple extractive summary - first sentence or first 30 words."""
        if not text.strip():
            return "No content available."
        
        # Clean the text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If text is already short, return as-is
        if len(text.split()) <= 10:
            return text
        
        # Get first sentence
        sentences = re.split(r'[.!?]+', text)
        if sentences and len(sentences[0].strip()) > 0:
            return sentences[0].strip() + "."
        
        # If no sentences, take first 30 words
        words = text.split()
        if len(words) > 30:
            return ' '.join(words[:30]) + "..."
        
        return text

class DemoThumbnailGenerator:
    """Creates placeholder thumbnails for demo purposes."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create_placeholder_thumbnail(self, timestamp: float, segment_text: str, output_filename: str) -> str:
        """Create a placeholder thumbnail with timestamp and text preview."""
        # Create a 640x360 image (16:9 aspect ratio)
        width, height = 640, 360
        image = Image.new('RGB', (width, height), color='#2C3E50')
        draw = ImageDraw.Draw(image)
        
        # Try to use a system font, fallback to default
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
            text_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
            time_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 20)
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            time_font = ImageFont.load_default()
        
        # Add timestamp
        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        time_text = f"{minutes:02d}:{seconds:02d}"
        
        # Draw background gradient effect
        for y in range(height):
            color_val = int(44 + (y / height) * 20)  # Gradient from dark to slightly lighter
            draw.line([(0, y), (width, y)], fill=(color_val, color_val + 10, color_val + 20))
        
        # Add title
        draw.text((width//2, 50), "Video Segment", font=title_font, fill='white', anchor='mm')
        
        # Add timestamp in a box
        time_bbox = draw.textbbox((0, 0), time_text, font=time_font)
        time_width = time_bbox[2] - time_bbox[0]
        time_height = time_bbox[3] - time_bbox[1]
        
        # Draw timestamp background
        time_x = width - time_width - 20
        time_y = 20
        draw.rectangle([time_x - 10, time_y - 5, time_x + time_width + 10, time_y + time_height + 5], 
                      fill='#E74C3C', outline='white')
        draw.text((time_x, time_y), time_text, font=time_font, fill='white')
        
        # Add segment text preview (first 100 characters)
        preview_text = segment_text[:100] + "..." if len(segment_text) > 100 else segment_text
        
        # Word wrap the preview text
        words = preview_text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            # Rough character limit per line
            if len(test_line) <= 40:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Draw text lines
        start_y = height // 2 + 20
        for i, line in enumerate(lines[:4]):  # Max 4 lines
            draw.text((width//2, start_y + i * 25), line, font=text_font, fill='#ECF0F1', anchor='mm')
        
        # Add decorative elements
        draw.rectangle([50, height - 60, width - 50, height - 50], fill='#3498DB', width=2)
        draw.text((width//2, height - 55), "Generated Highlight", font=text_font, fill='white', anchor='mm')
        
        # Save the image
        output_path = self.output_dir / output_filename
        image.save(output_path, "PNG")
        
        print(f"Demo thumbnail created: {output_path}")
        return str(output_path)

class HTMLGenerator:
    """Generates the static HTML page with embedded video and cards."""
    
    @staticmethod
    def generate_page(youtube_url: str, segments: List[Segment], output_dir: str, description: str = ""):
        """Generate complete HTML page with CSS and JavaScript."""
        
        # Extract video ID from YouTube URL
        video_id = HTMLGenerator._extract_video_id(youtube_url)
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Highlights - {description}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }}
        
        h1 {{
            text-align: center;
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5rem;
            font-weight: 700;
        }}
        
        .description {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1rem;
        }}
        
        .demo-notice {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
            font-weight: 500;
        }}
        
        .video-container {{
            position: relative;
            width: 100%;
            padding-bottom: 56.25%; /* 16:9 aspect ratio */
            margin-bottom: 40px;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}
        
        .video-container iframe {{
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
            margin-top: 20px;
        }}
        
        .highlight-card {{
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            cursor: pointer;
        }}
        
        .highlight-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
        }}
        
        .card-thumbnail {{
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #f0f0f0;
        }}
        
        .card-content {{
            padding: 20px;
        }}
        
        .card-summary {{
            color: #333;
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 15px;
        }}
        
        .card-timestamp {{
            color: #666;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        
        .card-link {{
            display: inline-block;
            margin-top: 10px;
            padding: 8px 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: transform 0.2s ease;
        }}
        
        .card-link:hover {{
            transform: scale(1.05);
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 20px;
                margin: 10px;
            }}
            
            h1 {{
                font-size: 2rem;
            }}
            
            .highlights-grid {{
                grid-template-columns: 1fr;
                gap: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Highlights</h1>
        {f'<p class="description">{description}</p>' if description else ''}
        
        <div class="demo-notice">
            🎬 Demo Mode - Placeholder thumbnails generated without video download
        </div>
        
        <div class="video-container">
            <iframe src="https://www.youtube.com/embed/{video_id}" 
                    allowfullscreen>
            </iframe>
        </div>
        
        <div class="highlights-grid">
"""
        
        # Add cards for each segment
        for i, segment in enumerate(segments):
            thumbnail_filename = Path(segment.thumbnail_path).name
            start_minutes = int(segment.start_time // 60)
            start_seconds = int(segment.start_time % 60)
            
            html_content += f"""
            <div class="highlight-card" onclick="window.open('{segment.youtube_link}', '_blank')">
                <img src="{thumbnail_filename}" alt="Video thumbnail" class="card-thumbnail">
                <div class="card-content">
                    <p class="card-summary">{segment.summary}</p>
                    <p class="card-timestamp">Starts at {start_minutes:02d}:{start_seconds:02d}</p>
                    <a href="{segment.youtube_link}" class="card-link" target="_blank">
                        Watch Segment
                    </a>
                </div>
            </div>
"""
        
        html_content += """
        </div>
    </div>
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
        
        return "dQw4w9WgXcQ"  # Default demo video ID

def create_transcript_interactively():
    """Create a transcript file from pasted text."""
    print("\n📝 Create Transcript from Pasted Text")
    print("=" * 45)
    print("Supported formats:")
    print("  • 0:15 Some text here")
    print("  • 1:23:45 Some text here") 
    print("  • [0:15] Some text here")
    print("  • 0:15 - Some text here")
    print("  • 0:15: Some text here")
    print("\nPaste your transcript below (press Ctrl+D when done):")
    print("-" * 45)
    
    # Read multiline input
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    
    text = '\n'.join(lines)
    
    if not text.strip():
        print("❌ No transcript text provided")
        sys.exit(1)
    
    # Parse the transcript
    print("\n🔍 Parsing transcript...")
    entries = parse_pasted_transcript(text)
    
    if not entries:
        print("❌ No valid timestamp entries found")
        print("Make sure your transcript includes timestamps in a supported format")
        sys.exit(1)
    
    print(f"   Found {len(entries)} entries")
    
    # Get output filename
    filename = input("Enter transcript filename (default: 'created_transcript.vtt'): ").strip()
    if not filename:
        filename = "created_transcript.vtt"
    
    if not filename.endswith('.vtt'):
        filename += '.vtt'
    
    # Create the file
    create_vtt_file(entries, filename)
    return filename

def get_interactive_input():
    """Get input interactively from user."""
    print("🎬 YouTube Highlight Generator (Demo Mode) - Interactive Setup")
    print("=" * 60)
    
    # Get YouTube URL
    youtube_url = input("Enter YouTube URL: ").strip()
    if not youtube_url:
        print("Error: YouTube URL is required")
        sys.exit(1)
    
    # Get transcript file
    print("\nTranscript options:")
    vtt_files = [f for f in os.listdir('.') if f.endswith('.vtt')]
    
    options = []
    if vtt_files:
        for i, file in enumerate(vtt_files, 1):
            print(f"  {i}. {file}")
            options.append(('file', file))
    
    next_num = len(options) + 1
    if HAS_TRANSCRIPT_CONVERTER:
        print(f"  {next_num}. Create transcript from pasted text")
        options.append(('create', None))
        next_num += 1
    
    print(f"  {next_num}. Enter custom file path")
    options.append(('custom', None))
    
    try:
        choice = int(input(f"\nSelect option (1-{len(options)}): "))
        if 1 <= choice <= len(options):
            option_type, file_path = options[choice - 1]
            
            if option_type == 'file':
                transcript_file = file_path
            elif option_type == 'create':
                transcript_file = create_transcript_interactively()
            else:  # custom
                transcript_file = input("Enter transcript file path: ").strip()
        else:
            transcript_file = input("Enter transcript file path: ").strip()
    except ValueError:
        transcript_file = input("Enter transcript file path: ").strip()
    
    if not transcript_file or not os.path.exists(transcript_file):
        print("Error: Valid transcript file is required")
        sys.exit(1)
    
    # Get optional parameters
    description = input("Enter video description (optional): ").strip()
    
    keywords_input = input("Enter keywords separated by spaces (optional): ").strip()
    keywords = keywords_input.split() if keywords_input else []
    
    try:
        cards = int(input("Number of highlight cards to generate (default 4): ").strip() or "4")
    except ValueError:
        cards = 4
    
    output_dir = input("Output directory (default 'demo_output'): ").strip() or "demo_output"
    
    return {
        'youtube_url': youtube_url,
        'transcript_file': transcript_file,
        'description': description,
        'keywords': keywords,
        'cards': cards,
        'output_dir': output_dir
    }

def main():
    parser = argparse.ArgumentParser(description='Generate YouTube highlight page (Demo Mode)')
    parser.add_argument('youtube_url', nargs='?', help='YouTube video URL')
    parser.add_argument('transcript_file', nargs='?', help='Path to transcript file (.vtt or .srt)')
    parser.add_argument('--description', default='', help='Description for the page')
    parser.add_argument('--keywords', nargs='*', default=[], help='Keywords to search for segments')
    parser.add_argument('--cards', type=int, default=4, help='Number of highlight cards to generate')
    parser.add_argument('--output-dir', default='demo_output', help='Output directory')
    
    args = parser.parse_args()
    
    # If required arguments are missing, get them interactively
    if not args.youtube_url or not args.transcript_file:
        interactive_args = get_interactive_input()
        args.youtube_url = interactive_args['youtube_url']
        args.transcript_file = interactive_args['transcript_file']
        args.description = interactive_args['description']
        args.keywords = interactive_args['keywords']
        args.cards = interactive_args['cards']
        args.output_dir = interactive_args['output_dir']
    
    try:
        print("🎬 YouTube Highlight Generator (Demo Mode)")
        print("=" * 50)
        
        # Parse transcript
        print("📝 Parsing transcript...")
        transcript_path = args.transcript_file
        file_ext = Path(transcript_path).suffix.lower()
        
        if file_ext == '.vtt':
            transcript = TranscriptParser.parse_webvtt(transcript_path)
        else:
            raise ValueError(f"Demo mode only supports .vtt files. Got: {file_ext}")
        
        print(f"   Loaded {len(transcript)} transcript entries")
        
        # Find segments
        print("🔍 Finding interesting segments...")
        segment_finder = SegmentFinder()
        segment_indices = segment_finder.search_keywords(transcript, args.keywords, args.cards)
        print(f"   Found {len(segment_indices)} segments")
        
        # Initialize components
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        summarizer = DemoSummarizer()
        thumbnail_generator = DemoThumbnailGenerator(args.output_dir)
        
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
            
            # Create placeholder thumbnail
            mid_time = (start_time + end_time) / 2
            thumbnail_filename = f"thumbnail_{i+1:03d}.png"
            thumbnail_path = thumbnail_generator.create_placeholder_thumbnail(mid_time, segment_text, thumbnail_filename)
            
            # Create YouTube link with timestamp
            video_id = HTMLGenerator._extract_video_id(args.youtube_url)
            youtube_link = f"https://www.youtube.com/watch?v={video_id}&t={int(start_time)}s"
            
            segment = Segment(
                start_time=start_time,
                end_time=end_time,
                summary=summary,
                thumbnail_path=thumbnail_path,
                youtube_link=youtube_link
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
        
        print("\n✅ Demo generation complete!")
        print(f"📁 Output directory: {output_dir.absolute()}")
        print(f"🌐 HTML file: {html_path}")
        print(f"🖼️  Thumbnails: {len(segments)} placeholder images generated")
        print(f"\n🚀 Open {html_path} in your browser to see the result!")
        print("\n💡 This demo shows how the system works without downloading videos.")
        print("   For production use, install full dependencies and use the main script.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logging.exception("Full error details:")
        sys.exit(1)

if __name__ == "__main__":
    main()