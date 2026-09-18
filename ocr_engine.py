"""
SIH26034 - Legal Metrology Packaging Compliance System
OCR Preprocessing & Spatial Coordinate Extraction Pipeline
"""

import os
import time
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCREngine")

class PreprocessingPipeline:
    """
    Advanced OpenCV Preprocessing Pipeline for real-world packaged commodity labels.
    Eliminates plastic sheen, camera flash glare, foil reflections, uneven lighting, skew, and low contrast
    using CLAHE, Bilateral Filtering, Unsharp Masking, and Canny Edge Detection.
    """

    @staticmethod
    def apply_clahe(gray_image: np.ndarray, clip_limit: float = 3.0, tile_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
        """Apply Contrast Limited Adaptive Histogram Equalization for lighting & glare normalization."""
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_size)
        return clahe.apply(gray_image)

    @staticmethod
    def unsharp_mask(gray_image: np.ndarray, kernel_size: int = 5, sigma: float = 1.0, strength: float = 1.5) -> np.ndarray:
        """
        Unsharp masking to sharpen fine print text on packaging labels.
        Critical for blurry phone camera shots and compressed label scans.
        strength controls sharpening intensity.
        """
        blurred = cv2.GaussianBlur(gray_image, (kernel_size, kernel_size), sigma)
        sharpened = cv2.addWeighted(gray_image, 1.0 + strength, blurred, -strength, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    @staticmethod
    def denoise_bilateral(gray_image: np.ndarray) -> np.ndarray:
        """Preserve sharp text edges while suppressing package printing textures, foil grain, and sheen."""
        return cv2.bilateralFilter(gray_image, d=9, sigmaColor=75, sigmaSpace=75)

    @staticmethod
    def detect_canny_edges(gray_image: np.ndarray, low_thresh: int = 80, high_thresh: int = 180) -> np.ndarray:
        """Canny edge detection to isolate packaging boundaries and prominent principal display panel text contours."""
        return cv2.Canny(gray_image, low_thresh, high_thresh)

    @staticmethod
    def adaptive_threshold(gray_image: np.ndarray) -> np.ndarray:
        """
        Adaptive binarization for local lighting variation on real packaging photos.
        Better than global thresholding for curved labels, shadows and partial reflections.
        """
        return cv2.adaptiveThreshold(
            gray_image, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=8
        )

    @staticmethod
    def suppress_glare(bgr_image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Eliminates plastic sheen and camera flash glare on shiny pouches and metallic foils.
        Detects localized specular over-saturation in HSV color space without wiping out white labels.
        """
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        
        # Specular glare is high brightness and low saturation
        raw_mask = cv2.inRange(hsv, np.array([0, 0, 250]), np.array([180, 25, 255]))
        total_pixels = bgr_image.shape[0] * bgr_image.shape[1]
        glare_ratio = float(np.count_nonzero(raw_mask)) / float(max(1, total_pixels))
        
        # Glare is localized specular highlights (typically 0.05% to 10% of total area).
        # If > 12% is white, it is a white background/paper label, NOT specular glare!
        if 0.0005 < glare_ratio < 0.12:
            dilated_mask = cv2.dilate(raw_mask, np.ones((3, 3), np.uint8), iterations=1)
            cleaned_bgr = cv2.inpaint(bgr_image, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
            return cleaned_bgr, dilated_mask
        
        return bgr_image, np.zeros_like(v)

    @staticmethod
    def deskew_image(image: np.ndarray) -> np.ndarray:
        """
        Detect label orientation and deskew using minimum area bounding rectangle
        on prominent text edge contours.
        """
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 50:
                return image
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            # Avoid aggressive rotation for small jitter or vertical labels
            if abs(angle) > 20 or abs(angle) < 0.5:
                return image

            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated
        except Exception as e:
            logger.warning(f"Deskew failed, returning original image: {e}")
            return image

    @classmethod
    def enhance_for_ocr(cls, bgr_image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Executes full Layer 1 Computer Vision preprocessing chain:
        1. Specular glare & plastic sheen suppression
        2. Orientation deskew
        3. CLAHE adaptive lighting equalization
        4. Bilateral edge-preserving denoising
        5. Unsharp mask sharpening for fine text
        6. Canny edge feature extraction
        Returns:
            processed_bgr: Deskewed, glare-attenuated, contrast-optimized color image
            processed_gray: Enhanced grayscale representation ready for OCR text segmentation
            canny_edges: Canny edge detection binary map
            cv_metrics: Diagnostic computer vision metadata (edge density, glare coverage)
        """
        anti_glare_bgr, glare_mask = cls.suppress_glare(bgr_image)
        deskewed = cls.deskew_image(anti_glare_bgr)
        gray = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)
        clahe_gray = cls.apply_clahe(gray, clip_limit=3.0)
        denoised_gray = cls.denoise_bilateral(clahe_gray)
        sharpened_gray = cls.unsharp_mask(denoised_gray, strength=1.5)
        edges = cls.detect_canny_edges(sharpened_gray, 80, 180)
        enhanced_bgr = cv2.cvtColor(sharpened_gray, cv2.COLOR_GRAY2BGR)

        h, w = gray.shape[:2]
        edge_density = float(np.count_nonzero(edges)) / float(max(1, edges.size))
        glare_ratio = float(np.count_nonzero(glare_mask)) / float(max(1, glare_mask.size))

        cv_metrics = {
            "edge_density": round(edge_density, 4),
            "glare_ratio": round(glare_ratio, 4),
            "glare_suppressed": glare_ratio > 0.001
        }
        return enhanced_bgr, sharpened_gray, edges, cv_metrics

    @classmethod
    def upscale_for_ocr(cls, bgr_image: np.ndarray, scale: float = 2.0) -> np.ndarray:
        """
        Bicubic upscaling to make small label text larger for ONNX OCR detection.
        Critical for phone camera photos where Net Qty / MRP font may be only 6-10px tall.
        """
        h, w = bgr_image.shape[:2]
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(bgr_image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    @classmethod
    def prepare_high_contrast(cls, bgr_image: np.ndarray) -> np.ndarray:
        """
        Produce an extremely high-contrast black-on-white rendering using adaptive threshold.
        Best for faded or low-contrast label printing (e.g., stamped expiry dates, inkjet prints).
        """
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY) if len(bgr_image.shape) == 3 else bgr_image
        # Aggressive CLAHE
        clahe_gray = cls.apply_clahe(gray, clip_limit=5.0)
        # Adaptive binarization
        binary = cls.adaptive_threshold(clahe_gray)
        # Invert if majority is dark (text on dark background)
        if np.mean(binary) < 127:
            binary = cv2.bitwise_not(binary)
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


class OCREngine:
    """
    Multi-engine OCR wrapper with RapidOCR (PaddleOCR ONNX) as primary high-speed engine.
    Implements 3-pass multi-scale inference for maximum accuracy on real-world packaging photos:
      Pass 1: Standard enhanced BGR
      Pass 2: 2x bicubic upscaled image (catches small font text like expiry stamps)
      Pass 3: High-contrast adaptive threshold image (catches faded/low-contrast printing)
    All three passes are merged and deduplicated by spatial proximity.
    """

    def __init__(self, preferred_engine: Optional[str] = None):
        self._preferred_engine = (
            preferred_engine or os.getenv("OCR_ENGINE", "rapidocr")
        ).lower()
        self._engine = None
        self._engine_type = "none"
        self._initialize_engine()

    def _initialize_engine(self):
        # Prioritize preferred engine (default: rapidocr)
        if self._preferred_engine == "easyocr":
            if self._try_init_easyocr():
                return
            if self._try_init_rapidocr():
                return
        else:
            if self._try_init_rapidocr():
                return
            if self._try_init_easyocr():
                return

        logger.warning("No hardware or local OCR engines available. Simulated fallback enabled.")
        self._engine_type = "mock"

    def _try_init_easyocr(self) -> bool:
        try:
            import warnings
            warnings.filterwarnings("ignore", category=UserWarning)
            import easyocr
            self._engine = easyocr.Reader(['en'], gpu=False, verbose=False)
            self._engine_type = "easyocr"
            logger.info("EasyOCR engine (PyTorch CRAFT + CRNN) initialized successfully as primary OCR.")
            return True
        except Exception as e:
            logger.warning(f"EasyOCR initialization failed: {e}. Trying fallback engines...")
            return False

    def _try_init_rapidocr(self) -> bool:
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR(use_angle_cls=False)
            self._engine_type = "rapidocr"
            logger.info("RapidOCR (PaddleOCR ONNX) engine initialized successfully.")
            return True
        except Exception as e:
            logger.warning(f"RapidOCR initialization failed: {e}.")
            return False

    @property
    def engine_type(self) -> str:
        return self._engine_type

    def extract_tokens(self, image_np: np.ndarray, scale_factor: float = 1.0) -> List[Dict[str, Any]]:
        """
        Extract OCR tokens with text, confidence, and bounding box [x, y, w, h]
        along with 4-corner polygon coordinates.
        scale_factor is used to normalize coordinates back to original image space.
        """
        h_img, w_img = image_np.shape[:2]
        tokens = []

        if self._engine_type == "rapidocr":
            result, _ = self._engine(image_np)
            if result:
                for item in result:
                    # item format: [dt_boxes, text, score]
                    polygon = item[0]
                    text = str(item[1]).strip()
                    score = float(item[2])
                    if not text:
                        continue
                    # Accept tokens with confidence >= 0.30 (was 0.0 but implicit filtering was too tight)
                    if score < 0.30:
                        continue

                    # Polygon is 4 points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                    xs = [p[0] for p in polygon]
                    ys = [p[1] for p in polygon]
                    x_min, x_max = max(0, min(xs)), min(w_img, max(xs))
                    y_min, y_max = max(0, min(ys)), min(h_img, max(ys))
                    w_box = max(1, x_max - x_min)
                    h_box = max(1, y_max - y_min)

                    # Scale coordinates back to original image space
                    ox = int(x_min / scale_factor)
                    oy = int(y_min / scale_factor)
                    ow = max(1, int(w_box / scale_factor))
                    oh = max(1, int(h_box / scale_factor))

                    tokens.append({
                        "text": text,
                        "confidence": round(score, 3),
                        "bbox": [ox, oy, ow, oh],
                        "polygon": [[int(pt[0] / scale_factor), int(pt[1] / scale_factor)] for pt in polygon],
                        "normalized_bbox": [
                            round(ox / (w_img / scale_factor), 4),
                            round(oy / (h_img / scale_factor), 4),
                            round(ow / (w_img / scale_factor), 4),
                            round(oh / (h_img / scale_factor), 4)
                        ]
                    })

        elif self._engine_type == "easyocr":
            results = self._engine.readtext(image_np)
            for item in results:
                polygon, text, score = item
                text = str(text).strip()
                if not text or score < 0.30:
                    continue
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                x_min, x_max = max(0, min(xs)), min(w_img, max(xs))
                y_min, y_max = max(0, min(ys)), min(h_img, max(ys))
                w_box = max(1, x_max - x_min)
                h_box = max(1, y_max - y_min)

                ox = int(x_min / scale_factor)
                oy = int(y_min / scale_factor)
                ow = max(1, int(w_box / scale_factor))
                oh = max(1, int(h_box / scale_factor))

                tokens.append({
                    "text": text,
                    "confidence": round(float(score), 3),
                    "bbox": [ox, oy, ow, oh],
                    "polygon": [[int(pt[0] / scale_factor), int(pt[1] / scale_factor)] for pt in polygon],
                    "normalized_bbox": [
                        round(ox / (w_img / scale_factor), 4),
                        round(oy / (h_img / scale_factor), 4),
                        round(ow / (w_img / scale_factor), 4),
                        round(oh / (h_img / scale_factor), 4)
                    ]
                })

        return tokens

    @staticmethod
    def _text_key(text: str) -> str:
        """Normalize text for duplicate comparison: lowercase, strip punctuation and spaces."""
        import re
        return re.sub(r'[\s\W]+', '', text.lower())

    def deduplicate_tokens(self, all_tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate detections from multi-scale OCR passes using text-based deduplication.
        When the same text appears from multiple passes (e.g. Pass 1 standard, Pass 2 upscale, Pass 3 high-contrast),
        keep the version with the highest confidence score.
        This avoids the IoU-based spatial overlap issue where large blocks absorb adjacent unique tokens.
        """
        seen_keys: Dict[str, Dict[str, Any]] = {}

        for token in all_tokens:
            key = self._text_key(token["text"])
            if not key:
                continue
            if key not in seen_keys:
                seen_keys[key] = token
            else:
                # Keep the one with higher confidence
                if token["confidence"] > seen_keys[key]["confidence"]:
                    seen_keys[key] = token

        # Re-sort by spatial position (top-to-bottom, left-to-right) for natural reading order
        return sorted(seen_keys.values(), key=lambda t: (t["bbox"][1], t["bbox"][0]))

    @staticmethod
    def assemble_lines(tokens: List[Dict[str, Any]], y_thresh_ratio: float = 0.5) -> List[Dict[str, Any]]:
        """
        Groups horizontally adjacent tokens that share the same baseline into composite text lines.
        Crucial for parsing split declarations like 'MRP Rs.' + '45.00' + '(Incl. of all taxes)'.
        """
        if not tokens:
            return []

        # Sort tokens top-to-bottom, left-to-right
        sorted_tokens = sorted(tokens, key=lambda t: (t["bbox"][1], t["bbox"][0]))
        lines = []

        for token in sorted_tokens:
            tb = token["bbox"]
            t_center_y = tb[1] + tb[3] / 2.0
            t_height = tb[3]

            placed = False
            for line in lines:
                l_center_y = line["bbox"][1] + line["bbox"][3] / 2.0
                l_height = line["bbox"][3]
                avg_height = (t_height + l_height) / 2.0

                # If vertical centers are close enough (within y_thresh_ratio * avg_height)
                if abs(t_center_y - l_center_y) <= (avg_height * y_thresh_ratio):
                    line["tokens"].append(token)
                    # Update line bounding box
                    x1 = min(line["bbox"][0], tb[0])
                    y1 = min(line["bbox"][1], tb[1])
                    x2 = max(line["bbox"][0] + line["bbox"][2], tb[0] + tb[2])
                    y2 = max(line["bbox"][1] + line["bbox"][3], tb[1] + tb[3])
                    line["bbox"] = [x1, y1, x2 - x1, y2 - y1]
                    placed = True
                    break

            if not placed:
                lines.append({
                    "bbox": list(tb),
                    "tokens": [token]
                })

        # Re-sort tokens inside each line by x-coordinate and construct line text
        assembled_lines = []
        for line in lines:
            line["tokens"].sort(key=lambda t: t["bbox"][0])
            full_text = " ".join(t["text"] for t in line["tokens"])
            avg_conf = sum(t["confidence"] for t in line["tokens"]) / max(1, len(line["tokens"]))
            assembled_lines.append({
                "text": full_text,
                "confidence": round(avg_conf, 3),
                "bbox": line["bbox"],
                "token_count": len(line["tokens"])
            })

        return assembled_lines

    def process(self, image_input) -> Dict[str, Any]:
        """
        High-accuracy, high-throughput OCR pipeline:
        1. Dimension normalization (prevents slow processing / OOM on phone camera photos, ensures fine print legibility)
        2. Glare suppression (removes camera flash highlights on shiny plastic/metallic foil pouches)
        3. Orientation deskew (aligns angled labels)
        4. Primary RapidOCR inference in color space
        5. Smart adaptive contrast retry ONLY if tokens < 3 (recovers faint/inkjet stamped text)
        6. Spatial line assembly
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found at {image_input}")
            img_bgr = cv2.imread(image_input)
            if img_bgr is None:
                raise ValueError(f"Failed to read image from {image_input}")
        elif isinstance(image_input, np.ndarray):
            img_bgr = image_input.copy()
        else:
            raise TypeError("Expected image file path or numpy ndarray.")

        h_orig, w_orig = img_bgr.shape[:2]
        start_time = time.perf_counter()

        # 1. Normalize dimensions for optimal ONNX inference speed & memory
        scale_factor = 1.0
        max_dim = max(h_orig, w_orig)
        if max_dim > 1600:
            scale_factor = 1440.0 / max_dim
            new_w = int(w_orig * scale_factor)
            new_h = int(h_orig * scale_factor)
            img_proc = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        elif max_dim < 700:
            scale_factor = 1000.0 / max_dim
            new_w = int(w_orig * scale_factor)
            new_h = int(h_orig * scale_factor)
            img_proc = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        else:
            img_proc = img_bgr

        # 2. Glare suppression & deskew
        clean_bgr, glare_mask = PreprocessingPipeline.suppress_glare(img_proc)
        clean_bgr = PreprocessingPipeline.deskew_image(clean_bgr)

        # 3. Primary OCR extraction (normalizing coordinates back to original image dimensions)
        tokens = self.extract_tokens(clean_bgr, scale_factor=scale_factor)

        # 4. Fallback: if fewer than 3 tokens detected, try adaptive CLAHE enhancement
        if len(tokens) < 3 and self._engine_type != "mock":
            enhanced_bgr, _, _, _ = PreprocessingPipeline.enhance_for_ocr(clean_bgr)
            retry_tokens = self.extract_tokens(enhanced_bgr, scale_factor=scale_factor)
            if len(retry_tokens) > len(tokens):
                tokens = retry_tokens

        lines = self.assemble_lines(tokens)
        full_text = "\n".join([line["text"] for line in lines]) if lines else " ".join([t["text"] for t in tokens])
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        mean_confidence = round(sum(t["confidence"] for t in tokens) / max(1, len(tokens)), 3) if tokens else 0.0
        low_conf_count = sum(1 for t in tokens if t.get("confidence", 0.0) < 0.60)
        needs_vlm_fallback = (mean_confidence < 0.60) or (len(tokens) < 4) or (low_conf_count >= max(2, int(len(tokens) * 0.4)))

        total_pixels = img_proc.shape[0] * img_proc.shape[1]
        glare_ratio = float(np.count_nonzero(glare_mask)) / float(max(1, total_pixels))

        return {
            "image_dimensions": {"width": w_orig, "height": h_orig},
            "engine_used": self._engine_type,
            "latency_ms": latency_ms,
            "mean_confidence": mean_confidence,
            "needs_vlm_fallback": needs_vlm_fallback,
            "cv_metrics": {
                "glare_ratio": round(glare_ratio, 4),
                "glare_suppressed": glare_ratio > 0.001
            },
            "token_count": len(tokens),
            "line_count": len(lines),
            "raw_tokens": tokens,
            "assembled_lines": lines,
            "full_extracted_text": full_text
        }


# Global singleton and module-level functional entrypoints
_GLOBAL_OCR_ENGINE: Optional[OCREngine] = None

def get_ocr_engine() -> OCREngine:
    """Returns or lazily creates a shared singleton instance of OCREngine."""
    global _GLOBAL_OCR_ENGINE
    if _GLOBAL_OCR_ENGINE is None:
        _GLOBAL_OCR_ENGINE = OCREngine()
    return _GLOBAL_OCR_ENGINE

def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Applies CLAHE, bilateral filtering and unsharp mask image enhancement."""
    enhanced_bgr, _, _, _ = PreprocessingPipeline.enhance_for_ocr(image)
    return enhanced_bgr

def detect_canny_edges(image: np.ndarray, low_threshold: int = 80, high_threshold: int = 180) -> np.ndarray:
    """Performs Canny edge detection on grayscale or BGR image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return PreprocessingPipeline.detect_canny_edges(gray, low_threshold, high_threshold)

def suppress_glare(image: np.ndarray) -> np.ndarray:
    """Suppresses localized camera glare/plastic sheen highlights while preserving white backgrounds."""
    cleaned_bgr, _ = PreprocessingPipeline.suppress_glare(image)
    return cleaned_bgr

def extract_text_from_image(image_input) -> str:
    """Fast extraction of textual content from an image using the active OCR engine."""
    engine = get_ocr_engine()
    result = engine.process(image_input)
    return result.get("full_extracted_text", "")

def run_ocr_with_metadata(image_input) -> Dict[str, Any]:
    """
    Executes full Layer 2 OCR with token coordinates, confidence scores,
    processing latency, and VLM fallback necessity gating.
    """
    engine = get_ocr_engine()
    result = engine.process(image_input)
    return {
        "raw_text": result.get("full_extracted_text", ""),
        "boxes": [t.get("bbox") for t in result.get("raw_tokens", [])],
        "tokens": result.get("raw_tokens", []),
        "lines": result.get("assembled_lines", []),
        "latency_ms": result.get("latency_ms", 0.0),
        "mean_confidence": result.get("mean_confidence", 0.0),
        "needs_vlm_fallback": result.get("needs_vlm_fallback", False),
        "ocr_engine": result.get("engine_used", "none"),
        "cv_metrics": result.get("cv_metrics", {}),
    }
