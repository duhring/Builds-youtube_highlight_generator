#!/usr/bin/env python3
"""Test script to check all imports."""

print("Testing imports...")

try:
    import sys
    print("✅ sys imported")
except ImportError as e:
    print(f"❌ sys failed: {e}")

try:
    from pytube import YouTube
    print("✅ pytube imported")
except ImportError as e:
    print(f"❌ pytube failed: {e}")

try:
    from PIL import Image
    print("✅ PIL imported")
except ImportError as e:
    print(f"❌ PIL failed: {e}")

try:
    import numpy as np
    print("✅ numpy imported")
except ImportError as e:
    print(f"❌ numpy failed: {e}")

# Test MoviePy different ways
print("\nTesting MoviePy imports:")
try:
    from moviepy.editor import VideoFileClip
    print("✅ moviepy.editor.VideoFileClip imported")
except ImportError as e:
    print(f"❌ moviepy.editor failed: {e}")
    
    try:
        from moviepy import VideoFileClip  
        print("✅ moviepy.VideoFileClip imported")
    except ImportError as e:
        print(f"❌ moviepy direct failed: {e}")
        
        try:
            import moviepy
            print(f"✅ moviepy base imported (version: {moviepy.__version__})")
            print(f"   Available: {dir(moviepy)}")
        except ImportError as e:
            print(f"❌ moviepy base failed: {e}")

# Test transformers
try:
    from transformers import pipeline
    print("✅ transformers imported")
except ImportError as e:
    print(f"❌ transformers failed: {e}")

print("\nImport test complete!")