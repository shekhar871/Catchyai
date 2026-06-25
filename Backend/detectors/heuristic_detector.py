import time
import logging
from .base import BaseDetector, DetectorResult

logger = logging.getLogger("uvicorn.error")

class HeuristicDetector(BaseDetector):
    """
    Simple heuristic-based detector as a free fallback.
    This is a placeholder that always returns a neutral score.
    In production, this could be replaced with a local ML model or Hive AI API.
    """
    def __init__(self):
        self.enabled = True  # Always available, no API key required

    async def analyze_image(self, image_bytes: bytes, filename: str) -> DetectorResult:
        start_time = time.time()
        
        try:
            # Simple heuristic checks
            file_size = len(image_bytes)
            
            # For now, return neutral/uncertain result
            # In production, you could:
            # - Run a local TensorFlow/PyTorch model
            # - Use Hive AI API
            # - Analyze image metadata/EXIF
            # - Check for common deepfake artifacts
            
            return DetectorResult(
                model_name="Heuristic Baseline",
                score=50.0,  # Neutral - not confident either way
                label="Suspicious",
                details=f"File size: {file_size} bytes. Baseline heuristic check completed.",
                latency_ms=(time.time() - start_time) * 1000,
                retry_count=0
            )
            
        except Exception as e:
            logger.error(f"Heuristic detector error: {e}")
            return DetectorResult(
                model_name="Heuristic Baseline",
                score=50.0,
                label="Suspicious",
                error=str(e)[:200],
                latency_ms=(time.time() - start_time) * 1000,
                retry_count=0
            )
