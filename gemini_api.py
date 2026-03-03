"""Generate featured images using Google Gemini API."""

import os
import tempfile
from google import genai
from google.genai import types


# Models to try in order of preference
GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]

IMAGEN_MODELS = [
    "imagen-4.0-fast-generate-001",
    "imagen-4.0-generate-001",
]


def generate_image(api_key, prompt, output_dir=None):
    """Generate an image from a text prompt using Gemini.

    Tries Gemini native image models first, then Imagen as fallback.
    Images are generated in 3:2 aspect ratio (landscape).

    Args:
        api_key: Google Gemini API key.
        prompt: Text description of the image to generate.
        output_dir: Directory to save the image. Uses temp dir if None.

    Returns:
        dict with 'success' (bool), 'path' (str) or 'error' (str).
    """
    if not api_key:
        return {"success": False, "error": "Gemini API key not configured."}

    if output_dir is None:
        output_dir = tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)

    client = genai.Client(api_key=api_key)
    errors = []

    for model in GEMINI_IMAGE_MODELS:
        result = _try_gemini_native(client, model, prompt, output_dir)
        if result["success"]:
            return result
        errors.append(result["error"])

    for model in IMAGEN_MODELS:
        result = _try_imagen(client, model, prompt, output_dir)
        if result["success"]:
            return result
        errors.append(result["error"])

    return {"success": False, "error": "All models failed:\n" + "\n".join(errors)}


def _try_gemini_native(client, model, prompt, output_dir):
    """Try generating image with Gemini native model."""
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="3:2",
                ),
            ),
        )

        if not response.candidates:
            return {"success": False, "error": f"{model}: No candidates in response."}

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                if not image_data:
                    continue
                mime = part.inline_data.mime_type or "image/png"
                ext = ".png" if "png" in mime else ".jpg"

                filename = f"gemini_{os.urandom(4).hex()}{ext}"
                filepath = os.path.join(output_dir, filename)

                with open(filepath, "wb") as f:
                    f.write(image_data)

                if os.path.isfile(filepath) and os.path.getsize(filepath) > 100:
                    return {"success": True, "path": filepath}
                else:
                    return {"success": False, "error": f"{model}: Image file is empty or corrupt."}

        return {"success": False, "error": f"{model}: Response contained no image data."}

    except Exception as e:
        error_msg = str(e)
        if "API_KEY" in error_msg.upper() or "401" in error_msg or "403" in error_msg:
            return {"success": False, "error": "Invalid Gemini API key."}
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            if "limit: 0" in error_msg or "limit:0" in error_msg:
                return {"success": False, "error": "Image generation requires a paid Gemini API plan. Upgrade at https://ai.dev/projects"}
            return {"success": False, "error": f"{model}: Rate limit exceeded. Try again later."}
        return {"success": False, "error": f"{model}: {error_msg}"}


def _try_imagen(client, model, prompt, output_dir):
    """Try generating image with Imagen model."""
    try:
        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="3:2",
            ),
        )

        if response.generated_images:
            img = response.generated_images[0]
            filename = f"gemini_{os.urandom(4).hex()}.jpg"
            filepath = os.path.join(output_dir, filename)

            img.image.save(filepath)

            if os.path.isfile(filepath) and os.path.getsize(filepath) > 100:
                return {"success": True, "path": filepath}
            else:
                return {"success": False, "error": f"{model}: Image file is empty."}

        return {"success": False, "error": f"{model}: No images generated."}

    except Exception as e:
        error_msg = str(e)
        if "paid plan" in error_msg.lower():
            return {"success": False, "error": "Imagen requires a paid Gemini API plan. Upgrade at https://ai.dev/projects"}
        return {"success": False, "error": f"{model}: {error_msg}"}


def build_image_prompt(title):
    """Build an image generation prompt from an article title."""
    return (
        f"Create a professional, high-quality blog featured image for an article titled: "
        f"\"{title}\". The image should be visually appealing, relevant to the topic, "
        f"photorealistic style, suitable for a blog header. No text on the image. "
        f"Landscape orientation, wide format."
    )
