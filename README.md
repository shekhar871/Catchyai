# Catchy AI - Deepfake Detection System

A professional, production-grade deepfake detection application featuring a robust multi-model ensemble backend and a sleek React Native frontend.

## Features

### Backend (FastAPI)
- **Multi-Model Ensemble:** Integrates Reality Defender, OpenAI GPT-4 Vision, Gemini Pro Vision, and Heuristic analysis.
- **Robust Error Handling:** Automatic retries, circuit breakers, and fallback mechanisms.
- **Weighted Voting:** Intelligent scoring system based on model reliability and confidence.
- **Async Processing:** High-performance asynchronous request handling.
- **Production Ready:** Structured logging, input validation, and stable API endpoints.

### Frontend (React Native Expo)
- **Professional UI:** Dark-themed, premium design with smooth animations (`react-native-reanimated`).
- **Real-time Analysis:** Live upload progress and analysis status.
- **Detailed Results:** Comprehensive breakdown of model scores, confidence levels, and explanations.
- **Retry Logic:** User-friendly error handling with retry options.
- **Cross-Platform:** Designed for both iOS/Android (via Expo Go) and Web.

## Installation & Setup

### Prerequisites
- Python 3.8+
- Node.js & npm
- Expo CLI

### 1. Backend Setup
```bash
cd Backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Environment Variables:**
Create a `.env` file in `Backend/` with your API keys:
```env
REALITY_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

**Run Server:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd Frontend
npm install
```

**Run App:**
```bash
npx expo start
```
- Press `w` for Web
- Scan QR code for Mobile (Expo Go)

## API Endpoints

- `POST /upload`: Analyze an image file.
- `GET /health`: Check system status and active models.
- `GET /`: API information.

## Architecture

The system uses a voting ensemble where each model analyzes the image independently. The results are normalized, weighted, and aggregated to form a final verdict (Real/Fake/Suspicious) with a confidence score.
