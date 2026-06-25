import os
import httpx
import asyncio
import base64
import time
import logging
import json
import re
from .base import BaseDetector, DetectorResult

logger = logging.getLogger("uvicorn.error")

class GeminiVisionDetector(BaseDetector):
    """
    Google Gemini Vision API integration with retry logic.
    """
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        # Use the correct model name - gemini-1.5-flash or gemini-1.5-pro
        self.model = "gemini-1.5-flash"

    async def analyze_image(self, image_bytes: bytes, filename: str) -> DetectorResult:
        start_time = time.time()
        retry_count = 0
        
        if not self.api_key:
            return DetectorResult(
                model_name="Gemini Vision",
                score=0.0,
                label="Skipped",
                error="No GEMINI_API_KEY environment variable",
                latency_ms=0.0,
                retry_count=0
            )

        # Try up to 3 times with increasing delays
        for attempt in range(3):
            try:
                result = await self._analyze_internal(image_bytes, filename, start_time)
                result.retry_count = retry_count
                return result
            except Exception as e:
                retry_count += 1
                error_str = str(e).lower()
                
                # Don't retry on certain errors
                if "api key" in error_str or "permission" in error_str:
                    return DetectorResult(
                        model_name="Gemini Vision",
                        score=0.0,
                        label="Error",
                        error=f"Authentication error: {str(e)[:150]}",
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )
                
                if attempt < 2:  # Retry
                    wait_time = (attempt + 1) * 2  # 2s, 4s
                    logger.warning(f"Gemini attempt {attempt + 1}/3 failed: {e}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:  # Final failure
                    logger.error(f"Gemini final error: {e}")
                    return DetectorResult(
                        model_name="Gemini Vision",
                        score=0.0,
                        label="Error",
                        error=str(e)[:200],
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )

    async def _analyze_internal(self, image_bytes: bytes, filename: str, start_time: float) -> DetectorResult:
        """Internal analysis method"""
        try:
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Correct Gemini API endpoint
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            
            headers = {
                "Content-Type": "application/json"
            }

            # Improved prompt for deepfake detection
            prompt = """Analyze this image for signs of AI generation or deepfake manipulation. 
            
Consider:
- Unnatural facial features or skin texture
- Inconsistent lighting or shadows
- Artifacts around edges or hair
- Unrealistic eyes or teeth
- Digital manipulation signs

Respond ONLY with valid JSON in this exact format:
{
    "verdict": "Real" or "Fake" or "Suspicious",
    "score": <0-100 integer where 0=definitely real, 100=definitely fake>,
    "reasoning": "<brief explanation>"
}"""

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64_image
                            }}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,  # Lower for more consistent results
                    "maxOutputTokens": 500
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    error_text = response.text[:300]
                    logger.error(f"Gemini API Error {response.status_code}: {error_text}")
                    
                    # More specific error messages
                    if response.status_code == 404:
                        error_msg = f"Model '{self.model}' not found. Check model name or API access."
                    elif response.status_code == 401 or response.status_code == 403:
                        error_msg = "Invalid API key or insufficient permissions"
                    elif response.status_code == 429:
                        error_msg = "Rate limit exceeded"
                    else:
                        error_msg = f"API Error {response.status_code}"
                    
                    return DetectorResult(
                        model_name="Gemini Vision",
                        score=0.0,
                        label="Error",
                        error=error_msg,
                        latency_ms=(time.time() - start_time) * 1000
                    )

                result = response.json()
                
                # Parse response with multiple fallback strategies
                try:
                    # Strategy 1: Extract text content
                    text_content = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Strategy 2: Try to parse as JSON
                    try:
                        # Remove markdown code blocks if present
                        text_content = re.sub(r'```json\s*|\s*```', '', text_content)
                        content = json.loads(text_content.strip())
                        
                        score = float(content.get('score', 0))
                        verdict = content.get('verdict', 'Unknown')
                        reasoning = content.get('reasoning', 'No reasoning provided')
                        
                    except json.JSONDecodeError:
                        # Strategy 3: Extract score from text
                        score_match = re.search(r'score["\s:]+(\d+)', text_content, re.IGNORECASE)
                        if score_match:
                            score = float(score_match.group(1))
                        else:
                            score = 50.0  # Default to uncertain
                        
                        # Infer verdict from keywords
                        text_lower = text_content.lower()
                        if 'fake' in text_lower or 'generated' in text_lower or 'ai' in text_lower:
                            verdict = "Fake"
                        elif 'suspicious' in text_lower or 'uncertain' in text_lower:
                            verdict = "Suspicious"
                        else:
                            verdict = "Real"
                        
                        reasoning = text_content[:200]  # Use first 200 chars as reasoning
                    
                    # Determine label based on score
                    if score > 75:
                        label = "Fake"
                    elif score > 50:
                        label = "Suspicious"
                    else:
                        label = "Real"

                    return DetectorResult(
                        model_name="Gemini Vision",
                        score=score,
                        label=label,
                        details=reasoning,
                        latency_ms=(time.time() - start_time) * 1000
                    )
                    
                except (KeyError, IndexError) as e:
                    logger.error(f"Gemini response parse error: {e}")
                    logger.error(f"Response structure: {json.dumps(result, indent=2)[:500]}")
                    return DetectorResult(
                        model_name="Gemini Vision",
                        score=0.0,
                        label="Error",
                        error=f"Failed to parse API response: {str(e)}",
                        latency_ms=(time.time() - start_time) * 1000
                    )

        except httpx.TimeoutException as e:
            raise Exception(f"Request timeout: {e}")
        except Exception as e:
            # Re-raise to be caught by outer retry logic
            raise
