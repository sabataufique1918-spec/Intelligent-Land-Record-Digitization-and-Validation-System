#!/usr/bin/env bash
# Fine-tune Tesseract's Hindi model on synthetic land-record lines (+ officer-verified lines if given).
# Runs natively on Windows (Git Bash) with the UB-Mannheim Tesseract install, or on Linux.
#   bash scripts/ocr_finetune/train.sh [ITERATIONS] [path/to/ocr_training_ground_truth.zip]
# Output: work/hin_landrec.traineddata. Copy it to backend/tessdata/ (HINDI_OCR_MODEL=hin_landrec).
set -euo pipefail
ITER=${1:-8000}
GT_ZIP=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
BACKEND=$(cd "$HERE/../.." && pwd)
WORK="$HERE/work"
PY="$BACKEND/.venv/Scripts/python.exe"; [ -x "$PY" ] || PY="$BACKEND/.venv/bin/python"
TBIN=$(dirname "$(command -v tesseract || echo "/c/Program Files/Tesseract-OCR/tesseract.exe")")
TD="$BACKEND/tessdata"
CFG=$(ls "$TBIN/tessdata/configs/lstm.train" /usr/share/tesseract-ocr/*/tessdata/configs/lstm.train 2>/dev/null | head -1 || true)
export OCR_FT_WORK="$WORK"
mkdir -p "$WORK/fonts" "$WORK/out"
cd "$WORK"

# 1. Tools and fonts (Google Fonts, OFL). hin.traineddata must be the tessdata_best (float) model.
[ -d pylib/uharfbuzz ] || "$PY" -m pip install -q --target pylib uharfbuzz freetype-py
B=https://raw.githubusercontent.com/google/fonts/main/ofl
for f in kalam/Kalam-Regular.ttf kalam/Kalam-Light.ttf kalam/Kalam-Bold.ttf amita/Amita-Regular.ttf \
  hind/Hind-Regular.ttf hind/Hind-Medium.ttf mukta/Mukta-Regular.ttf martel/Martel-Regular.ttf \
  laila/Laila-Regular.ttf sura/Sura-Regular.ttf yatraone/YatraOne-Regular.ttf khand/Khand-Regular.ttf \
  palanquin/Palanquin-Regular.ttf karma/Karma-Regular.ttf biryani/Biryani-Regular.ttf \
  sahitya/Sahitya-Regular.ttf gotu/Gotu-Regular.ttf tirodevanagarihindi/TiroDevanagariHindi-Regular.ttf \
  rozhaone/RozhaOne-Regular.ttf "notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf" \
  "notoserifdevanagari/NotoSerifDevanagari%5Bwdth,wght%5D.ttf" "eczar/Eczar%5Bwght%5D.ttf" "baloo2/Baloo2%5Bwght%5D.ttf"; do
  n=$(basename "$f" | sed 's/%5B.*%5D//'); [ -f "fonts/$n" ] || curl -sfL -o "fonts/$n" "$B/$f"
done
"$TBIN/combine_tessdata" -u "$TD/hin.traineddata" hin. >/dev/null
[ -f hin.lstm ] || { echo "hin.traineddata has no float LSTM (use tessdata_best)"; exit 1; }

# 2. Synthetic lines. Laila and Martel are held out of training to test unseen fonts.
rm -rf data && HOLD=Laila-Regular,Martel-Regular
for s in 1 2 3 4 5 6; do "$PY" "$HERE/synth_lines.py" data/train 1000 $s --exclude $HOLD & done
"$PY" "$HERE/synth_lines.py" data/eval_seen 400 101 --exclude $HOLD &
"$PY" "$HERE/synth_lines.py" data/eval_unseen 300 102 --fonts $HOLD &
(cd "$HERE" && "$PY" synth_general.py "$WORK/data/eval_general" 200 201 Laila-Regular,Martel-Regular,Nirmala) &
wait

# 3. Officer-verified real lines (exported from the Training Data page) join the training set.
if [ -n "$GT_ZIP" ]; then
  mkdir -p data/real && unzip -qo "$GT_ZIP" -d data/real_zip
  for png in data/real_zip/ground-truth/*.png; do
    b=data/real/$(basename "${png%.png}")
    "$PY" -c "import sys;from PIL import Image;Image.open(sys.argv[1]).convert('L').save(sys.argv[2])" "$png" "$b.tif"
    cp "${png%.png}.gt.txt" "$b.gt.txt"
    (cd "$HERE" && "$PY" -c "import sys,unicodedata;import synth_lines as g;from PIL import Image
t=unicodedata.normalize('NFC',open(sys.argv[2],encoding='utf-8').read().strip());w,h=Image.open(sys.argv[1]).size
open(sys.argv[3],'w',encoding='utf-8').write(g.box_lines(t,w,h))" "$WORK/$b.tif" "$WORK/$b.gt.txt" "$WORK/$b.box")
  done
fi

# 4. .lstmf files, then fine-tune.
export TD CFG TBIN
ls data/*/*.tif | sed 's/\.tif$//' | xargs -P 8 -I{} sh -c '"$TBIN/tesseract" {}.tif {} --tessdata-dir "$TD" -l hin --psm 13 "$CFG" >/dev/null 2>&1'
W=$(pwd -W 2>/dev/null || pwd)
list() { ls data/$1/*.lstmf 2>/dev/null | sed "s#^#$W/#" || true; }
{ list train; list real; } > list.train
for d in eval_seen eval_unseen eval_general; do list $d > list.$d; done
"$TBIN/lstmtraining" --model_output out/landrec --continue_from hin.lstm --traineddata "$TD/hin.traineddata" \
  --train_listfile list.train --eval_listfile list.eval_seen --learning_rate 0.0001 \
  --max_iterations "$ITER" --target_error_rate 0.01
"$TBIN/lstmtraining" --stop_training --continue_from out/landrec_checkpoint --traineddata "$TD/hin.traineddata" \
  --model_output hin_landrec.traineddata
"$TBIN/combine_tessdata" -e hin_landrec.traineddata landrec.lstm >/dev/null

# 5. Stock vs fine-tuned on held-out sets (character error rate).
for d in eval_seen eval_unseen eval_general; do for m in hin landrec; do
  printf '%-13s %-8s ' "$d" "$m"; "$TBIN/lstmeval" --model $m.lstm --traineddata "$TD/hin.traineddata" --eval_listfile list.$d 2>&1 | grep -o 'BCER.*'
done; done
echo "Model: $WORK/hin_landrec.traineddata"
