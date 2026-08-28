from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from services.llm import get_provider

router = APIRouter()


class ChatRequest(BaseModel):
    """Request payload for chat endpoint."""
    message: str
    context: Optional[Dict[str, Any]] = None


def generate_demo_response(request: ChatRequest) -> str:
    """
    Generate intelligent demo responses for testing when API is unavailable.
    Uses context awareness to provide relevant answers.
    """
    message = request.message.lower()
    context = request.context or {}
    smiles = context.get('smiles', 'unknown molecule')
    results = context.get('results', {})
    
    # Demo responses based on keywords
    if 'toxicity' in message or 'toxic' in message:
        tox = results.get('toxicity', 0.093)
        return f"[DEMO MODE] The toxicity score of {smiles} is {tox}. A score below 0.5 generally indicates low toxicity. This SMILES structure has {'favorable' if tox < 0.3 else 'moderate'} toxicity properties for drug development."
    
    if 'solubility' in message or 'dissolve' in message or 'water' in message:
        sol = results.get('solubility', -1.5)
        return f"[DEMO MODE] The aqueous solubility (logS) of {smiles} is {sol}. Values between -6 and 0.5 are typical for drugs. This molecule shows {'good' if sol > -3 else 'moderate'} water solubility."
    
    if 'binding' in message or 'affinity' in message or 'target' in message:
        binding = results.get('binding_score', 7.2)
        return f"[DEMO MODE] Drug-target binding score for {smiles}: {binding} (scale 5-9.5). This indicates {'strong' if binding > 8 else 'moderate'} binding affinity. Higher scores suggest better binding interactions."
    
    if 'bbbp' in message or 'brain' in message or 'barrier' in message:
        bbbp = results.get('bbbp', 0)
        return f"[DEMO MODE] Blood-brain barrier permeability for {smiles}: {'Permeable' if bbbp == 1 else 'Not permeable'}. CNS drugs typically need BBB penetration, while peripheral drugs should be blocked."
    
    if 'how do i' in message or 'improve' in message or 'optimize' in message:
        return f"[DEMO MODE] To optimize {smiles}: Consider reducing hydrophobic regions (LogP), maintaining TPSA 20-130Ų for membrane permeability, and avoiding excessive H-bond donors. Consult medicinal chemistry principles for structural modifications."
    
    if 'what' in message or 'tell me' in message or 'explain' in message:
        return f"[DEMO MODE] Analyzing {smiles}: This molecule shows mixed ADMET properties. Review individual predictions (solubility, toxicity, binding) to understand drug-like characteristics. Optimize problem areas while maintaining potency."
    
    # Default response
    return f"[DEMO MODE] Analyzing {smiles} for your question: '{request.message}'. The AI is currently in demo mode due to API quota limits. For full responses, please add billing to your Gemini API account at https://ai.google.dev/pricing"


@router.post("/ask")
async def ask_gemini(request: ChatRequest):
    """
    Secure endpoint that intercepts user message, injects invisible context,
    and forwards to Gemini 1.5 Pro for analysis.
    
    The API key never reaches the frontend — only this backend endpoint knows it.
    """
    llm = get_provider()
    if not llm:
        raise HTTPException(
            status_code=503,
            detail="AI engine not configured. Set GEMINI_API_KEY in backend .env"
        )

    try:
        # 1. Build the System Prompt
        system_prompt = """You are the DrugForge AI, an expert cheminformatics and drug discovery assistant.
Your goal is to help researchers analyze molecules, interpret ADMET predictions, and suggest structural optimizations.

Guidelines:
- Be concise, highly scientific, and professional
- Cite specific prediction scores when analyzing results
- Suggest structural modifications with chemical reasoning
- Explain why certain functional groups affect predicted properties
- Use accurate IUPAC nomenclature when discussing chemistry

Current role: Help the researcher understand their molecular analysis."""

        # 2. Inject the "Invisible Context" — the user has no idea how much the AI knows
        if request.context:
            context_str = "\n".join([f"• {k}: {v}" for k, v in request.context.items()])
            system_prompt += f"\n\n--- SCREEN CONTEXT (Researcher is currently analyzing this) ---\n{context_str}\n---"
        
        # 3. Build the full prompt
        full_prompt = f"{system_prompt}\n\nResearcher Question: {request.message}\n\nAnswer:"
        
        # 4. Generate Response via the configured LLM provider
        reply = llm.generate(full_prompt)

        return {"reply": reply}

    except Exception as e:
        import traceback
        error_str = str(e)
        
        # Check for quota exceeded (429) errors - use demo mode instead of erroring
        if "quota" in error_str.lower() or "429" in error_str:
            demo_response = generate_demo_response(request)
            return {"reply": demo_response}
        
        # Check for auth errors
        if "api key" in error_str.lower() or "unauthorized" in error_str.lower():
            raise HTTPException(
                status_code=503,
                detail="Invalid or missing GEMINI_API_KEY in backend environment"
            )
        
        print(f"[ChatRouter] Gemini Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate response: {error_str[:200]}"
        )
