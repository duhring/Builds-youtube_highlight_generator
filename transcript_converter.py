#!/usr/bin/env python3
"""
Transcript Converter Utility
Converts pasted transcript text with timestamps into properly formatted WebVTT files.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional

def parse_pasted_transcript(text: str) -> List[Tuple[str, str]]:
    """
    Parse various transcript formats and extract timestamp-text pairs.
    
    Supports formats like:
    - "0:15 Some text here"
    - "00:15 Some text here"  
    - "1:23:45 Some text here"
    - "0:15: Some text here"
    - "[0:15] Some text here"
    - "0:15 - Some text here"
    - Timestamps on separate lines from text
    """
    
    entries = []
    lines = text.strip().split('\n')
    
    # First pass: try parsing lines with timestamps and text together
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try various timestamp patterns with text on same line
        patterns = [
            r'^(\d{1,2}:\d{2}:\d{2})\s*[-:]?\s*(.+)$',  # H:MM:SS format
            r'^(\d{1,2}:\d{2})\s*[-:]?\s*(.+)$',       # M:SS or MM:SS format
            r'^\[(\d{1,2}:\d{2}:\d{2})\]\s*(.+)$',     # [H:MM:SS] format
            r'^\[(\d{1,2}:\d{2})\]\s*(.+)$',           # [M:SS] format
            r'^(\d{1,2}:\d{2}:\d{2})\s*-\s*(.+)$',     # H:MM:SS - text
            r'^(\d{1,2}:\d{2})\s*-\s*(.+)$',           # M:SS - text
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                timestamp = match.group(1)
                text = match.group(2).strip()
                if text:  # Only add if there's actual text
                    entries.append((timestamp, text))
                break
    
    # If we found entries, return them
    if entries:
        return entries
    
    # Second pass: handle timestamps on separate lines
    # This format looks like:
    # 0:15
    # Some text here
    # 0:30
    # More text here
    
    current_timestamp = None
    current_text_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this line is just a timestamp
        timestamp_patterns = [
            r'^(\d{1,2}:\d{2}:\d{2})$',  # H:MM:SS
            r'^(\d{1,2}:\d{2})$',        # M:SS or MM:SS
        ]
        
        is_timestamp = False
        for pattern in timestamp_patterns:
            match = re.match(pattern, line)
            if match:
                # Save previous entry if we have one
                if current_timestamp and current_text_lines:
                    combined_text = ' '.join(current_text_lines).strip()
                    if combined_text and not combined_text.startswith('■'):  # Skip chapter markers
                        entries.append((current_timestamp, combined_text))
                
                # Start new entry
                current_timestamp = match.group(1)
                current_text_lines = []
                is_timestamp = True
                break
        
        if not is_timestamp:
            # This is text content - skip chapter markers and empty lines
            if line and not line.startswith('■') and not line.startswith('♪'):
                current_text_lines.append(line)
    
    # Don't forget the last entry
    if current_timestamp and current_text_lines:
        combined_text = ' '.join(current_text_lines).strip()
        if combined_text and not combined_text.startswith('■'):
            entries.append((current_timestamp, combined_text))
    
    return entries

def normalize_timestamp(timestamp: str) -> str:
    """Convert timestamp to H:MM:SS.mmm format required by WebVTT."""
    
    # Split by colons
    parts = timestamp.split(':')
    
    if len(parts) == 2:
        # MM:SS format
        minutes, seconds = parts
        hours = "00"
    elif len(parts) == 3:
        # H:MM:SS format
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")
    
    # Ensure proper formatting
    hours = hours.zfill(2)
    minutes = minutes.zfill(2)
    seconds = seconds.zfill(2)
    
    # Add milliseconds if not present
    if '.' not in seconds:
        seconds += ".000"
    elif len(seconds.split('.')[1]) < 3:
        # Pad milliseconds to 3 digits
        seconds = seconds.split('.')[0] + '.' + seconds.split('.')[1].ljust(3, '0')
    
    return f"{hours}:{minutes}:{seconds}"

def estimate_end_time(start_time: str, text: str, next_start_time: Optional[str] = None) -> str:
    """Estimate end time based on text length and next timestamp."""
    
    # Parse start time to seconds
    parts = start_time.split(':')
    if len(parts) == 3:
        hours, minutes, seconds_ms = parts
        seconds, ms = seconds_ms.split('.')
        start_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(ms) / 1000
    else:
        raise ValueError(f"Invalid timestamp format: {start_time}")
    
    # Estimate duration based on text length (roughly 3 words per second)
    words = len(text.split())
    estimated_duration = max(2.0, words / 3.0)  # Minimum 2 seconds
    
    if next_start_time:
        # Parse next start time
        parts = next_start_time.split(':')
        if len(parts) == 3:
            hours, minutes, seconds_ms = parts
            seconds, ms = seconds_ms.split('.')
            next_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(ms) / 1000
            
            # Use the minimum of estimated duration and time to next segment
            estimated_duration = min(estimated_duration, next_seconds - start_seconds - 0.1)
    
    # Calculate end time
    end_seconds = start_seconds + estimated_duration
    
    # Convert back to timestamp format
    hours = int(end_seconds // 3600)
    minutes = int((end_seconds % 3600) // 60)
    seconds = int(end_seconds % 60)
    milliseconds = int((end_seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def create_vtt_file(entries: List[Tuple[str, str]], output_path: str):
    """Create a WebVTT file from timestamp-text pairs."""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        
        for i, (timestamp, text) in enumerate(entries):
            # Normalize timestamp
            start_time = normalize_timestamp(timestamp)
            
            # Estimate end time
            next_timestamp = entries[i + 1][0] if i + 1 < len(entries) else None
            next_start_time = normalize_timestamp(next_timestamp) if next_timestamp else None
            end_time = estimate_end_time(start_time, text, next_start_time)
            
            # Write WebVTT entry
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")
    
    print(f"✅ WebVTT file created: {output_path}")

def interactive_transcript_creator():
    """Interactive mode for creating transcripts."""
    
    print("🎬 Transcript to WebVTT Converter")
    print("=" * 40)
    print("\nSupported formats:")
    print("  • 0:15 Some text here")
    print("  • 1:23:45 Some text here") 
    print("  • [0:15] Some text here")
    print("  • 0:15 - Some text here")
    print("  • 0:15: Some text here")
    print("\n📝 Paste your transcript below (press Ctrl+D when done):")
    print("-" * 40)
    
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
        return
    
    # Parse the transcript
    print("\n🔍 Parsing transcript...")
    entries = parse_pasted_transcript(text)
    
    if not entries:
        print("❌ No valid timestamp entries found")
        print("Make sure your transcript includes timestamps in a supported format")
        return
    
    print(f"   Found {len(entries)} entries")
    
    # Show preview
    print("\n📋 Preview of first few entries:")
    for i, (timestamp, text) in enumerate(entries[:3]):
        print(f"   {timestamp}: {text[:50]}{'...' if len(text) > 50 else ''}")
    
    if len(entries) > 3:
        print(f"   ... and {len(entries) - 3} more entries")
    
    # Get output filename
    print()
    filename = input("Enter output filename (default: 'transcript.vtt'): ").strip()
    if not filename:
        filename = "transcript.vtt"
    
    if not filename.endswith('.vtt'):
        filename += '.vtt'
    
    # Create the file
    create_vtt_file(entries, filename)
    print(f"\n🎉 Success! You can now use '{filename}' with the highlight generator")

def main():
    """Main function for command line usage."""
    
    if len(sys.argv) > 1:
        # Command line mode with file input
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else 'transcript.vtt'
        
        with open(input_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        entries = parse_pasted_transcript(text)
        create_vtt_file(entries, output_file)
    else:
        # Interactive mode
        interactive_transcript_creator()

if __name__ == "__main__":
    main()