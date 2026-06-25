import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Image,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  Vibration,
  View,
  Alert,
  StatusBar
} from 'react-native';
import Animated, {
  FadeIn,
  SlideInDown,
  SlideOutDown,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { API_URL } from '../../src/config';

// Types matching Backend Response
interface AnalysisResult {
  final_verdict: string;
  final_score: number;
  confidence: string;
  summary: string;
  model_breakdown: {
    model_name: string;
    score: number;
    label: string;
    error?: string;
    details?: string;
    retry_count?: number;
  }[];
  metrics?: {
    total_models: number;
    successful_models: number;
    failed_models: number;
    average_latency_ms: number;
  };
}

interface ErrorState {
  visible: boolean;
  title: string;
  message: string;
  code?: string;
}

// --- COMPONENTS ---

const ErrorBanner = ({ error, onDismiss }: { error: ErrorState; onDismiss: () => void }) => {
  if (!error.visible) return null;

  return (
    <Animated.View
      entering={SlideInDown.springify()}
      exiting={SlideOutDown}
      style={styles.errorBanner}
    >
      <View style={styles.errorContent}>
        <View style={styles.errorIcon}>
          <Ionicons name="alert-circle" size={32} color="#ff4444" />
        </View>
        <View style={styles.errorTextContainer}>
          <Text style={styles.errorTitle}>{error.title}</Text>
          <Text style={styles.errorMessage}>{error.message}</Text>
          {error.code && <Text style={styles.errorCode}>Code: {error.code}</Text>}
        </View>
        <TouchableOpacity onPress={onDismiss} style={styles.errorClose}>
          <Ionicons name="close" size={24} color="#fff" />
        </TouchableOpacity>
      </View>
    </Animated.View>
  );
};

const ScanLine = () => {
  const translateY = useSharedValue(0);

  useEffect(() => {
    translateY.value = withRepeat(
      withTiming(280, { duration: 2000, easing: Easing.linear }),
      -1,
      true
    );
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
  }));

  return (
    <Animated.View style={[styles.scanLine, animatedStyle]}>
      <LinearGradient
        colors={['rgba(79, 172, 254, 0)', '#4facfe', 'rgba(79, 172, 254, 0)']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={styles.scanGradient}
      />
    </Animated.View>
  );
};

const HomeScreen: React.FC = () => {
  const [selectedImage, setSelectedImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [results, setResults] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [step, setStep] = useState<'idle' | 'uploading' | 'analyzing' | 'complete'>('idle');
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [error, setError] = useState<ErrorState>({ visible: false, title: '', message: '' });

  const showError = (title: string, message: string, code?: string) => {
    Vibration.vibrate();
    setError({ visible: true, title, message, code });
  };

  const fetchWithRetry = async (url: string, options: RequestInit = {}, retries = 3, backoff = 1000) => {
    try {
      const headers = {
        ...options.headers,
        'Accept': 'application/json',
      };

      // Add 90s timeout (matching backend max timeout)
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), 90000);

      const res = await fetch(url, { ...options, headers, signal: controller.signal });
      clearTimeout(id);

      if (!res.ok) {
        // Handle 500 errors that return JSON
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
          const errorData = await res.json();
          // If it's a structured error from our backend, return it as result if possible, or throw
          if (errorData.final_verdict === "Error") {
            return { ok: true, json: () => Promise.resolve(errorData) } as Response;
          }
          throw new Error(errorData.detail || `Server Error: ${res.status}`);
        }

        if (res.status >= 500 && retries > 0) {
          throw new Error(`Retryable error: ${res.status}`);
        }
        throw new Error(`Request failed with status ${res.status}`);
      }
      return res;
    } catch (err: any) {
      if (retries > 0 && (err.message.includes('Retryable') || err.name === 'AbortError' || err.message.includes('Network request failed'))) {
        console.log(`Retrying... attempts left: ${retries}`);
        await new Promise(r => setTimeout(r, backoff));
        return fetchWithRetry(url, options, retries - 1, backoff * 1.5);
      }
      throw err;
    }
  };

  const pickImage = async () => {
    try {
      const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permissionResult.granted) {
        showError("Permission Denied", "We need access to your photos to verify them.", "PERM_01");
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        quality: 0.8, // Optimize size
      });

      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        // Check file size if possible (approximate)
        if (asset.fileSize && asset.fileSize > 10 * 1024 * 1024) {
          showError("File Too Large", "Please select an image under 10MB.", "SIZE_01");
          return;
        }

        setSelectedImage(asset);
        setResults(null);
        setError({ ...error, visible: false });
      }
    } catch (e) {
      showError("Gallery Error", "Could not open image gallery.", "GAL_01");
    }
  };

  const handleVerify = async () => {
    if (!selectedImage) return;

    setLoading(true);
    setStep('uploading');
    setResults(null);
    setUploadProgress(0);
    setError({ ...error, visible: false });

    try {
      // Simulate upload progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) return 90;
          return prev + 10;
        });
      }, 300);

      const formData = new FormData();

      if (Platform.OS === 'web') {
        const res = await fetch(selectedImage.uri);
        const blob = await res.blob();
        let filename = selectedImage.fileName || 'upload.jpg';
        const fileType = blob.type || 'image/jpeg';

        // Ensure extension matches mime type
        if (fileType === 'image/png' && !filename.endsWith('.png')) filename += '.png';
        if (fileType === 'image/jpeg' && !filename.match(/\.jpe?g$/)) filename += '.jpg';

        formData.append('file', blob, filename);
      } else {
        const filename = selectedImage.fileName || selectedImage.uri.split('/').pop() || 'upload.jpg';
        const match = /\.(\w+)$/.exec(filename);
        const type = match ? `image/${match[1]}` : 'image/jpeg';

        formData.append('file', {
          uri: selectedImage.uri,
          name: filename,
          type: type,
        } as any);
      }

      setStep('analyzing');

      // Use configured API URL
      const uploadRes = await fetchWithRetry(`${API_URL}/upload`, {
        method: 'POST',
        body: formData,
      });

      clearInterval(progressInterval);
      setUploadProgress(100);

      const data = await uploadRes.json();
      console.log("Ensemble Result:", data);

      if (data.final_verdict === "Error" && data.model_breakdown.length === 0) {
        throw new Error(data.summary || "Analysis failed");
      }

      setResults(data);
      setStep('complete');

    } catch (err: any) {
      console.error(err);
      showError("Analysis Failed", err.message || "Could not connect to server.", "NET_01");
      setStep('idle');
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score > 75) return '#ff4444'; // Fake
    if (score > 50) return '#ffbb33'; // Suspicious
    return '#00c851'; // Real
  };

  const getVerdictUI = () => {
    if (!results) return null;

    const verdict = results.final_verdict;

    let color, icon, text;

    if (verdict === 'Fake') {
      color = '#ff4444';
      icon = 'warning';
      text = 'MANIPULATION DETECTED';
    } else if (verdict === 'Suspicious') {
      color = '#ffbb33';
      icon = 'alert-circle';
      text = 'SUSPICIOUS ACTIVITY';
    } else if (verdict === 'Error') {
      color = '#888888';
      icon = 'help-circle';
      text = 'ANALYSIS FAILED';
    } else {
      color = '#00c851';
      icon = 'checkmark-circle';
      text = 'AUTHENTIC MEDIA';
    }

    return { color, icon, text };
  };

  const renderResults = () => {
    if (!results) return null;
    const ui = getVerdictUI();

    return (
      <Animated.View entering={FadeIn} style={styles.resultContainer}>
        <View style={[styles.verdictCard, { borderColor: ui?.color }]}>
          <Ionicons name={ui?.icon as any} size={48} color={ui?.color} />
          <Text style={[styles.verdictTitle, { color: ui?.color }]}>{ui?.text}</Text>
          <Text style={styles.verdictScore}>
            Score: {results.final_score}%
          </Text>
          <Text style={styles.verdictConfidence}>
            Confidence: {results.confidence}
          </Text>
        </View>

        <View style={styles.detailsContainer}>
          <Text style={styles.subHeader}>MODEL BREAKDOWN</Text>

          {results.model_breakdown.map((model, idx) => (
            <View key={idx} style={styles.modelRow}>
              <View style={styles.modelInfo}>
                <Text style={styles.modelName}>{model.model_name}</Text>
                <View style={styles.badgeContainer}>
                  <Text style={[styles.modelStatus, {
                    color: model.label === 'Error' ? '#ff4444' :
                      model.label === 'Fake' ? '#ff4444' :
                        model.label === 'Real' ? '#00c851' : '#aaa'
                  }]}>
                    {model.label}
                  </Text>
                </View>
              </View>

              {model.error ? (
                <Text style={styles.modelError}>{model.error}</Text>
              ) : (
                <View style={styles.scoreContainer}>
                  <View style={styles.progressBarBg}>
                    <View
                      style={[
                        styles.progressBarFill,
                        {
                          width: `${Math.min(model.score, 100)}%`,
                          backgroundColor: getScoreColor(model.score)
                        }
                      ]}
                    />
                  </View>
                  <Text style={styles.scoreText}>{Math.round(model.score)}%</Text>
                </View>
              )}
              {model.details && <Text style={styles.modelDetails}>{model.details}</Text>}
            </View>
          ))}

          {results.metrics && (
            <View style={styles.metricsContainer}>
              <Text style={styles.metricText}>Models: {results.metrics.successful_models}/{results.metrics.total_models}</Text>
              <Text style={styles.metricText}>Latency: {results.metrics.average_latency_ms}ms</Text>
            </View>
          )}

          <Text style={styles.summaryText}>{results.summary}</Text>
        </View>

        <TouchableOpacity
          style={styles.resetButton}
          onPress={() => {
            setResults(null);
            setSelectedImage(null);
            setStep('idle');
          }}
        >
          <Text style={styles.resetButtonText}>Scan Another Image</Text>
        </TouchableOpacity>
      </Animated.View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" />
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Render Results Component */}
        {renderResults()}

        {/* Header */}
        {!results && (
          <View style={styles.header}>
            <View style={styles.statusBadge}>
              <View style={styles.statusDot} />
              <Text style={styles.statusText}>SYSTEM ONLINE</Text>
            </View>
            <Text style={styles.headerTitle}>CATCHY<Text style={{ color: '#4facfe' }}> AI</Text></Text>
          </View>
        )}

        {/* Main Interface */}
        {!results && (
          <View style={styles.card}>
            {selectedImage ? (
              <View style={styles.previewContainer}>
                <Image source={{ uri: selectedImage.uri }} style={styles.previewImage} />
                {loading && <ScanLine />}
                {!loading && (
                  <TouchableOpacity
                    style={styles.closeBtn}
                    onPress={() => {
                      setSelectedImage(null);
                      setResults(null);
                      setStep('idle');
                    }}
                  >
                    <Ionicons name="close" size={20} color="#fff" />
                  </TouchableOpacity>
                )}
              </View>
            ) : (
              <TouchableOpacity
                style={styles.uploadZone}
                onPress={pickImage}
                activeOpacity={0.8}
              >
                <LinearGradient
                  colors={['rgba(79, 172, 254, 0.1)', 'rgba(0, 242, 254, 0.05)']}
                  style={styles.uploadGradient}
                >
                  <Ionicons name="aperture" size={64} color="#4facfe" />
                  <Text style={styles.uploadTitle}>TAP TO SCAN</Text>
                  <Text style={styles.uploadSubtitle}>Upload image for verification</Text>
                </LinearGradient>
              </TouchableOpacity>
            )}

            {/* Controls */}
            <View style={styles.controls}>
              {loading ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator color="#4facfe" size="large" />
                  <Text style={styles.loadingText}>
                    {step === 'uploading' ? `Uploading... ${uploadProgress}%` : 'Analyzing patterns...'}
                  </Text>
                  <Text style={styles.loadingSubText}>Running multi-model ensemble</Text>
                </View>
              ) : (
                <TouchableOpacity
                  style={[styles.verifyBtn, !selectedImage && styles.disabledBtn]}
                  onPress={handleVerify}
                  disabled={!selectedImage}
                >
                  <LinearGradient
                    colors={selectedImage ? ['#4facfe', '#00f2fe'] : ['#333', '#333']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.btnGradient}
                  >
                    <Text style={styles.btnText}>INITIATE SCAN</Text>
                    <Ionicons name="arrow-forward" size={20} color={selectedImage ? "#000" : "#666"} />
                  </LinearGradient>
                </TouchableOpacity>
              )}
            </View>
          </View>
        )}

        <ErrorBanner error={error} onDismiss={() => setError({ ...error, visible: false })} />
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#050505',
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 100,
  },
  header: {
    marginBottom: 30,
    alignItems: 'center',
    marginTop: 20,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 200, 81, 0.1)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: 'rgba(0, 200, 81, 0.2)',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#00c851',
    marginRight: 8,
  },
  statusText: {
    color: '#00c851',
    fontSize: 10,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  headerTitle: {
    color: '#fff',
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: 2,
  },
  card: {
    backgroundColor: '#121212',
    borderRadius: 24,
    padding: 6,
    borderWidth: 1,
    borderColor: '#2a2a2a',
    marginBottom: 24,
  },
  uploadZone: {
    height: 320,
    borderRadius: 20,
    overflow: 'hidden',
  },
  uploadGradient: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(79, 172, 254, 0.3)',
    borderStyle: 'dashed',
    borderRadius: 20,
  },
  uploadTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
    marginTop: 20,
    letterSpacing: 2,
  },
  uploadSubtitle: {
    color: '#666',
    marginTop: 8,
    fontSize: 14,
  },
  previewContainer: {
    height: 320,
    borderRadius: 20,
    overflow: 'hidden',
    position: 'relative',
    backgroundColor: '#000',
  },
  previewImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'contain',
  },
  closeBtn: {
    position: 'absolute',
    top: 10,
    right: 10,
    backgroundColor: 'rgba(0,0,0,0.6)',
    padding: 8,
    borderRadius: 20,
  },
  scanLine: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 2,
    zIndex: 10,
  },
  scanGradient: {
    flex: 1,
    height: 2,
    shadowColor: "#4facfe",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 10,
  },
  controls: {
    padding: 14,
  },
  verifyBtn: {
    height: 56,
    borderRadius: 16,
    overflow: 'hidden',
  },
  disabledBtn: {
    opacity: 0.5,
  },
  btnGradient: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  btnText: {
    color: '#000',
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  loadingContainer: {
    alignItems: 'center',
    padding: 10,
  },
  loadingText: {
    color: '#4facfe',
    marginTop: 12,
    fontSize: 14,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  loadingSubText: {
    color: '#666',
    marginTop: 4,
    fontSize: 12,
  },
  // Results Styles
  resultContainer: {
    backgroundColor: '#121212',
    borderRadius: 24,
    padding: 24,
    borderWidth: 1,
    marginBottom: 30,
    marginTop: 10,
  },
  verdictCard: {
    alignItems: 'center',
    padding: 24,
    borderWidth: 2,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.03)',
    marginBottom: 24,
  },
  verdictTitle: {
    fontSize: 22,
    fontWeight: '900',
    marginTop: 16,
    letterSpacing: 1,
    textAlign: 'center',
  },
  verdictScore: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
    marginTop: 8,
  },
  verdictConfidence: {
    color: '#888',
    fontSize: 14,
    marginTop: 4,
  },
  detailsContainer: {
    paddingTop: 10,
  },
  subHeader: {
    color: '#666',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 15,
    letterSpacing: 1,
  },
  modelRow: {
    marginBottom: 16,
    backgroundColor: 'rgba(255,255,255,0.02)',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  modelInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  modelName: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  badgeContainer: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  modelStatus: {
    fontSize: 12,
    fontWeight: 'bold',
  },
  modelError: {
    color: '#ff4444',
    fontSize: 12,
    marginTop: 4,
    fontStyle: 'italic',
  },
  modelDetails: {
    color: '#888',
    fontSize: 12,
    marginTop: 8,
    lineHeight: 18,
  },
  scoreContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  progressBarBg: {
    flex: 1,
    height: 8,
    backgroundColor: '#333',
    borderRadius: 4,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    borderRadius: 4,
  },
  scoreText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: 'bold',
    width: 40,
    textAlign: 'right',
  },
  metricsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#333',
  },
  metricText: {
    color: '#666',
    fontSize: 12,
  },
  summaryText: {
    color: '#aaa',
    fontSize: 14,
    marginTop: 20,
    lineHeight: 22,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  resetButton: {
    marginTop: 24,
    backgroundColor: '#222',
    padding: 18,
    borderRadius: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#333',
  },
  resetButtonText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
  },
  // Error Banner Styles
  errorBanner: {
    position: 'absolute',
    bottom: 20,
    left: 20,
    right: 20,
    backgroundColor: '#1e1e1e',
    borderRadius: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#ff4444',
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
    zIndex: 100,
  },
  errorContent: {
    flexDirection: 'row',
    padding: 16,
    alignItems: 'flex-start',
  },
  errorIcon: {
    marginRight: 12,
    marginTop: 2,
  },
  errorTextContainer: {
    flex: 1,
  },
  errorTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  errorMessage: {
    color: '#aaa',
    fontSize: 14,
    lineHeight: 20,
  },
  errorCode: {
    color: '#666',
    fontSize: 10,
    marginTop: 6,
  },
  errorClose: {
    padding: 4,
  },
});

export default HomeScreen;