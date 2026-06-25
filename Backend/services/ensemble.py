import asyncio
import logging
from typing import List, Dict, Any, Optional
from detectors.base import BaseDetector, DetectorResult
from detectors.reality_defender import RealityDefenderDetector
from detectors.gemini_detector import GeminiVisionDetector
from detectors.openai_detector import OpenAIDetector
from detectors.heuristic_detector import HeuristicDetector

logger = logging.getLogger("uvicorn.error")

class EnsembleService:
    """
    Production-grade ensemble service for multi-model deepfake detection.
    
    Features:
    - Parallel execution of all detectors
    - Graceful handling of partial failures
    - Weighted voting with confidence scores
    - Automatic fallback to available models
    - Performance metrics and latency tracking
    """
    
    def __init__(self):
        # Initialize all available detectors
        self.detectors: List[BaseDetector] = [
            RealityDefenderDetector(),
            GeminiVisionDetector(),
            OpenAIDetector(),
            HeuristicDetector(),  # Always available as fallback
        ]
        
        # Model weights for weighted voting
        # Higher weight = more trusted
        self.weights = {
            "Reality Defender": 0.35,  # Commercial, specialized
            "Gemini Vision": 0.30,     # Google's vision AI
            "OpenAI Vision": 0.30,     # GPT-4 Vision
            "Heuristic Baseline": 0.05  # Fallback only
        }
        
        # Minimum number of successful models required
        self.min_models_required = 1

    async def analyze(self, image_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Run multi-model ensemble analysis on an image.
        
        Args:
            image_bytes: Raw image file bytes
            filename: Original filename
            
        Returns:
            Dictionary with final verdict, score, confidence, and model breakdown
        """
        logger.info(f"Starting ensemble analysis for {filename}")
        
        # Run all detectors in parallel
        tasks = [d.analyze_image(image_bytes, filename) for d in self.detectors]
        
        # Gather results - return_exceptions=True prevents one failure from crashing all
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        results: List[DetectorResult] = []
        for i, res in enumerate(raw_results):
            if isinstance(res, Exception):
                detector_name = self.detectors[i].__class__.__name__.replace("Detector", "")
                logger.error(f"Detector {detector_name} crashed: {res}")
                # Create error result
                results.append(DetectorResult(
                    model_name=detector_name,
                    score=0.0,
                    label="Error",
                    error=f"System Error: {str(res)[:150]}",
                    latency_ms=0.0,
                    retry_count=0
                ))
            else:
                results.append(res)
        
        # Separate successful vs failed models
        successful_results = [r for r in results if r.label not in ["Error", "Skipped", "Timeout"]]
        failed_results = [r for r in results if r.label in ["Error", "Skipped", "Timeout"]]
        
        logger.info(f"Analysis complete: {len(successful_results)} successful, {len(failed_results)} failed")
        
        # Check if we have minimum required successful models
        if len(successful_results) < self.min_models_required:
            return self._create_error_response(results, "Insufficient models available")
        
        # Calculate ensemble metrics
        final_verdict, final_score, confidence = self._calculate_ensemble_verdict(successful_results)
        summary = self._generate_summary(successful_results)
        
        return {
            "final_verdict": final_verdict,
            "final_score": round(final_score, 1),
            "confidence": confidence,
            "summary": summary,
            "model_breakdown": [r.dict() for r in results],
            "metrics": {
                "total_models": len(results),
                "successful_models": len(successful_results),
                "failed_models": len(failed_results),
                "average_latency_ms": round(sum(r.latency_ms for r in results) / len(results), 1) if results else 0
            }
        }

    def _calculate_ensemble_verdict(self, successful_results: List[DetectorResult]) -> tuple[str, float, str]:
        """
        Calculate final verdict using weighted voting.
        
        Returns:
            (verdict, score, confidence)
        """
        if not successful_results:
            return "Error", 0.0, "None"
        
        # Weighted score calculation
        total_score = 0.0
        total_weight = 0.0
        
        for result in successful_results:
            weight = self.weights.get(result.model_name, 0.1)
            total_score += result.score * weight
            total_weight += weight
        
        if total_weight > 0:
            final_score = total_score / total_weight
        else:
            # Fallback: simple average
            final_score = sum(r.score for r in successful_results) / len(successful_results)
        
        # Determine verdict based on score thresholds
        if final_score > 75:
            verdict = "Fake"
            confidence = "High"
        elif final_score > 60:
            verdict = "Suspicious"
            confidence = "Medium"
        elif final_score > 40:
            verdict = "Suspicious"
            confidence = "Low"
        else:
            verdict = "Real"
            # High confidence if multiple models agree on "Real"
            real_count = sum(1 for r in successful_results if r.label == "Real")
            confidence = "High" if real_count >= 2 else "Medium"
        
        # Adjust confidence based on model agreement
        if len(successful_results) >= 3:
            # Check for consensus
            labels = [r.label for r in successful_results]
            most_common = max(set(labels), key=labels.count)
            agreement_ratio = labels.count(most_common) / len(labels)
            
            if agreement_ratio >= 0.75:  # 75%+ agreement
                # Keep confidence as is
                pass
            elif agreement_ratio >= 0.5:  # 50-75% agreement
                if confidence == "High":
                    confidence = "Medium"
            else:  # Less than 50% agreement
                confidence = "Low"
        
        return verdict, final_score, confidence

    def _generate_summary(self, successful_results: List[DetectorResult]) -> str:
        """Generate human-readable summary of model results"""
        if not successful_results:
            return "No models successfully analyzed the image."
        
        summary_parts = []
        for result in successful_results:
            if result.details:
                summary_parts.append(f"{result.model_name}: {result.label} ({result.score:.1f}%)")
            else:
                summary_parts.append(f"{result.model_name}: {result.label} ({result.score:.1f}%)")
        
        return " | ".join(summary_parts)

    def _create_error_response(self, all_results: List[DetectorResult], message: str) -> Dict[str, Any]:
        """Create error response when analysis fails"""
        return {
            "final_verdict": "Error",
            "final_score": 0.0,
            "confidence": "None",
            "summary": message,
            "model_breakdown": [r.dict() for r in all_results],
            "metrics": {
                "total_models": len(all_results),
                "successful_models": 0,
                "failed_models": len(all_results),
                "average_latency_ms": 0
            }
        }
