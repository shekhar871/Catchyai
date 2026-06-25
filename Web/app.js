// API Configuration
const API_URL = 'http://localhost:8000';

// State
let selectedFile = null;
let selectedImage = null;

// File Selection Handler
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    selectedFile = file;

    // Create image preview
    const reader = new FileReader();
    reader.onload = (e) => {
        selectedImage = e.target.result;
        document.getElementById('uploadZone').style.display = 'none';
        document.getElementById('imagePreview').style.display = 'block';
        document.getElementById('previewImage').src = selectedImage;
        document.getElementById('verifyBtn').disabled = false;
        document.getElementById('resultsContainer').style.display = 'none';
    };
    reader.readAsDataURL(file);
}

// Reset Image
function resetImage() {
    selectedFile = null;
    selectedImage = null;
    document.getElementById('uploadZone').style.display = 'block';
    document.getElementById('imagePreview').style.display = 'none';
    document.getElementById('previewImage').src = '';
    document.getElementById('verifyBtn').disabled = true;
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('fileInput').value = '';
}

// Scan Another
function scanAnother() {
    resetImage();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Verify/Analyze Image
async function handleVerify() {
    if (!selectedFile) return;

    // Show loading state
    document.getElementById('verifyBtn').style.display = 'none';
    document.getElementById('loadingContainer').style.display = 'flex';
    document.getElementById('scanLine').style.display = 'block';
    document.getElementById('loadingText').textContent = 'Uploading...';

    try {
        // Create FormData
        const formData = new FormData();
        formData.append('file', selectedFile);

        // Update loading text
        setTimeout(() => {
            document.getElementById('loadingText').textContent = 'Analyzing image patterns...';
        }, 1000);

        // Call API
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`Upload failed: ${response.status}`);
        }

        const results = await response.json();
        console.log('Analysis Results:', results);

        // Hide loading
        document.getElementById('loadingContainer').style.display = 'none';
        document.getElementById('scanLine').style.display = 'none';
        document.getElementById('verifyBtn').style.display = 'flex';

        // Display results
        displayResults(results);

    } catch (error) {
        console.error('Error:', error);
        alert('Failed to analyze image. Please check if the backend server is running on port 8000.');

        // Reset loading state
        document.getElementById('loadingContainer').style.display = 'none';
        document.getElementById('scanLine').style.display = 'none';
        document.getElementById('verifyBtn').style.display = 'flex';
    }
}

// Display Results
function displayResults(results) {
    const resultsContainer = document.getElementById('resultsContainer');
    const verdictCard = document.getElementById('verdictCard');
    const verdictIcon = document.getElementById('verdictIcon');
    const verdictTitle = document.getElementById('verdictTitle');
    const verdictScore = document.getElementById('verdictScore');
    const verdictConfidence = document.getElementById('verdictConfidence');
    const summaryText = document.getElementById('summaryText');
    const modelBreakdown = document.getElementById('modelBreakdown');

    // Determine verdict UI
    const verdict = results.final_verdict;
    const score = results.final_score;
    let color, iconPath, text;

    if (verdict === 'Fake') {
        color = '#ff4444';
        text = 'MANIPULATION DETECTED';
        iconPath = '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>';
    } else if (verdict === 'Suspicious') {
        color = '#ffbb33';
        text = 'SUSPICIOUS ACTIVITY';
        iconPath = '<path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>';
    } else if (verdict === 'Error') {
        color = '#888888';
        text = 'ANALYSIS FAILED';
        iconPath = '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>';
    } else {
        color = '#00c851';
        text = 'AUTHENTIC MEDIA';
        iconPath = '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>';
    }

    // Update verdict card
    verdictCard.style.borderColor = color;
    verdictIcon.style.fill = color;
    verdictIcon.innerHTML = iconPath;
    verdictTitle.textContent = text;
    verdictTitle.style.color = color;
    verdictScore.textContent = `Aggregate Score: ${score}%`;
    verdictConfidence.textContent = `Confidence: ${results.confidence}`;
    summaryText.textContent = results.summary;

    // Build model breakdown
    modelBreakdown.innerHTML = '';
    results.model_breakdown.forEach(model => {
        const modelRow = document.createElement('div');
        modelRow.className = 'model-row';

        const modelInfo = document.createElement('div');
        modelInfo.className = 'model-info';

        const modelName = document.createElement('span');
        modelName.className = 'model-name';
        modelName.textContent = model.model_name;

        const modelStatus = document.createElement('span');
        modelStatus.className = 'model-status';
        modelStatus.textContent = model.label;

        modelInfo.appendChild(modelName);
        modelInfo.appendChild(modelStatus);
        modelRow.appendChild(modelInfo);

        if (model.error) {
            const modelError = document.createElement('div');
            modelError.className = 'model-error';
            modelError.textContent = model.error;
            modelRow.appendChild(modelError);
        } else {
            const scoreContainer = document.createElement('div');
            scoreContainer.className = 'score-container';

            const progressBarBg = document.createElement('div');
            progressBarBg.className = 'progress-bar-bg';

            const progressBarFill = document.createElement('div');
            progressBarFill.className = 'progress-bar-fill';
            progressBarFill.style.width = `${Math.min(model.score, 100)}%`;
            progressBarFill.style.backgroundColor = getScoreColor(model.score);

            progressBarBg.appendChild(progressBarFill);

            const scoreText = document.createElement('span');
            scoreText.className = 'score-text';
            scoreText.textContent = `${Math.round(model.score)}%`;

            scoreContainer.appendChild(progressBarBg);
            scoreContainer.appendChild(scoreText);
            modelRow.appendChild(scoreContainer);
        }

        modelBreakdown.appendChild(modelRow);
    });

    // Show results with smooth scroll
    resultsContainer.style.display = 'block';
    setTimeout(() => {
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

// Helper: Get Score Color
function getScoreColor(score) {
    if (score > 75) return '#ff4444'; // Fake
    if (score > 60) return '#ffbb33'; // Suspicious
    return '#00c851'; // Authentic
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Catchy AI Web Interface Loaded');
    console.log('Backend API:', API_URL);
});
