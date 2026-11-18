
import os
import json
import io

from dotenv import load_dotenv
from PIL import Image

from google import genai
from google.genai import types

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-3.5-flash-lite"

# Image optimization settings
MAX_IMAGE_SIZE = 1200
JPEG_QUALITY = 80


# --------------------------------------------------
# IMAGE OPTIMIZATION
# --------------------------------------------------

def optimize_image(image_bytes):
    """
    Resize and compress images before sending them to Gemini.
    """

    try:
        image = Image.open(io.BytesIO(image_bytes))

        # Correct image orientation
        try:
            from PIL import ImageOps
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        # Convert unsupported formats to RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize large images
        image.thumbnail(
            (MAX_IMAGE_SIZE, MAX_IMAGE_SIZE),
            Image.Resampling.LANCZOS
        )

        # Compress to JPEG
        output = io.BytesIO()

        image.save(
            output,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True
        )

        return output.getvalue(), "image/jpeg"

    except Exception:
        # If optimization fails, use original image
        return image_bytes, "image/jpeg"


# --------------------------------------------------
# JSON RESPONSE HELPER
# --------------------------------------------------

def parse_json_response(response):

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    return json.loads(response.text)


# --------------------------------------------------
# CIVIC ISSUE IMAGE ANALYSIS
# --------------------------------------------------

def analyze_civic_image(image_bytes, mime_type="image/jpeg"):

    prompt = """
Analyze this image for visible civic infrastructure problems.

Possible issues:
- Damaged road or pothole
- Garbage or waste accumulation
- Water leakage
- Broken streetlight
- Drainage or sewage problem
- Construction debris
- Fallen tree
- Other civic issue
- No visible civic issue

Return JSON only:
{
  "issue_type": "Issue name",
  "severity": "Low, Medium, High, or Critical",
  "description": "Brief visible explanation",
  "department": "Suggested responsible department",
  "urgency": "Low, Medium, or High",
  "confidence": "Low, Medium, or High"
}

Analyze only visible evidence.
Do not invent facts, location, or hidden details.
Severity and urgency are estimates, not official decisions.
"""

    try:

        # Optimize image
        image_bytes, mime_type = optimize_image(image_bytes)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=256
            )
        )

        result = parse_json_response(response)

        return {
            "success": True,
            "analysis": result,
            "error": None
        }

    except Exception as error:

        return {
            "success": False,
            "analysis": None,
            "error": str(error)
        }


# --------------------------------------------------
# BEFORE / AFTER REPAIR VERIFICATION
# --------------------------------------------------

def compare_repair_images(
    before_bytes,
    after_bytes,
    before_mime="image/jpeg",
    after_mime="image/jpeg"
):

    prompt = """
Compare these two civic issue photographs.

IMAGE 1: Before repair
IMAGE 2: After repair

Determine whether the visible problem is:
- Fixed
- Partially Fixed
- Not Fixed

Return JSON only:
{
  "repair_status": "Fixed, Partially Fixed, or Not Fixed",
  "confidence": "Low, Medium, or High",
  "explanation": "Brief comparison of visible changes",
  "remaining_problem": "Remaining visible problem"
}

Compare only visible evidence.
If locations or angles differ, mention uncertainty.
Do not assume repairs occurred.
This is an AI estimate, not official verification.
"""

    try:

        # Optimize both images
        before_bytes, before_mime = optimize_image(before_bytes)
        after_bytes, after_mime = optimize_image(after_bytes)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,

                types.Part.from_bytes(
                    data=before_bytes,
                    mime_type=before_mime
                ),

                types.Part.from_bytes(
                    data=after_bytes,
                    mime_type=after_mime
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=256
            )
        )

        result = parse_json_response(response)

        return {
            "success": True,
            "analysis": result,
            "error": None
        }

    except Exception as error:

        return {
            "success": False,
            "analysis": None,
            "error": str(error)
        }


# --------------------------------------------------
# MULTILINGUAL CIVIC ASSISTANT
# --------------------------------------------------

def civic_assistant_reply(question, language="English"):

    prompt = f"""
You are CIVIC EYE's citizen support assistant.

Respond in {language}.

Citizen question:
{question}

Help with:
- Reporting civic issues
- Potholes, garbage, water leakage
- Streetlights and drainage
- Complaint IDs and tracking
- Before-and-after repair verification

Rules:
- Use simple, friendly language.
- Keep the answer concise, around 3-5 sentences.
- Never invent complaint status.
- Do not claim reports reach government offices automatically.
- Never request passwords or API keys.
- For immediate danger, advise contacting local emergency services.

Respond directly in {language}.
"""

    try:

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=256
            )
        )

        return {
            "success": True,
            "answer": response.text.strip(),
            "error": None
        }

    except Exception as error:

        return {
            "success": False,
            "answer": None,
            "error": str(error)
        }
