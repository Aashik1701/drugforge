from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import pickle
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
import os
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=['http://localhost:3000', 'http://127.0.0.1:3000'])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Model storage
models = {}

# Error handling decorator
def handle_api_errors(f):
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.error(f"Validation error in {f.__name__}: {str(e)}")
            return jsonify({'error': str(e), 'type': 'validation_error'}), 400
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}")
            return jsonify({'error': 'Internal server error', 'type': 'server_error'}), 500
    wrapper.__name__ = f.__name__
    return wrapper

def load_models():
    """Load all ML models on startup"""
    try:
        # Load BBBP model
        bbbp_model_path = os.path.join('ADMET Properties', 'models', 'bbbp_model.pkl')
        if os.path.exists(bbbp_model_path):
            with open(bbbp_model_path, 'rb') as f:
                models['bbbp'] = pickle.load(f)
                logger.info("BBBP model loaded successfully")
        
        # Load other models similarly
        model_paths = {
            'cyp3a4': os.path.join('ADMET Properties', 'models', 'cyp3a4_model.pkl'),
            'solubility': os.path.join('ADMET Properties', 'models', 'solubility_model.pkl'),
            'toxicity': os.path.join('ADMET Properties', 'models', 'toxicity_model.pkl'),
            'binding_score': os.path.join('Drug Target Binding Score', 'binding_model.pkl'),
        }
        
        for model_name, model_path in model_paths.items():
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    models[model_name] = pickle.load(f)
                    logger.info(f"{model_name} model loaded successfully")
            else:
                logger.warning(f"Model file not found: {model_path}")
                
    except Exception as e:
        logger.error(f"Error loading models: {str(e)}")

def smiles_to_features(smiles):
    """Convert SMILES string to molecular features"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid SMILES string")
        
        # Calculate molecular descriptors
        features = {
            'MolWt': Descriptors.MolWt(mol),
            'MolLogP': Descriptors.MolLogP(mol),
            'NumHDonors': Descriptors.NumHDonors(mol),
            'NumHAcceptors': Descriptors.NumHAcceptors(mol),
            'TPSA': Descriptors.TPSA(mol),
            'NumRotatableBonds': Descriptors.NumRotatableBonds(mol),
            'NumAromaticRings': Descriptors.NumAromaticRings(mol),
            'NumSaturatedRings': Descriptors.NumSaturatedRings(mol),
            'RingCount': Descriptors.RingCount(mol),
            'FractionCsp3': Descriptors.FractionCsp3(mol),
        }
        
        return np.array(list(features.values())).reshape(1, -1)
    except Exception as e:
        raise ValueError(f"Error processing SMILES: {str(e)}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'models_loaded': len(models),
        'available_models': list(models.keys())
    })

@app.route('/predict/bbbp', methods=['POST'])
def predict_bbbp():
    """Blood-Brain Barrier Penetration prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        if 'bbbp' not in models:
            # Return mock prediction for testing
            return jsonify({
                'Predicted Class': 1,
                'Predicted Probability for Class 1': 0.75,
                'smiles': smiles,
                'model': 'mock'
            })
        
        # Extract features and predict
        features = smiles_to_features(smiles)
        prediction = models['bbbp'].predict(features)[0]
        probability = models['bbbp'].predict_proba(features)[0][1]
        
        return jsonify({
            'Predicted Class': int(prediction),
            'Predicted Probability for Class 1': float(probability),
            'smiles': smiles
        })
        
    except Exception as e:
        logger.error(f"Error in BBBP prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/cyp3a4', methods=['POST'])
def predict_cyp3a4():
    """CYP3A4 interaction prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Class': 0,
            'Predicted Probability for Class 1': 0.35,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in CYP3A4 prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/solubility', methods=['POST'])
def predict_solubility():
    """Solubility prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Solubility': -2.45,
            'Unit': 'log(mol/L)',
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in solubility prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/half-life', methods=['POST'])
def predict_half_life():
    """Half-life prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Half-Life': 8.5,
            'Unit': 'hours',
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in half-life prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/cox2', methods=['POST'])
def predict_cox2():
    """COX2 inhibition prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Class': 1,
            'Predicted Probability for Class 1': 0.82,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in COX2 prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/hepg2', methods=['POST'])
def predict_hepg2():
    """HEPG2 toxicity prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Class': 0,
            'Predicted Probability for Class 1': 0.25,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in HEPG2 prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/ace2', methods=['POST'])
def predict_ace2():
    """ACE2 binding prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Class': 1,
            'Predicted Probability for Class 1': 0.65,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in ACE2 prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/toxicity', methods=['POST'])
def predict_toxicity():
    """General toxicity prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Predicted Class': 0,
            'Predicted Probability for Class 1': 0.30,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in toxicity prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict/binding-score', methods=['POST'])
def predict_binding_score():
    """Drug-target binding score prediction"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        target_id = data.get('target_id', 'default')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Mock prediction for testing
        return jsonify({
            'Binding Score': -8.5,
            'Unit': 'kcal/mol',
            'Target': target_id,
            'smiles': smiles,
            'model': 'mock'
        })
        
    except Exception as e:
        logger.error(f"Error in binding score prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/predict', methods=['POST'])
def predict_generic():
    """Generic prediction endpoint (fallback)"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '')
        
        if not smiles:
            return jsonify({'error': 'SMILES string is required'}), 400
        
        # Default to BBBP prediction
        return predict_bbbp()
        
    except Exception as e:
        logger.error(f"Error in generic prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    load_models()
    app.run(host='0.0.0.0', port=5001, debug=True)
