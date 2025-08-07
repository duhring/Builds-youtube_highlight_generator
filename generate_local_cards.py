#!/usr/bin/env python3
"""
generate_local_cards.py
Download a YouTube video (yt-dlp), parse an SRT/VTT transcript, pick highlight segments,
grab thumbnails (MoviePy), and render a local HTML page with an HTML5 <video> player
that seeks on card click.
"""
import argparse, os, re, subprocess, sys, tempfile, math, shutil
from dataclasses import dataclass
from typing import List, Tuple
from pathlib import Path

# Lightweight template render (Jinja-style {{ }}, {% for %} only for our simple case)
def render_template(template_text: str, context: dict) -> str:
    # VERY tiny/stupid renderer: handle {% for c in cards %} ... {% endfor %} and {{ var }}
    # Good enough for this self-contained script (avoids Jinja2 dependency).
    def replace_vars(txt, local_ctx):
        return re.sub(r"{{\s*([^}]+)\s*}}", lambda m: str(eval(m.group(1), {}, local_ctx)), txt)

    out = []
    tokens = re.split(r"(\{%.*?%\})", template_text, flags=re.DOTALL)
    i = 0
    local_ctx = dict(context)
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("{%"):
            # only for loops
            m = re.match(r"\{% for (\w+) in ([^%]+) %\}", tok.strip())
            if m:
                var_name, list_expr = m.group(1), m.group(2).strip()
                # find endfor
                body = []
                i += 1
                depth = 1
                while i < len(tokens):
                    if tokens[i].strip().startswith("{% endfor %}"):
                        depth -= 1
                        if depth == 0:
                            break
                    body.append(tokens[i])
                    i += 1
                seq = eval(list_expr, {}, local_ctx)
                for item in seq:
                    local_ctx[var_name] = item
                    chunk = "".join(body)
                    out.append(replace_vars(chunk, local_ctx))
                # skip the endfor
            else:
                # ignore anything else
                pass
        else:
            out.append(replace_vars(tok, local_ctx))
        i += 1
    return "".join(out)

@dataclass
class Segment:
    start: float
    end: float
    title: str
    mid: float
    def to_card(self, idx:int):
        return {
            "title": self.title.strip() or f"Segment {idx+1}",
            "ts": seconds_to_clock(self.start),
            "start_seconds": round(self.start),
            "thumbnail": f"thumbnail_{idx+1:03d}.png",
        }

def ffprobe_duration(path: str) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ], text=True).strip()
        return float(out)
    except Exception:
        return 0.0

def seconds_to_clock(s: float) -> str:
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:d}:{sec:02d}"

def parse_vtt(fp: str) -> List[Tuple[float, float, str]]:
    """Very simple VTT parser; supports standard cues."""
    cues = []
    ts_re = re.compile(r"(\d+):(\d{2}):(\d{2}\.\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2}\.\d{3})|(\d{1,2}):(\d{2})\.(\d{3})\s*-->\s*(\d{1,2}):(\d{2})\.(\d{3})")
    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        block = []
        for line in f:
            line = line.strip("\n")
            if line.strip() == "":
                if block:
                    # process block
                    text_lines = []
                    start = end = None
                    for b in block:
                        m = ts_re.search(b)
                        if m:
                            if m.group(1) is not None:
                                h1,m1,s1 = int(m.group(1)), int(m.group(2)), float(m.group(3))
                                h2,m2,s2 = int(m.group(4)), int(m.group(5)), float(m.group(6))
                                start = h1*3600+m1*60+s1
                                end   = h2*3600+m2*60+s2
                            else:
                                m1,s1,ms1 = int(m.group(7)), int(m.group(8)), int(m.group(9))
                                m2_,s2_,ms2 = int(m.group(10)), int(m.group(11)), int(m.group(12))
                                start = m1*60 + s1 + ms1/1000
                                end   = m2_*60 + s2_ + ms2/1000
                        else:
                            # text line
                            txt = re.sub(r"<[^>]+>", "", b).strip()
                            if txt:
                                text_lines.append(txt)
                    if start is not None and end is not None and text_lines:
                        cues.append((start, end, " ".join(text_lines)))
                    block = []
            else:
                block.append(line)
        # last block
        if block:
            text_lines = []
            start = end = None
            for b in block:
                m = ts_re.search(b)
                if m:
                    if m.group(1) is not None:
                        h1,m1,s1 = int(m.group(1)), int(m.group(2)), float(m.group(3))
                        h2,m2,s2 = int(m.group(4)), int(m.group(5)), float(m.group(6))
                        start = h1*3600+m1*60+s1
                        end   = h2*3600+m2*60+s2
                    else:
                        m1,s1,ms1 = int(m.group(7)), int(m.group(8)), int(m.group(9))
                        m2_,s2_,ms2 = int(m.group(10)), int(m.group(11)), int(m.group(12))
                        start = m1*60 + s1 + ms1/1000
                        end   = m2_*60 + s2_ + ms2/1000
                else:
                    txt = re.sub(r"<[^>]+>", "", b).strip()
                    if txt:
                        text_lines.append(txt)
            if start is not None and end is not None and text_lines:
                cues.append((start, end, " ".join(text_lines)))
    return cues

def parse_srt(fp: str) -> List[Tuple[float, float, str]]:
    # Very small SRT parser
    cues = []
    ts_re = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")
    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        block = []
        for line in f:
            line = line.strip("\n")
            if not line.strip():
                if block:
                    start = end = None
                    texts = []
                    for b in block:
                        m = ts_re.search(b)
                        if m:
                            h1,m1,s1,ms1 = map(int, m.groups()[0:4])
                            h2,m2,s2,ms2 = map(int, m.groups()[4:8])
                            start = h1*3600 + m1*60 + s1 + ms1/1000.0
                            end   = h2*3600 + m2*60 + s2 + ms2/1000.0
                        else:
                            if b.isdigit():  # index line
                                continue
                            txt = re.sub(r"<[^>]+>", "", b).strip()
                            if txt:
                                texts.append(txt)
                    if start is not None and end is not None and texts:
                        cues.append((start, end, " ".join(texts)))
                    block = []
            else:
                block.append(line)
        if block:
            start = end = None
            texts = []
            for b in block:
                m = ts_re.search(b)
                if m:
                    h1,m1,s1,ms1 = map(int, m.groups()[0:4])
                    h2,m2,s2,ms2 = map(int, m.groups()[4:8])
                    start = h1*3600 + m1*60 + s1 + ms1/1000.0
                    end   = h2*3600 + m2*60 + s2 + ms2/1000.0
                else:
                    if b.isdigit(): continue
                    txt = re.sub(r"<[^>]+>", "", b).strip()
                    if txt: texts.append(txt)
            if start is not None and end is not None and texts:
                cues.append((start, end, " ".join(texts)))
    return cues

def pick_segments(cues: List[Tuple[float,float,str]], keywords: List[str], n_cards: int, total_duration: float) -> List[Segment]:
    # keyword-first: pick first occurrence of each keyword; pad remainder with even splits
    segments = []
    used_times = []
    lower = [(s,e,t.lower(),t) for s,e,t in cues]
    for kw in keywords:
        kw_l = kw.lower()
        for s,e,tl,orig in lower:
            if kw_l in tl:
                start = max(0.0, s - 10.0)
                end = min(total_duration, e + 10.0)
                title = orig[:120]
                mid = (start + end) / 2.0
                if not any(abs(mid - u) < 10 for u in used_times):
                    segments.append(Segment(start, end, title, mid))
                    used_times.append(mid)
                    break
    # fill remaining by even splits
    if len(segments) < n_cards and total_duration > 0:
        remain = n_cards - len(segments)
        step = total_duration / (remain + 1)
        for i in range(remain):
            start = max(0.0, i*step)
            end = min(total_duration, start + min(60.0, step))  # cap 60s
            title = f"Highlight at {seconds_to_clock(start)}"
            mid = (start + end)/2.0
            if not any(abs(mid - u) < 10 for u in used_times):
                segments.append(Segment(start, end, title, mid))
                used_times.append(mid)
    # sort by time and truncate to n_cards
    segments.sort(key=lambda s:s.start)
    return segments[:n_cards]

def ensure_ffmpeg():
    try:
        subprocess.check_output(["ffmpeg", "-hide_banner", "-version"], text=True)
        subprocess.check_output(["ffprobe", "-hide_banner", "-version"], text=True)
    except Exception:
        print("ffmpeg/ffprobe not found. Please install with Homebrew: brew install ffmpeg", file=sys.stderr)
        sys.exit(2)

def download_video(url:str, out_dir:Path) -> Path:
    # prefers mp4; merge best video+audio into mp4
    out_path = out_dir / "video.mp4"
    cmd = [
        "yt-dlp",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "-o", str(out_dir / "video.%(ext)s"),
        "--merge-output-format", "mp4",
        url
    ]
    print("Downloading video with yt-dlp...")
    subprocess.check_call(cmd)
    # find resulting file (video.mp4 or video.mkv then renamed)
    candidates = list(out_dir.glob("video.*"))
    if not candidates:
        raise RuntimeError("yt-dlp did not produce a video file")
    # rename first candidate to video.mp4 if needed
    if candidates[0].name != "video.mp4":
        shutil.move(str(candidates[0]), str(out_path))
    return out_path

