# DrugForge Backend API

## 🚀 Flask API Server for ML Predictions

This directory contains the backend API server that powers DrugForge's machine learning predictions.

### 📂 Structure

```
backendML/
├── app.py                           # Main Flask application
├── requirements.txt                 # Python dependencies
├── ADMET Properties/               # ADMET prediction models
├── Drug Target Binding Score/      # Binding affinity models
├── Molecular Docking/              # Docking simulation tools
└── Target Identification/          # Target prediction models
```

### 🔗 API Endpoints

- **Health Check**: `GET /health`
- **Predictions**: `POST /predict/{tool_name}`

See main README.md for complete API documentation.

### 🚀 Quick Start

```bash
# Setup environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies  
pip install -r requirements.txt

# Start server
python app.py
```

### 📦 Dependencies

- **Flask**: Web framework
- **Flask-CORS**: Cross-origin resource sharing
- **RDKit**: Chemical informatics (for SMILES validation)
- **Scikit-learn**: Machine learning models
- **NumPy/Pandas**: Data processing

For detailed setup instructions, see the main [README.md](../README.md) in the project root.
