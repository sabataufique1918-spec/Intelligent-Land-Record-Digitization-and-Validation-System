# Fine-tuning Tesseract on your own documents

The app collects training data while officers work (**Training Data** page):

* **Line transcriptions**: document pages are cut into line images; an officer types the correct
  text of each line. Export them with **Download training data** (`ocr_training_ground_truth.zip`).
* **Field feedback**: which suggested values were accepted or corrected. This measures accuracy and
  drives the automatic "learned corrections", but is not used for model training.

Fine-tuning itself runs **outside the app**, with the official
[tesstrain](https://github.com/tesseract-ocr/tesstrain) tool. It needs Linux (on Windows use WSL),
and several hours of CPU time for a few thousand iterations.

## How much data

| Goal | Verified lines (rough guide) |
|---|---|
| Better accuracy on your printed forms / fonts | 400+ |
| Useful on one handwriting style | 2,000+ lines from many pages |
| General handwriting of many writers | tens of thousands (research-scale) |

The Training Data page shows the current OCR character error rate on your verified lines. Measure it
again after fine-tuning on lines that were **not** used for training.

## Included model: `hin_landrec` (printed text)

`backend/tessdata/hin_landrec.traineddata` is the stock Hindi `tessdata_best` model fine-tuned on
6,000 **synthetic** land-record lines (khasra/khata numbers, areas, dates, names, villages, revenue terms;
Devanagari and Western digits) rendered in 21 Devanagari fonts and degraded like scans (blur, low
resolution, noise, faded ink, skew, table rules, JPEG). The app uses it for Hindi when the file is present
(`HINDI_OCR_MODEL=hin_landrec`; set `HINDI_OCR_MODEL=hin` to go back to the stock model).
The file is not in Git (`backend/tessdata/` is ignored): copy it or rebuild it with the script below.

Character error rate on held-out lines (8,000 iterations):

| Test set | stock `hin` | `hin_landrec` |
|---|---|---|
| Land-record lines, fonts seen in training (`lstmeval`) | 21.6 % | 3.2 % |
| Land-record lines, 2 fonts **not** used in training (`lstmeval`) | 11.2 % | 1.0 % |
| General Hindi sentences, unseen fonts (`lstmeval`) | 10.9 % | 2.7 % |
| Same unseen-font lines through the app's call (`eng+…`, psm 7) | 7.6 % | 5.6 % |
| General Hindi through the app's call | 5.2 % | 3.3 % |

Limits: all test lines are synthetic, made with the same degradations as the training lines, so gains on
real scans will be smaller. It does **not** read handwriting (tested on record 18: ~100 % CER for both
models), cannot output characters missing from the Hindi model (Marathi ळ, Latin letters), and cannot
fix images that are too small (under ~20 px letter height).

Rebuild or improve it (Windows Git Bash with the UB-Mannheim Tesseract install, or Linux):

```bash
cd backend
bash scripts/ocr_finetune/train.sh 8000                                   # synthetic only, ~45 min
bash scripts/ocr_finetune/train.sh 8000 ~/ocr_training_ground_truth.zip   # + officer-verified lines
cp scripts/ocr_finetune/work/hin_landrec.traineddata tessdata/
```

The script prints stock vs fine-tuned error rates at the end; only replace the model if it is better.

## Steps with tesstrain (Ubuntu / WSL)

```bash
sudo apt install -y tesseract-ocr libtesseract-dev make wget unzip python3-pip
git clone https://github.com/tesseract-ocr/tesstrain && cd tesstrain
pip install -r requirements.txt

# Start from the best Hindi model (use mar, pan, ... for other languages)
mkdir -p tessdata && wget -P tessdata https://github.com/tesseract-ocr/tessdata_best/raw/main/hin.traineddata

# Put the exported line pairs (*.png + *.gt.txt) in data/landrec-ground-truth/
mkdir -p data/landrec-ground-truth
unzip ~/ocr_training_ground_truth.zip -d /tmp/gt && cp /tmp/gt/ground-truth/* data/landrec-ground-truth/

make training MODEL_NAME=landrec START_MODEL=hin TESSDATA=$(pwd)/tessdata \
     MAX_ITERATIONS=10000 LEARNING_RATE=0.0001
```

The result is `data/landrec.traineddata`. Copy it into `backend/tessdata/`, then use it like any other
language (for example set the OCR language to `landrec` via the API, or add it to `LANGUAGES` in
`backend/app/services/ocr.py`).

## Privacy

Exported line images contain names, survey numbers and other personal data from real records. Keep the
ZIP and the training machine inside your organisation. The `backend/uploads/` folder (which also holds
the line images) is excluded from Git.
