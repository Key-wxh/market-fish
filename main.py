"""
MarketFish — Multi-Agent Market Simulation Engine
FastAPI entry point + 5-stage pipeline API.
"""

import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from engine.pipeline import Pipeline

app = FastAPI(title="MarketFish", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "MarketFish"}


@app.post("/api/pipeline/run")
def run_pipeline():
    """Run the full 5-stage MarketFish pipeline."""
    # Load seed data
    seed = {}
    seed_files = {
        "freelancer": "data/seed_freelancer.json",
        "economy": "data/seed_economy.json",
        "tech": "data/seed_tech.json",
        "consumer": "data/seed_consumer.json",
        "b2b": "data/seed_b2b.json",
    }
    for key, path in seed_files.items():
        try:
            with open(path) as f:
                seed[key] = json.load(f)
        except FileNotFoundError:
            raise HTTPException(500, f"Seed data missing: {path}")

    pipeline = Pipeline()
    result = pipeline.run(seed)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
