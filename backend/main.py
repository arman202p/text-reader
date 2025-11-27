from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import pytesseract
from gtts import gTTS
import os
from dotenv import load_dotenv
from fastapi.responses import Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import tempfile
from pathlib import Path
import platform
from deep_translator import GoogleTranslator
from fastapi import Form
from fastapi.responses import JSONResponse

load_dotenv()  # loads variables from .env file

PORT = int(os.getenv("PORT", 10000))


if platform.system() == "Windows":
    tesseract_path = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    tessdata_dir_path = os.getenv("TESSERACT_LANG_DATA_PATH", r"C:\Program Files\Tesseract-OCR\tessdata")
else:
    tesseract_path = os.getenv("TESSERACT_PATH", "/usr/bin/tesseract")
    tessdata_dir_path = os.getenv("TESSERACT_LANG_DATA_PATH", "/usr/share/tesseract-ocr/tessdata")
print("Running on:", platform.system())
print("Tesseract path:", tesseract_path)
print("Tessdata path:", tessdata_dir_path)

#pytesseract.pytesseract.TesseractNotFoundError: tesseract is not installed or it's not in your path
pytesseract.pytesseract.tesseract_cmd = tesseract_path
custom_config = f'--tessdata-dir "{tessdata_dir_path}"' if tessdata_dir_path else ""

app = FastAPI()

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "frontend", html=True), name="frontend")
# Allow frontend to access backend from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL") or "*"],  # In production, specify your frontend domain instead of "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Path to the frontend index.html
frontend_index = Path(__file__).parent / "frontend" / "index.html"

LANG_CODE_MAP = {
    'eng': 'en',
    'spa': 'es',
    'fra': 'fr',
    'deu': 'de',
    'ita': 'it',
    'por': 'pt',
    'rus': 'ru',
    'jpn': 'ja',
    'chi_sim': 'zh-cn',
    'ara': 'ar',
    'hin': 'hi'
}

@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(frontend_index)

# Serve a default favicon (16x16 blank icon)
@app.get("/favicon.ico")
async def favicon():
    # A tiny transparent 16x16 favicon in bytes
    favicon_bytes = bytes.fromhex(
        "00000100010010100000010010000000000100000001000000000000000000000000000000"
    )
    return Response(content=favicon_bytes, media_type="image/x-icon")

@app.post("/ocr-tts/")
async def ocr_tts(
    file: UploadFile = File(...),
    source_lang: str = Form("eng"),      #  NEW: Source language for OCR
    target_lang: str = Form("en"),       #  NEW: Target language for TTS
    translate: str = Form("false")       #  NEW: Whether to translate
):

    try:
        print("=" * 50)
        print("Source language (OCR):", source_lang)
        print("Target language (TTS):", target_lang)
        print("Translation needed:", translate)
        # Debug: Print paths
        print("Tesseract path:", pytesseract.pytesseract.tesseract_cmd)
        print("Tessdata dir path:", tessdata_dir_path)
        print("Uploaded file:", file.filename)

        # Read uploaded image
        contents = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
            tmp_img.write(contents)
            temp_file = tmp_img.name
        print("Temporary image path:", temp_file)

        # Open image and run OCR
        img = Image.open(temp_file)
        text = pytesseract.image_to_string(img, lang=source_lang, config=f'--tessdata-dir "{tessdata_dir_path}"')
        print("OCR extracted text:", repr(text))  # Debug: show exactly what was extracted
        print("OCR extracted text:", repr(text))

        if not text.strip():
            return JSONResponse({"error": "No text found in image!"}, status_code=400)
        
        translated_text = None
        final_text = text.strip()
        source_iso = LANG_CODE_MAP.get(source_lang, source_lang)
        if translate == "true" and source_iso != target_lang:
            try:
                print(f"Translating from {source_iso} to {target_lang}...")
                translator = GoogleTranslator(source=source_iso, target=target_lang)
                translated_text = translator.translate(text.strip())
                final_text = translated_text
                print("Translated text:", repr(translated_text))
            except Exception as e:
                print(f"Translation error: {e}")
                # If translation fails, use original text
                translated_text = None
        
        audio_file = temp_file.replace(".png", ".mp3")
        
        # Map target_lang to gTTS format if needed
        gtts_lang = target_lang
        if target_lang == 'zh':
            gtts_lang = 'zh-cn'  # gTTS uses 'zh-cn' for Chinese
        
        tts = gTTS(text=final_text, lang=gtts_lang)
        tts.save(audio_file)
        print("Audio file created:", audio_file)

        # 🆕 NEW: Return JSON response with all information
        # Save audio to a static location so we can reference it
        static_audio_dir = Path(__file__).parent / "frontend" / "audio"
        static_audio_dir.mkdir(exist_ok=True)
        
        audio_filename = f"audio_{os.path.basename(audio_file)}"
        static_audio_path = static_audio_dir / audio_filename
        
        # Copy audio to static directory
        import shutil
        shutil.copy(audio_file, static_audio_path)
        
        response_data = {
            "extracted_text": text.strip(),
            "audio_url": f"/static/audio/{audio_filename}"
        }
        
        # Only include translated_text if translation occurred
        if translated_text:
            response_data["translated_text"] = translated_text
        
        print("Response data:", response_data)
        return JSONResponse(response_data)

    except Exception as e:
        print("Error:", str(e))
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
