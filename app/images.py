"""Procesado de imágenes subidas por los usuarios.

Toda imagen se vuelve a generar desde cero: así se rechaza lo que no sea una imagen
real, se corrige la orientación de las fotos del móvil, se eliminan los metadatos
(EXIF, que pueden incluir la ubicación GPS) y se guarda siempre pequeña.
"""
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_SIZE = 256                       # px, cuadrado
AVATAR_QUALITY = 82                     # WebP: ~10–30 KB por imagen
MAX_UPLOAD_BYTES = 8 * 1024 * 1024      # lo que se acepta subir (se reduce al guardar)
MAX_PIXELS = 40_000_000                 # p. ej. 8000×5000; más grande se rechaza
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImageError(ValueError):
    """La imagen no se puede aceptar; el mensaje se muestra al usuario."""


def make_avatar(raw):
    """Devuelve (mime, bytes) de un avatar cuadrado WebP a partir de cualquier imagen admitida."""
    if not raw:
        raise ImageError("No se ha recibido ninguna imagen.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError(f"La imagen supera {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        with warnings.catch_warnings():
            # Imágenes con dimensiones enormes («bombas de descompresión») se rechazan
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as img:
                if img.format not in ALLOWED_FORMATS:
                    raise ImageError("Formato no admitido. Usa JPG, PNG, WebP o GIF.")
                if img.width * img.height > MAX_PIXELS:
                    raise ImageError("La imagen tiene demasiados píxeles.")
                img = ImageOps.exif_transpose(img)  # de un GIF animado se usa el primer fotograma
                has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
                img = img.convert("RGBA" if has_alpha else "RGB")
                img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
                out = BytesIO()
                img.save(out, "WEBP", quality=AVATAR_QUALITY, method=6)
    except ImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageError("La imagen tiene demasiados píxeles; redúcela antes de subirla.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ImageError("El archivo no es una imagen válida.") from None
    return "image/webp", out.getvalue()
