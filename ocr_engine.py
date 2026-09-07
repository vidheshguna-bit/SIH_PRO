"""
SIH26034 - Legal Metrology Packaging Compliance System
OCR Preprocessing & Spatial Coordinate Extraction Pipeline
"""

import os
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCREngine")

class PreprocessingPipeline:
    """
    Advanced OpenCV Preprocessing Pipeline for real-world packaged commodity labels.
    Handles packaging glare, foil reflections, uneven lighting, skew, and low contrast.
    """

    @staticmethod
    def apply_clahe(gray_image: np.ndarray, clip_limit: float = 2.5, tile_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
        """Apply Contrast Limited Adaptive Histogram Equalization for lighting & glare normalization."""
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_size)
        return clahe.apply(gray_image)

    @staticmethod
    def denoise_bilateral(gray_image: np.ndarray) -> np.ndarray:
        """Preserve sharp text edges while suppressing package printing textures and grain."""
        return cv2.bilateralFilter(gray_image, d=7, sigmaColor=50, sigmaSpace=50)

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
    def enhance_for_ocr(cls, bgr_image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Executes full preprocessing chain.
        Returns:
            processed_bgr: Deskewed and contrast-optimized color image
            processed_gray: Enhanced grayscale representation ready for text segmentation
        """
        deskewed = cls.deskew_image(bgr_image)
        gray = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)
        clahe_gray = cls.apply_clahe(gray)
        denoised_gray = cls.denoise_bilateral(clahe_gray)
        enhanced_bgr = cv2.cvtColor(denoised_gray, cv2.COLOR_GRAY2BGR)
        return enhanced_bgr, denoised_gray


class OCREngine:
    """
    Multi-engine OCR wrapper with PaddleOCR / RapidOCR as primary high-speed ONNX engine,
    and automatic spatial coordinate clustering for Legal Metrology text analysis.
    """

    def __init__(self):
        self._engine = None
        self._engine_type = "none"
        self._initialize_engine()

    def _initialize_engine(self):
        # 1. Try RapidOCR (PaddleOCR ONNX Runtime port)
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
            self._engine_type = "rapidocr"
            logger.info("RapidOCR (PaddleOCR ONNX) engine initialized successfully.")
            return
        except Exception as e:
            logger.warning(f"RapidOCR initialization failed: {e}. Checking secondary engines...")

        # 2. Try EasyOCR
        try:
            import easyocr
            self._engine = easyocr.Reader(['en'], gpu=False)
            self._engine_type = "easyocr"
            logger.info("EasyOCR engine initialized successfully.")
            return
        except Exception as e:
            logger.warning(f"EasyOCR initialization failed: {e}. Fallback to simulated OCR enabled.")
            self._engine_type = "mock"

    @property
    def engine_type(self) -> str:
        return self._engine_type

    def extract_tokens(self, image_np: np.ndarray) -> List[Dict[str, Any]]:
        """
        Extract OCR tokens with text, confidence, and bounding box [x, y, w, h]
        along with 4-corner polygon coordinates.
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

                    # Polygon is 4 points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                    xs = [p[0] for p in polygon]
                    ys = [p[1] for p in polygon]
                    x_min, x_max = max(0, min(xs)), min(w_img, max(xs))
                    y_min, y_max = max(0, min(ys)), min(h_img, max(ys))
                    w_box = max(1, x_max - x_min)
                    h_box = max(1, y_max - y_min)

                    tokens.append({
                        "text": text,
                        "confidence": round(score, 3),
                        "bbox": [int(x_min), int(y_min), int(w_box), int(h_box)],
                        "polygon": [[int(pt[0]), int(pt[1])] for pt in polygon],
                        "normalized_bbox": [
                            round(x_min / w_img, 4),
                            round(y_min / h_img, 4),
                            round(w_box / w_img, 4),
                            round(h_box / h_img, 4)
                        ]
                    })

        elif self._engine_type == "easyocr":
            results = self._engine.readtext(image_np)
            for item in results:
                polygon, text, score = item
                text = str(text).strip()
                if not text:
                    continue
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                x_min, x_max = max(0, min(xs)), min(w_img, max(xs))
                y_min, y_max = max(0, min(ys)), min(h_img, max(ys))
                w_box = max(1, x_max - x_min)
                h_box = max(1, y_max - y_min)

                tokens.append({
                    "text": text,
                    "confidence": round(float(score), 3),
                    "bbox": [int(x_min), int(y_min), int(w_box), int(h_box)],
                    "polygon": [[int(pt[0]), int(pt[1])] for pt in polygon],
                    "normalized_bbox": [
                        round(x_min / w_img, 4),
                        round(y_min / h_img, 4),
                        round(w_box / w_img, 4),
                        round(h_box / h_img, 4)
                    ]
                })

        return tokens

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
        Complete OCR pipeline:
        1. Input reading (filepath or numpy array)
        2. CLAHE & Bilateral enhancement
        3. OCR text token extraction
        4. Spatial line assembly
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found at {image_input}")
            img_bgr = cv2.imread(image_input)
            if img_bgr is None:
                raise ValueError(f"Failed to read image from {image_input}")
        elif isinstance(image_input, np.ndarray):
            img_bgr = image_input
        else:
            raise TypeError("Expected image file path or numpy ndarray.")

        h, w = img_bgr.shape[:2]
        enhanced_bgr, enhanced_gray = PreprocessingPipeline.enhance_for_ocr(img_bgr)
        tokens = self.extract_tokens(enhanced_bgr)
        
        # If tokens are few, try on enhanced grayscale
        if len(tokens) < 3 and self._engine_type != "mock":
            gray_3ch = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
            tokens_retry = self.extract_tokens(gray_3ch)
            if len(tokens_retry) > len(tokens):
                tokens = tokens_retry

        lines = self.assemble_lines(tokens)
        full_text = "\n".join([line["text"] for line in lines]) if lines else " ".join([t["text"] for t in tokens])

        return {
            "image_dimensions": {"width": w, "height": h},
            "engine_used": self._engine_type,
            "token_count": len(tokens),
            "line_count": len(lines),
            "raw_tokens": tokens,
            "assembled_lines": lines,
            "full_extracted_text": full_text
        }
