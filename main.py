"""
MarketFish — Multi-Agent Market Simulation Engine
FastAPI entry point + 5-stage pipeline API.
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from engine.pipeline import Pipeline

app = FastAPI(title="MarketFish", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class UserProduct(BaseModel):
    name: str
    description: str
    target_market: str = "consumer"
    pricing: str = ""
    pain_point: Optional[str] = None
    differentiation: Optional[str] = None


class PipelineRequest(BaseModel):
    mode: str = "explore"  # explore | validate | hybrid
    user_product: Optional[UserProduct] = None
    seed_data: Optional[Dict] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "MarketFish", "version": "2.0"}


@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRequest = PipelineRequest()):
    """Run the MarketFish pipeline in explore/validate/hybrid mode."""
    pipeline = Pipeline()
    user_product_dict = req.user_product.model_dump() if req.user_product else None

    # Seed data: pass through to pipeline (pipeline._load_seed_data handles defaults)
    result = pipeline.run(seed_data=req.seed_data, mode=req.mode, user_product=user_product_dict)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
