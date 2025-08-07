#!/usr/bin/env python3
"""
Interactive mode for YouTube Highlight Generator.
This script guides the user through the process of generating video highlights
with interactive prompts.
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import re
from youtube_transcript_api import YouTubeTranscriptApi
from generate_video_cards import (
    TranscriptParser,
    SegmentFinder,
    Summarizer,
    VideoProcessor,
    HTMLGenerator,
    Segment,
    TranscriptEntry
)

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
        width, height = 640, 360
        image = Image.new('RGB', (width, height), color='#2C3E50')
        draw = ImageDraw.Draw(image)

        try:
            title_font = ImageFont.truetype("Arial.ttf", 24)
            text_font = ImageFont.truetype("Arial.ttf", 16)
            time_font = ImageFont.truetype("Arial.ttf", 20)
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            time_font = ImageFont.load_default()

        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        time_text = f"{minutes:02d}:{seconds:02d}"

        for y in range(height):
            color_val = int(44 + (y / height) * 20)
            draw.line([(0, y), (width, y)], fill=(color_val, color_val + 10, color_val + 20))

        draw.text((width//2, 50), "Video Segment", font=title_font, fill='white', anchor='mm')

        time_bbox = draw.textbbox((0, 0), time_text, font=time_font)
        time_width = time_bbox[2] - time_bbox[0]
        time_height = time_bbox[3] - time_bbox[1]

        time_x = width - time_width - 20
        time_y = 20
        draw.rectangle([time_x - 10, time_y - 5, time_x + time_width + 10, time_y + time_height + 5],
                      fill='#E74C3C', outline='white')
        draw.text((time_x, time_y), time_text, font=time_font, fill='white')

        preview_text = segment_text[:100] + "..." if len(segment_text) > 100 else segment_text

        words = preview_text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if len(test_line) <= 40:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        start_y = height // 2 + 20
        for i, line in enumerate(lines[:4]):
            draw.text((width//2, start_y + i * 25), line, font=text_font, fill='#ECF0F1', anchor='mm')

        draw.rectangle([50, height - 60, width - 50, height - 50], fill='#3498DB', width=2)
        draw.text((width//2, height - 55), "Generated Highlight", font=text_font, fill='white', anchor='mm')

        output_path = self.output_dir / output_filename
        image.save(output_path, "PNG")

        print(f"Demo thumbnail created: {output_path}")
        return str(output_path)


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with an optional default value."""
    if default:
        return input(f"{prompt} (default: {default}): ") or default
    else:
        response = ""
        while not response:
            response = input(f"{prompt}: ")
            if not response:
                print("This field is required.")
        return response

def download_transcript(video_id: str, output_path: Path) -> bool:
    """Download transcript and save as a VTT file."""
    try:
        transcript_list = YouTubeTranscriptApi().list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en'])
        transcript_data = transcript.fetch()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for item in transcript_data:
                start = item['start']
                end = start + item['duration']

                start_h, start_rem = divmod(start, 3600)
                start_m, start_s = divmod(start_rem, 60)

                end_h, end_rem = divmod(end, 3600)
                end_m, end_s = divmod(end_rem, 60)

                start_time = f"{int(start_h):02}:{int(start_m):02}:{start_s:06.3f}"
                end_time = f"{int(end_h):02}:{int(end_m):02}:{end_s:06.3f}"

                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{item['text']}\n\n")

        print(f"Transcript downloaded successfully to {output_path}")
        return True
    except Exception as e:
        print(f"Could not download transcript: {e}")
        return False

