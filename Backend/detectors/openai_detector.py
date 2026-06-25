import os
import httpx
import asyncio
import base64
import time
import logging
from .base import BaseDetector, DetectorResult

logger = logging.getLogger("uvicorn.error")

class OpenAIDetector(BaseDetector):
    """
    OpenAI GPT-4 Vision API integration for deepfake detection.
    """
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = "gpt-4-vision-preview"  # or "gpt-4o" for newer model
        self.api_base = "https://api.openai.com/v1/chat/completions"

    async def analyze_image(self, image_bytes: bytes, filename: str) -> DetectorResult:
        start_time = time.time()
        retry_count = 0
        
        if not self.api_key:
            return DetectorResult(
                model_name="OpenAI Vision",
                score=0.0,
                label="Skipped",
                error="No OPENAI_API_KEY environment variable",
                latency_ms=0.0,
                retry_count=0
            )

        # Try up to 3 times with exponential backoff
        for attempt in range(3):
            try:
                result = await self._analyze_internal(image_bytes, filename, start_time)
                result.retry_count = retry_count
                return result
            except Exception as e:
                retry_count += 1
                error_str = str(e).lower()
                
                # Don't retry on authentication errors
                if "api key" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
                    return DetectorResult(
                        model_name="OpenAI Vision",
                        score=0.0,
                        label="Error",
                        error=f"Authentication error: {str(e)[:150]}",
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )
                
                if attempt < 2:  # Retry
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    logger.warning(f"OpenAI attempt {attempt + 1}/3 failed: {e}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:  # Final failure
                    logger.error(f"OpenAI final error: {e}")
                    return DetectorResult(
                        model_name="OpenAI Vision",
                        score=0.0,
                        label="Error",
                        error=str(e)[:200],
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )

    async def _analyze_internal(self, image_bytes: bytes, filename: str, start_time: float) -> DetectorResult:
        """Internal analysis method"""
        try:
            # Encode image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Detailed prompt for deepfake detection
            prompt = """Analyze this image for signs of AI generation or deepfake manipulation.

Look for these indicators:
1. Facial inconsistencies (unnatural skin texture, asymmetry)
2. Lighting and shadow anomalies
3. Background artifacts or blur patterns  
4. Edge artifacts around faces or hair
5. Unrealistic eyes, teeth, or facial features
6. Digital manipulation signatures

Provide your analysis in this exact JSON format:
{
    "verdict": "Real" | "Fake" | "Suspicious",
    "score": <integer 0-100, where 0=definitely real, 100=definitely fake>,
    "confidence": "High" | "Medium" | "Low",
    "reasoning": "<brief explanation of key findings>"
}

Only respond with the JSON, no additional text."""

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"  # High detail for better analysis
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.2  # Low temperature for consistent results
            }

            async with httpx.AsyncClient(timeout=40) as client:
                response = await client.post(self.api_base, headers=headers, json=payload)
                
                if response.status_code != 200:
                    error_text = response.text[:300]
                    logger.error(f"OpenAI API Error {response.status_code}: {error_text}")
                    
                    if response.status_code == 401:
                        error_msg = "Invalid API key"
                    elif response.status_code == 429:
                        error_msg = "Rate limit exceeded"
                    elif response.status_code == 400:
                        error_msg = "Invalid request format"
                    else:
                        error_msg = f"API Error {response.status_code}"
                    
                    return DetectorResult(
                        model_name="OpenAI Vision",
                        score=0.0,
                        label="Error",
                        error=error_msg,
                        latency_ms=(time.time() - start_time) * 1000
                    )

                result = response.json()
                
                try:
                    # Extract response text
                    content = result['choices'][0]['message']['content']
                    
                    # Parse JSON response
                    import json
                    import re
                    
                    # Remove markdown code blocks if present
                    content = re.sub(r'```json\s*|\s*```', '', content)
                    content = content.strip()
                    
                    parsed = json.loads(content)
                    
                    score = float(parsed.get('score', 50))
                    verdict = parsed.get('verdict', 'Suspicious')
                    reasoning = parsed.get('reasoning', 'No reasoning provided')
                    
                    # Determine label from score
                    if score > 75:
                        label = "Fake"
                    elif score > 50:
                        label = "Suspicious"
                    else:
                        label = "Real"

                    return DetectorResult(
                        model_name="OpenAI Vision",
                        score=score,
                        label=label,
                        details=reasoning,
                        latency_ms=(time.time() - start_time) * 1000
                    )
                    
                except (KeyError, json.JSONDecodeError, ValueError) as e:
                    logger.error(f"OpenAI parse error: {e}")
                    logger.error(f"Response: {content[:500]}")
                    return DetectorResult(
                        model_name="OpenAI Vision",
                        score=0.0,
                        label="Error",
                        error=f"Failed to parse response: {str(e)}",
                        latency_ms=(time.time() - start_time) * 1000
                    )

        except httpx.TimeoutException as e:
            raise Exception(f"Request timeout: {e}")
        except Exception as e:
            raise  # Re-raise for retry logic
