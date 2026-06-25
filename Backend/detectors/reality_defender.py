import os
import httpx
import asyncio
import logging
import time
from .base import BaseDetector, DetectorResult
from services.retry_handler import async_retry, RetryConfig

logger = logging.getLogger("uvicorn.error")

class RealityDefenderDetector(BaseDetector):
    """
    Reality Defender API integration with retry logic and optimized polling.
    """
    def __init__(self):
        self.api_key = os.getenv("REALITY_API_KEY")
        self.base_url = os.getenv("REALITY_BASE", "https://api.prd.realitydefender.xyz")
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        # Polling configuration with exponential backoff
        self.poll_intervals = [1, 2, 3, 5, 8, 10, 15]  # seconds
        self.max_poll_time = 90  # 90 seconds total timeout

    async def analyze_image(self, image_bytes: bytes, filename: str) -> DetectorResult:
        """Main entry point with retry wrapper"""
        start_time = time.time()
        retry_count = 0
        
        if not self.api_key:
            return DetectorResult(
                model_name="Reality Defender",
                score=0.0,
                label="Error",
                error="Missing REALITY_API_KEY environment variable",
                latency_ms=0.0,
                retry_count=0
            )

        # Try up to 2 times (1 initial + 1 retry)
        for attempt in range(2):
            try:
                result = await self._analyze_with_timeout(image_bytes, filename, start_time)
                result.retry_count = retry_count
                return result
            except asyncio.TimeoutError:
                retry_count += 1
                if attempt < 1:  # Only retry once
                    logger.warning(f"Reality Defender timeout, retrying... (attempt {attempt + 2}/2)")
                    await asyncio.sleep(2)
                else:
                    return DetectorResult(
                        model_name="Reality Defender",
                        score=0.0,
                        label="Timeout",
                        error="Analysis timed out after 90 seconds",
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )
            except Exception as e:
                retry_count += 1
                if attempt < 1:
                    logger.warning(f"Reality Defender error, retrying: {e}")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Reality Defender final error: {e}")
                    return DetectorResult(
                        model_name="Reality Defender",
                        score=0.0,
                        label="Error",
                        error=str(e)[:200],  # Truncate error messages
                        latency_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count
                    )

    async def _analyze_with_timeout(self, image_bytes: bytes, filename: str, start_time: float) -> DetectorResult:
        """Internal analysis with timeout"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Step 1: Get Presigned URL
                presign_url = f"{self.base_url}/api/files/aws-presigned"
                presign_payload = {"fileName": filename}
                
                presign_resp = await client.post(
                    presign_url,
                    json=presign_payload,
                    headers=self.headers
                )
                
                if presign_resp.status_code >= 300:
                    error_text = presign_resp.text[:200]
                    return DetectorResult(
                        model_name="Reality Defender",
                        score=0.0,
                        label="Error",
                        error=f"Presign failed ({presign_resp.status_code}): {error_text}",
                        latency_ms=(time.time() - start_time) * 1000
                    )
                
                presign_data = presign_resp.json()
                
                # Handle nested response structure
                if "response" in presign_data and "signedUrl" in presign_data["response"]:
                    signed_url = presign_data["response"]["signedUrl"]
                else:
                    signed_url = presign_data.get("signedUrl")
                
                request_id = presign_data.get("requestId")

                if not signed_url or not request_id:
                    return DetectorResult(
                        model_name="Reality Defender",
                        score=0.0,
                        label="Error",
                        error="Invalid presign response - missing signedUrl or requestId",
                        latency_ms=(time.time() - start_time) * 1000
                    )

                # Step 2: Upload File to S3
                upload_resp = await client.put(signed_url, content=image_bytes, timeout=45)
                
                if upload_resp.status_code not in (200, 201, 204):
                    return DetectorResult(
                        model_name="Reality Defender",
                        score=0.0,
                        label="Error",
                        error=f"Upload failed with status {upload_resp.status_code}",
                        latency_ms=(time.time() - start_time) * 1000
                    )

                # Step 3: Poll for Result with exponential backoff
                check_url = f"{self.base_url}/api/media/users/{request_id}"
                deadline = time.time() + self.max_poll_time
                poll_index = 0
                
                while time.time() < deadline:
                    resp = await client.get(check_url, headers=self.headers)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status")
                        
                        if status == "COMPLETE":
                            return self._parse_result(data, start_time)
                        elif status == "FAILED":
                            error_msg = data.get("error", "Analysis failed")
                            return DetectorResult(
                                model_name="Reality Defender",
                                score=0.0,
                                label="Error",
                                error=f"Reality Defender analysis failed: {error_msg}",
                                latency_ms=(time.time() - start_time) * 1000
                            )
                        # Status is PENDING or PROCESSING - continue polling
                    
                    # Use exponential backoff for polling
                    if poll_index < len(self.poll_intervals):
                        wait_time = self.poll_intervals[poll_index]
                        poll_index += 1
                    else:
                        wait_time = self.poll_intervals[-1]  # Max interval
                    
                    logger.debug(f"Reality Defender status: {data.get('status')}, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                
                # Timeout reached
                raise asyncio.TimeoutError("Polling exceeded 90 seconds")

        except httpx.TimeoutException as e:
            raise asyncio.TimeoutError(f"HTTP timeout: {e}")
        except httpx.HTTPError as e:
            raise Exception(f"HTTP error: {e}")

    def _parse_result(self, data: dict, start_time: float) -> DetectorResult:
        """Parse Reality Defender API response"""
        try:
            summary = data.get("resultsSummary", {})
            metadata = summary.get("metadata", {})
            final_score = metadata.get("finalScore", 0)  # 0-100
            
            # Determine label based on score
            if final_score > 75:
                label = "Fake"
            elif final_score > 60:
                label = "Suspicious"
            else:
                label = "Real"

            # Extract details
            request_id = data.get("requestId", "unknown")
            
            return DetectorResult(
                model_name="Reality Defender",
                score=float(final_score),
                label=label,
                details=f"Request ID: {request_id}",
                latency_ms=(time.time() - start_time) * 1000
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Reality Defender parse error: {e}")
            return DetectorResult(
                model_name="Reality Defender",
                score=0.0,
                label="Error",
                error=f"Failed to parse response: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )
