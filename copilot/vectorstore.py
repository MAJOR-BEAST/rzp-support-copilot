"""VectorStore interface: PineconeStore (integrated multilingual-e5-large) and LocalStore (TF-IDF fallback).

Query results are cached under cache/retrieval/ so re-runs are reproducible and offline.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
RCACHE = ROOT / "cache" / "retrieval"
RCACHE.mkdir(parents=True, exist_ok=True)
INDEX_NAME = "rzp-kb"


class VectorStore:
    backend = "base"

    def _search(self, text: str, k: int, namespace: str) -> list:
        raise NotImplementedError

    def query(self, text: str, k: int = 3, namespace: str = "kb") -> list:
        """Return [(id, score)] best-first. Cached per backend+namespace+text."""
        key = hashlib.sha256(json.dumps([self.backend, namespace, k, text]).encode()).hexdigest()
        p = RCACHE / f"{key}.json"
        if p.exists():
            return [tuple(x) for x in json.loads(p.read_text())]
        res = self._search(text, k, namespace)
        p.write_text(json.dumps(res))
        return res


class LocalStore(VectorStore):
    backend = "local"

    def __init__(self, kb: dict, tickets=None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.docs = {"kb": [(k, f"{v['topic']}. {v['guidance']}") for k, v in kb.items()]}
        if tickets is not None:
            self.docs["tickets"] = [(r.ticket_id, r.merchant_message) for r in tickets.itertuples()]
        self.vec, self.mat = {}, {}
        for ns, docs in self.docs.items():
            v = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
            self.mat[ns] = v.fit_transform([d for _, d in docs])
            self.vec[ns] = v

    def _search(self, text, k, namespace):
        from sklearn.metrics.pairwise import cosine_similarity
        sims = cosine_similarity(self.vec[namespace].transform([text]), self.mat[namespace])[0]
        order = sims.argsort()[::-1][:k]
        return [(self.docs[namespace][i][0], round(float(sims[i]), 4)) for i in order]


class PineconeStore(VectorStore):
    backend = "pinecone"

    def __init__(self, kb: dict, tickets=None):
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        if not pc.has_index(INDEX_NAME):
            pc.create_index_for_model(
                name=INDEX_NAME, cloud="aws", region="us-east-1",
                embed={"model": "multilingual-e5-large", "field_map": {"text": "chunk_text"}},
            )
            for _ in range(60):
                if pc.describe_index(INDEX_NAME).status.ready:
                    break
                time.sleep(2)
        self.index = pc.Index(INDEX_NAME)
        stats = self.index.describe_index_stats()
        ns = getattr(stats, "namespaces", {}) or {}

        def count(name):
            n = ns.get(name)
            return getattr(n, "vector_count", 0) if n else 0

        if count("kb") < len(kb):
            recs = [{"_id": k, "chunk_text": f"{v['topic']}. {v['guidance']}", "topic": v["topic"]} for k, v in kb.items()]
            self.index.upsert_records(namespace="kb", records=recs)
        if tickets is not None and count("tickets") < len(tickets):
            recs = [{"_id": r.ticket_id, "chunk_text": r.merchant_message, "merchant_id": str(r.merchant_id or ""),
                     "created_at": str(r.created_at)} for r in tickets.itertuples()]
            for i in range(0, len(recs), 90):
                self.index.upsert_records(namespace="tickets", records=recs[i:i + 90])
        # wait for eventual consistency on the kb namespace
        for _ in range(30):
            if self._raw("settlement", 1, "kb"):
                break
            time.sleep(2)

    def _raw(self, text, k, namespace):
        resp = self.index.search(namespace=namespace, query={"inputs": {"text": text}, "top_k": k})
        hits = resp.result.hits
        return [(h.id, round(float(h.score), 4)) for h in hits]

    def _search(self, text, k, namespace):
        return self._raw(text, k, namespace)


def get_store(kb: dict, tickets=None) -> VectorStore:
    backend = os.getenv("VECTOR_BACKEND", "pinecone").lower()
    if backend == "pinecone":
        try:
            s = PineconeStore(kb, tickets)
            print("[vectorstore] Pinecone index rzp-kb ready")
            return s
        except Exception as e:  # never block on Pinecone
            print(f"[vectorstore] Pinecone failed ({type(e).__name__}: {str(e)[:150]}); falling back to LocalStore")
    return LocalStore(kb, tickets)
