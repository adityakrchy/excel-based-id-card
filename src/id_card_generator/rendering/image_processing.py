"""Image scaling, fit modes, anti-aliased masking, and placeholder generation."""

import logging
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from id_card_generator.core.constants import ImageFitMode
from id_card_generator.rendering.font_manager import FontManager

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image resizing, fit modes, masking (circle, rounded), borders, and placeholders."""

    @staticmethod
    def load_and_fit(
        image_path: Path,
        target_width: int,
        target_height: int,
        fit_mode: ImageFitMode = ImageFitMode.COVER,
    ) -> Image.Image:
        """Load an image from disk and resize it according to target dimensions and fit mode."""
        try:
            with Image.open(image_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGBA")
                return ImageProcessor.fit_image(img, target_width, target_height, fit_mode)
        except Exception as e:
            logger.error("Failed to load and fit image from %s: %s", image_path, e)
            return ImageProcessor.generate_placeholder(target_width, target_height, "!")

    @staticmethod
    def fit_image(
        img: Image.Image,
        target_width: int,
        target_height: int,
        fit_mode: ImageFitMode = ImageFitMode.COVER,
    ) -> Image.Image:
        """Resize RGBA image according to fit mode."""
        if target_width <= 0 or target_height <= 0:
            return img

        orig_w, orig_h = img.size

        if fit_mode == ImageFitMode.STRETCH:
            return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        elif fit_mode == ImageFitMode.CONTAIN:
            # Maintain aspect ratio, letterbox / pillarbox transparently
            scale = min(target_width / orig_w, target_height / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
            offset_x = (target_width - new_w) // 2
            offset_y = (target_height - new_h) // 2
            canvas.paste(resized, (offset_x, offset_y), resized)
            return canvas

        elif fit_mode == ImageFitMode.COVER:
            # Scale to cover target box and crop centered excess
            scale = max(target_width / orig_w, target_height / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            crop_x = (new_w - target_width) // 2
            crop_y = (new_h - target_height) // 2
            return resized.crop((crop_x, crop_y, crop_x + target_width, crop_y + target_height))

        elif fit_mode == ImageFitMode.CROP:
            # Direct centered crop without scaling if possible
            crop_x = max(0, (orig_w - target_width) // 2)
            crop_y = max(0, (orig_h - target_height) // 2)
            cropped = img.crop((crop_x, crop_y, crop_x + target_width, crop_y + target_height))
            return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

        return img

    @staticmethod
    def apply_mask_and_border(
        img: Image.Image,
        mask_shape: str = "rect",  # rect, circle, rounded
        border_radius: int = 0,
        border_width: int = 0,
        border_color: str = "transparent",
    ) -> Image.Image:
        """Apply anti-aliased mask (circle, rounded rect) and optional border."""
        w, h = img.size
        # Render mask at 2x resolution for smooth anti-aliasing, then downsample
        scale = 2
        mask_w, mask_h = w * scale, h * scale
        mask = Image.new("L", (mask_w, mask_h), 0)
        draw = ImageDraw.Draw(mask)

        if mask_shape == "circle":
            draw.ellipse((0, 0, mask_w - 1, mask_h - 1), fill=255)
        elif mask_shape == "rounded" or border_radius > 0:
            radius = border_radius * scale
            draw.rounded_rectangle((0, 0, mask_w - 1, mask_h - 1), radius=radius, fill=255)
        else:
            draw.rectangle((0, 0, mask_w - 1, mask_h - 1), fill=255)

        # Downsample mask
        mask = mask.resize((w, h), Image.Resampling.LANCZOS)

        # Apply mask to alpha channel
        result = img.copy()
        alpha = result.split()[3]
        combined_alpha = ImageChops.multiply(alpha, mask)
        result.putalpha(combined_alpha)

        # Draw border if configured
        if border_width > 0 and border_color and border_color != "transparent":
            border_canvas = Image.new("RGBA", (mask_w, mask_h), (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border_canvas)
            bw = border_width * scale

            if mask_shape == "circle":
                border_draw.ellipse(
                    (bw // 2, bw // 2, mask_w - 1 - bw // 2, mask_h - 1 - bw // 2),
                    outline=border_color,
                    width=bw,
                )
            elif mask_shape == "rounded" or border_radius > 0:
                radius = border_radius * scale
                border_draw.rounded_rectangle(
                    (bw // 2, bw // 2, mask_w - 1 - bw // 2, mask_h - 1 - bw // 2),
                    radius=radius,
                    outline=border_color,
                    width=bw,
                )
            else:
                border_draw.rectangle(
                    (bw // 2, bw // 2, mask_w - 1 - bw // 2, mask_h - 1 - bw // 2),
                    outline=border_color,
                    width=bw,
                )

            border_img = border_canvas.resize((w, h), Image.Resampling.LANCZOS)
            result = Image.alpha_composite(result, border_img)

        return result

    @staticmethod
    def generate_placeholder(
        width: int,
        height: int,
        initials: str = "?",
        bg_color: str = "#E2E8F0",
        fg_color: str = "#64748B",
    ) -> Image.Image:
        """Generate a clean profile placeholder with initials or camera icon symbol."""
        img = Image.new("RGBA", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        font_size = max(14, int(min(width, height) * 0.4))
        font = FontManager.get_font("Arial", font_size, bold=True)

        text = initials[:2].upper()
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) / 2
        y = (height - th) / 2 - (bbox[1])

        draw.text((x, y), text, fill=fg_color, font=font)
        return img
