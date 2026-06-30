"""
Paper Ingest — learning mechanism for new research/knowledge.
Ingests papers (text/URL), extracts structured insights, suggests config changes.
All suggestions require human review before application.
"""

import json, os, re, time
from pathlib import Path
from engine.llm_client import get_llm


EXTRACT_PROMPT = """You are a research paper analyst. Extract structured insights from this paper.

Output EXACTLY this JSON:
{
  "paper_metadata": {
    "title": "extracted title",
    "authors": "extracted or unknown",
    "venue": "extracted or unknown",
    "year": "extracted or 2026",
    "arxiv_id": "if present"
  },
  "key_findings": [
    {"finding": "statement", "strength": 0.0-1.0, "category": "methodology|empirical|theoretical|benchmark"}
  ],
  "new_concepts": [
    {"name": "concept", "definition": "1-2 sentences", "marketfish_relevance": "how it applies to MarketFish"}
  ],
  "config_implications": {
    "new_parameters": [
      {"name": "param", "type": "float|int|str", "range": "suggested range", "default": "value", "reason": "why"}
    ],
    "modify_existing": [
      {"param_path": "SIMULATION.rounds", "current": "?", "suggested": "value", "reason": "why"}
    ]
  },
  "pipeline_implications": {
    "new_stage": "suggested new pipeline stage or null",
    "modify_stage": "which existing stage to modify or null",
    "rationale": "why this paper changes the pipeline"
  }
}"""


class LearningSystem:
    """Manages paper ingestion → knowledge update lifecycle."""

    def __init__(self, storage_dir: str = "data/ingested_papers"):
        self.storage_dir = Path(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)

    def ingest(self, content: str, source: str = "text") -> dict:
        """Ingest a paper and extract structured insights."""
        llm = get_llm()
        truncated = content[:12000] if len(content) > 12000 else content

        try:
            extraction = llm.chat_json(
                system=EXTRACT_PROMPT,
                user=f"Source: {source}\n\nPAPER CONTENT:\n{truncated}",
                agent_type="ontology",
            )
        except Exception as e:
            return {"error": str(e), "source": source}

        # Save
        title = extraction.get("paper_metadata", {}).get("title", "untitled")
        slug = re.sub(r'[^a-z0-9]+', '-', title[:50].lower().strip('-'))
        path = self.storage_dir / f"{time.strftime('%Y%m%d')}-{slug}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(extraction, f, indent=2, ensure_ascii=False)
        extraction["saved_to"] = str(path)
        return extraction

    def ingest_from_url(self, url: str) -> dict:
        """Fetch paper from URL and ingest."""
        try:
            import httpx
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            return self.ingest(resp.text, source=url)
        except Exception as e:
            return {"error": str(e), "url": url}

    def get_all(self) -> list:
        """Load all ingested papers."""
        papers = []
        if not self.storage_dir.exists():
            return papers
        for f in sorted(self.storage_dir.glob("*.json")):
            with open(f, encoding='utf-8') as fp:
                papers.append(json.load(fp))
        return papers

    def get_suggestions(self) -> list:
        """Get all pending config change suggestions across all papers."""
        suggestions = []
        for paper in self.get_all():
            implications = paper.get("config_implications", {})
            for param in implications.get("new_parameters", []):
                suggestions.append({
                    "action": "ADD", "paper": paper.get("paper_metadata", {}).get("title", "?"),
                    "param": param["name"], "default": param.get("default"),
                    "reason": param.get("reason", ""), "status": "pending_review",
                })
            for mod in implications.get("modify_existing", []):
                suggestions.append({
                    "action": "MODIFY", "paper": paper.get("paper_metadata", {}).get("title", "?"),
                    "path": mod.get("param_path"), "suggested": mod.get("suggested"),
                    "reason": mod.get("reason", ""), "status": "pending_review",
                })
        return suggestions

    def get_pipeline_implications(self) -> list:
        """Get pipeline change suggestions across all papers."""
        implications = []
        for paper in self.get_all():
            pi = paper.get("pipeline_implications", {})
            if pi.get("new_stage") or pi.get("modify_stage"):
                implications.append({
                    "paper": paper.get("paper_metadata", {}).get("title", "?"),
                    "new_stage": pi.get("new_stage"),
                    "modify_stage": pi.get("modify_stage"),
                    "rationale": pi.get("rationale", ""),
                    "status": "pending_review",
                })
        return implications
