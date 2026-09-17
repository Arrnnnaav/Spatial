#!/bin/bash
# Fetch the CPU speech models straight into the Hugging Face cache with curl over IPv4.
# Use when `pip`/`huggingface_hub` downloads stall (broken IPv6 route, flaky xet backend).
# Afterwards the server finds the files without touching the network.
#
#   bash scripts/fetch_models.sh            # pocket-tts (english) + faster-whisper base
#   bash scripts/fetch_models.sh small      # faster-whisper small instead of base
set -u
WHISPER_SIZE="${1:-base}"
HUB="$HOME/.cache/huggingface/hub"

fetch() {  # fetch <repo> <revision> <path>
  local repo="$1" rev="$2" path="$3"
  local dir="$HUB/models--${repo//\//--}/snapshots/$rev"
  mkdir -p "$dir/$(dirname "$path")"
  local out="$dir/$path"
  for try in 1 2 3 4 5 6 7 8; do
    curl -4 -L -C - --retry 3 --max-time 900 -sS -o "$out" "https://huggingface.co/$repo/resolve/$rev/$path" && break
    echo "retry $try $path"; sleep 3
  done
  echo "ok $path ($(stat -c %s "$out") bytes)"
}

# --- Kyutai pocket-tts, english, without voice cloning (public repo) ---
TTS=kyutai/pocket-tts-without-voice-cloning
fetch $TTS d29db7978e464fb90cb3359ee0c69a273b9142cc languages/english/model.safetensors
fetch $TTS d29db7978e464fb90cb3359ee0c69a273b9142cc languages/english/tokenizer.model
fetch $TTS d4fdd22ae8c8e1cb3634e150ebeff1dab2d16df3 tokenizer.model
for voice in alba jane paul; do
  fetch $TTS e81d79e8194ad4c7ce879c87a4258ef20cbf2487 languages/english/embeddings/$voice.safetensors
done

# --- faster-whisper (CTranslate2) ---
WHISPER="Systran/faster-whisper-$WHISPER_SIZE"
REV=$(curl -4 -sL --max-time 20 "https://huggingface.co/api/models/$WHISPER" | python -c "import sys,json;print(json.load(sys.stdin)['sha'])")
mkdir -p "$HUB/models--Systran--faster-whisper-$WHISPER_SIZE/refs"
echo -n "$REV" > "$HUB/models--Systran--faster-whisper-$WHISPER_SIZE/refs/main"
for f in config.json model.bin tokenizer.json vocabulary.txt; do fetch "$WHISPER" "$REV" "$f"; done

echo "All models fetched into $HUB"