def main():
    """Main function to run the interactive highlight generation."""
    print("🎬 Welcome to the Interactive YouTube Highlight Generator!")
    print("=" * 60)
    print("This tool will guide you through creating a video highlight page.")
    print()

    try:
        # 0. Ask for demo mode
        demo_mode = get_user_input("Run in demo mode (y/n)?", "y").lower() == 'y'
        if demo_mode:
            print("Running in  demo mode. Video will not be downloaded and thumbnails will be placeholders.")

        # 1. Get YouTube URL
        youtube_url = get_user_input("Enter the YouTube video URL")
        try:
            video_id = HTMLGenerator._extract_video_id(youtube_url)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

        # 2. Get transcript file
        transcript_path = None
        if get_user_input("Automatically download transcript (y/n)?", "y").lower() == 'y':
            transcript_path_str = f"{video_id}.vtt"
            if download_transcript(video_id, Path(transcript_path_str)):
                transcript_path = Path(transcript_path_str)

        if not transcript_path:
            while True:
                transcript_path_str = get_user_input("Enter the path to your transcript file (.vtt or .srt)")
                transcript_path = Path(transcript_path_str)
                if transcript_path.is_file() and transcript_path.suffix.lower() in ['.vtt', '.srt']:
                    break
                else:
                    print("❌ Invalid file path or format. Please provide a valid .vtt or .srt file.")

        # 3. Get description
        description = get_user_input("Enter a description for the highlight page (optional)")

        # 4. Get keywords
        keywords_str = get_user_input("Enter keywords to find segments (space-separated)", "introduction conclusion demo")
        keywords = keywords_str.split()

        # 5. Get number of cards
        while True:
            try:
                cards_str = get_user_input("How many highlight cards to generate?", "4")
                num_cards = int(cards_str)
                if num_cards > 0:
                    break
                else:
                    print("Please enter a positive number.")
            except ValueError:
                print("Please enter a valid number.")

        # 6. Get output directory
        output_dir_str = get_user_input("Enter the output directory name", "output")
        output_dir = Path(output_dir_str)
        output_dir.mkdir(parents=True, exist_ok=True)

        print("\n👍 Great! All inputs received. Starting the process...\n")

        print("📝 Parsing transcript...")
        file_ext = transcript_path.suffix.lower()
        if file_ext == '.vtt':
            transcript = TranscriptParser.parse_webvtt(str(transcript_path))
        elif file_ext == '.srt':
            transcript = TranscriptParser.parse_srt(str(transcript_path))
        else:
            raise ValueError(f"Unsupported transcript format: {file_ext}")
        print(f"   Loaded {len(transcript)} transcript entries")

        print("🔍 Finding interesting segments...")
        segment_finder = SegmentFinder()
        segment_indices = segment_finder.search_keywords(transcript, keywords, num_cards)
        print(f"   Found {len(segment_indices)} segments")

        if demo_mode:
            summarizer = DemoSummarizer()
            thumbnail_generator = DemoThumbnailGenerator(output_dir_str)
        else:
            summarizer = Summarizer()
            video_processor = VideoProcessor(output_dir_str)
            print("⬇️  Downloading video (this might take a while)...")
            video_path = video_processor.download_video(youtube_url)

        print("🎯 Processing segments...")
        segments = []
        for i, (start_idx, end_idx) in enumerate(segment_indices):
            print(f"   Processing segment {i+1}/{len(segment_indices)}...")

            segment_entries = transcript[start_idx:end_idx+1]
            segment_text = ' '.join([entry.text for entry in segment_entries])
            start_time = segment_entries[0].start
            end_time = segment_entries[-1].end

            summary = summarizer.summarize(segment_text, max_length=60)

            mid_time = (start_time + end_time) / 2
            thumbnail_filename = f"thumbnail_{i+1:03d}.png"

            if demo_mode:
                thumbnail_path = thumbnail_generator.create_placeholder_thumbnail(mid_time, segment_text, thumbnail_filename)
            else:
                thumbnail_path = video_processor.extract_frame(video_path, mid_time, thumbnail_filename)

            video_id = HTMLGenerator._extract_video_id(youtube_url)
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

        print("🌐 Generating HTML page...")
        html_path = HTMLGenerator.generate_page(
            youtube_url,
            segments,
            output_dir_str,
            description
        )

        print("\n✅ Generation complete!")
        print(f"📁 Output directory: {output_dir.absolute()}")
        print(f"🌐 HTML file: {Path(html_path).absolute()}")
        if demo_mode:
            print("\n💡 Demo mode was enabled. Thumbnails are placeholders.")
        print("\n🚀 Ready to deploy to Netlify!")

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Process cancelled by user. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
