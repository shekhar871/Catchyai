from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional

class DetectorResult(BaseModel):
    model_name: str
    score: float  # 0.0 to 100.0
    label: str    # "Real", "Fake", "Suspicious", "Error", "Timeout"
    details: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    retry_count: int = 0  # Number of retries attempted
    
    class Config:
        frozen = False  # Allow updates during retries

class BaseDetector(ABC):
    """
    Base class for all deepfake detectors.
    All detectors must implement async analyze_image method.
    """
    
    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, filename: str) -> DetectorResult:
        """
        Analyze the given image bytes and return a standardized result.
        
        Args:
            image_bytes: Raw image file bytes
            filename: Original filename (for context/logging)
            
        Returns:
            DetectorResult with score, label, and metadata
        """
        pass
    
    def get_model_name(self) -> str:
        """Return human-readable model name"""
        return self.__class__.__name__.replace("Detector", "")
