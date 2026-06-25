# app.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
from dotenv import load_dotenv
from services.ensemble import EnsembleService
from PIL import Image
import io

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Catchy AI - Multi-Model Deepfake Detector",
    description="Production-grade deepfake detection API using multi-model ensemble",
    version="2.0.0"
)

# Initialize Ensemble Service
ensemble_service = EnsembleService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow ALL origins to prevent any CORS blocking during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Incoming request: {request.method} {request.url}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"Request finished: {response.status_code} (took {process_time:.2f}ms)")
        return response
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error": str(e)}
        )

def validate_image(image_bytes: bytes) -> tuple[bool, str]:
    """Validate image format and size"""
    try:
        if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
            return False, "Image too large (max 10MB)"
            
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()  # Verify it's an image
        
        if img.format not in ['JPEG', 'PNG', 'WEBP']:
            return False, f"Unsupported format: {img.format}. Use JPEG, PNG, or WEBP."
            
        return True, ""
    except Exception as e:
        return False, f"Invalid image file: {e}"

@app.post("/upload")
async def analyze_image(
    file: UploadFile = File(...),
):
    """
    Uploads an image and runs it through the Multi-Model Ensemble.
    Returns a combined verdict and individual model results.
    """
    filename = file.filename or "upload.bin"
    logger.info(f"Received file: {filename}")

    try:
        # Read file bytes
        image_bytes = await file.read()
        
        # Validate image
        is_valid, error_msg = validate_image(image_bytes)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Run Ensemble Analysis
        result = await ensemble_service.analyze(image_bytes, filename)
        
        logger.info(f"Analysis complete. Verdict: {result['final_verdict']}")
        return result

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Ensemble Error: {e}")
        # Return a structured error response instead of crashing
        return JSONResponse(
            status_code=500,
            content={
                "final_verdict": "Error",
                "final_score": 0.0,
                "confidence": "None",
                "summary": f"System Error: {str(e)}",
                "model_breakdown": []
            }
        )

@app.get("/")
def root():
    return {
        "status": "online", 
        "service": "Catchy AI Ensemble",
        "version": "2.0.0",
        "models": [d.get_model_name() for d in ensemble_service.detectors]
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "active_models": len(ensemble_service.detectors)
    }