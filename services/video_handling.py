import whisper
import subprocess
import os
import sys
import tempfile
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

# ==========================================
# CONFIG
# ==========================================

MODEL_SIZE = "base"
WORDS_PER_LINE = 4
FONT_SIZE = 60
FONT_NAME = "Arial"
MIN_SILENCE_LEN = 700      # ms
SILENCE_THRESH = -40       # dB
OUTPUT_FILE = "final_output.mp4"

# ==========================================
# FUNCTION: Extract Audio From Video
# ==========================================

def extract_audio(video_path, audio_path):
    """
    Uses FFmpeg to extract WAV audio from the video.
    Required for silence detection.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ac", "1",
        "-ar", "16000",
        audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ==========================================
# FUNCTION: Remove Silence From Video
# ==========================================

def remove_silence(video_path):
    """
    Detects non-silent chunks using pydub
    and stitches them together with FFmpeg.
    Returns path to trimmed video.
    """

    temp_audio = "temp_audio.wav"
    extract_audio(video_path, temp_audio)

    audio = AudioSegment.from_wav(temp_audio)

    nonsilent_ranges = detect_nonsilent(
        audio,
        min_silence_len=MIN_SILENCE_LEN,
        silence_thresh=SILENCE_THRESH
    )

    if not nonsilent_ranges:
        return video_path

    # Build FFmpeg filter string
    filter_parts = []
    for start, end in nonsilent_ranges:
        start_sec = start / 1000
        end_sec = end / 1000
        filter_parts.append(
            f"between(t,{start_sec},{end_sec})"
        )

    select_filter = "+".join(filter_parts)

    output_trimmed = "temp_trimmed.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"select='{select_filter}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{select_filter}',asetpts=N/SR/TB",
        output_trimmed
    ]

    subprocess.run(cmd)

    return output_trimmed

# ==========================================
# FUNCTION: Convert to Vertical 9:16
# ==========================================

def vertical_crop(video_path):
    """
    Crops center of video to 9:16 format.
    Keeps height, crops width.
    """

    output_vertical = "temp_vertical.mp4"

    crop_filter = (
        "crop=ih*9/16:ih"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", crop_filter,
        output_vertical
    ]

    subprocess.run(cmd)

    return output_vertical

# ==========================================
# FUNCTION: Generate ASS Subtitle File
# ==========================================

def generate_subtitles(video_path):
    """
    Transcribes video using Whisper,
    groups words into chunks,
    and generates styled ASS subtitle file.
    """

    model = whisper.load_model(MODEL_SIZE)
    result = model.transcribe(video_path, word_timestamps=True)

    def sec_to_ass(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,3,0,2,50,50,200,1

[Events]
Format: Layer,Start,End,Style,Text
"""

    words = []
    for seg in result["segments"]:
        for word in seg["words"]:
            words.append(word)

    for i in range(0, len(words), WORDS_PER_LINE):
        chunk = words[i:i+WORDS_PER_LINE]
        if not chunk:
            continue

        start = sec_to_ass(chunk[0]["start"])
        end = sec_to_ass(chunk[-1]["end"])
        text = " ".join(w["word"].strip() for w in chunk).upper()

        ass += f"Dialogue: 0,{start},{end},Default,{text}\n"

    subtitle_file = "temp_subs.ass"
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(ass)

    return subtitle_file

# ==========================================
# FUNCTION: Burn Subtitles Into Video
# ==========================================

def burn_subtitles(video_path, subtitle_path):
    """
    Uses FFmpeg to permanently burn subtitles into video.
    """

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={subtitle_path}",
        "-c:a", "copy",
        OUTPUT_FILE
    ]

    subprocess.run(cmd)

# ==========================================
# MAIN PIPELINE
# ==========================================

def main(input_video):
    print("1. Removing silence...")
    no_silence = remove_silence(input_video)

    print("2. Converting to vertical 9:16...")
    vertical = vertical_crop(no_silence)

    print("3. Generating subtitles...")
    subs = generate_subtitles(vertical)

    print("4. Burning subtitles...")
    burn_subtitles(vertical, subs)

    print("Done. Output saved as:", OUTPUT_FILE)

# ==========================================

#if __name__ == "__main__":
#    if len(sys.argv) < 2:
#        print("Usage: python ai_streamer_editor.py input.mp4")
#        sys.exit(1)

#    main(sys.argv[1])