def extract_thumbnail(video_path:Path, t:float, out_path:Path):
    # use moviepy for simplicity
    from moviepy.editor import VideoFileClip
    with VideoFileClip(str(video_path)) as clip:
        frame = clip.get_frame(t)
        from PIL import Image
        img = Image.fromarray(frame)
        img.save(out_path)

def main():
    p = argparse.ArgumentParser(description="Generate highlight cards with local HTML5 video embed")
    p.add_argument("youtube_url", help="YouTube video URL")
    p.add_argument("transcript_file", help="Path to .vtt or .srt transcript")
    p.add_argument("--description", default="Video highlights", help="Description for the page")
    p.add_argument("--keywords", nargs="*", default=[], help="Keywords to prioritize for segments")
    p.add_argument("--cards", type=int, default=4, help="Number of cards to create")
    p.add_argument("--output-dir", default="output", help="Output directory")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    static_dir = out_dir / "static"
    static_dir.mkdir(exist_ok=True)

    ensure_ffmpeg()

    # Download video
    video_path = download_video(args.youtube_url, out_dir)

    # Duration
    duration = ffprobe_duration(str(video_path))

    # Parse transcript
    transcript_path = Path(args.transcript_file)
    if transcript_path.suffix.lower() == ".vtt":
        cues = parse_vtt(str(transcript_path))
    elif transcript_path.suffix.lower() == ".srt":
        cues = parse_srt(str(transcript_path))
    else:
        print("Transcript must be .vtt or .srt", file=sys.stderr)
        sys.exit(1)

    # Pick segments
    segments = pick_segments(cues, args.keywords or [], args.cards, duration or 0)

    # Thumbnails
    for i, seg in enumerate(segments):
        thumb = out_dir / f"thumbnail_{i+1:03d}.png"
        t = max(0.0, min(duration - 0.5, seg.mid)) if duration else seg.mid
        extract_thumbnail(video_path, t, thumb)

    # Copy assets
    # Expect the script to be run from repo root where templates/static live.
    # If not, fall back to embedded copies (we'll write them next to script).
    repo_templates = Path(__file__).resolve().parent / "templates" / "local-player.html"
    repo_js = Path(__file__).resolve().parent / "static" / "player.js"
    if repo_templates.exists():
        template_text = repo_templates.read_text(encoding="utf-8")
    else:
        template_text = DEFAULT_TEMPLATE_TEXT
    if repo_js.exists():
        shutil.copyfile(repo_js, static_dir / "player.js")
    else:
        (static_dir / "player.js").write_text(DEFAULT_PLAYER_JS, encoding="utf-8")

    # Render HTML
    cards = [s.to_card(i) for i, s in enumerate(segments)]
    ctx = {
        "title": "Video Highlights",
        "description": args.description,
        "cards": cards,
    }
    html = render_template(template_text, ctx)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Done. Open {out_dir/'index.html'} in a browser.")

DEFAULT_TEMPLATE_TEXT = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body>
  <h1>{{ title }}</h1>
  <p>{{ description }}</p>
  <video id="player" src="video.mp4" controls playsinline style="width:100%;max-width:960px;"></video>
  <div id="cards">
  {% for c in cards %}
    <div class="card" data-start="{{ c.start_seconds }}">
      <img src="{{ c.thumbnail }}" alt="{{ c.title }}" style="width:220px;height:124px;object-fit:cover" />
      <div>{{ c.title }}</div>
      <small>Starts at {{ c.ts }}</small>
    </div>
  {% endfor %}
  </div>
  <script>
    const player = document.getElementById('player');
    document.addEventListener('click', (e)=>{
      const card = e.target.closest('.card');
      if(card){ player.currentTime = Number(card.dataset.start)||0; player.play(); window.scrollTo({top:0, behavior:'smooth'}); }
    });
  </script>
</body></html>
"""

DEFAULT_PLAYER_JS = """(function(){ const p=document.getElementById('player'); if(!p) return;
document.addEventListener('click',e=>{ const c=e.target.closest('[data-start]'); if(!c) return;
p.currentTime = Number(c.dataset.start)||0; p.play(); window.scrollTo({top:0,behavior:'smooth'}); });})();"""

if __name__ == "__main__":
    main()
