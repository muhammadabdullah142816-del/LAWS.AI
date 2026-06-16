import os
import re
import json
import hashlib
import logging
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pinecone import Pinecone, ServerlessSpec
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION & ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────────────────────────────
# NOTE: Environment reads are deferred to _ensure_connections() so that
# load_dotenv() in run_spider.py has already executed by the time we
# read them. Module-level os.getenv() runs at import time, which is
# BEFORE dotenv loads the .env file.

MIN_TOKENS_PER_CHUNK = 500
MAX_TOKENS_PER_CHUNK = 1000
CHARS_PER_TOKEN = 4

EMBEDDING_DIMENSION = 384


class LegalCloudRoutingPipeline:
    def __init__(self):
        self.db_conn = None
        self.db_cursor = None
        self.pc = None
        self.pinecone_index = None
        self.hf_api_key = None
        self.is_connected = False  # Operational lock variable
        self.cloud_disabled = False
        self.batch_buffer = []
        self.BATCH_SIZE = 50  # Default value, dynamically updated in _ensure_connections

    def open_spider(self, spider):
        """
        Loads the high-speed local SentenceTransformer model.
        """
        spider.logger.info("⏳ Loading featherweight local embedding model (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', local_files_only=True)
        spider.logger.info("✅ Local model loaded successfully.")

    def _ensure_connections(self, spider):
        """
        Guarantees cloud connections are safely instantiated exactly once
        without choking Scrapy's async initialization hooks.
        """
        if self.is_connected:
            return

        spider.logger.info("⚡ Activating Production Cloud Routing Engine Clients...")

        # Read environment variables NOW (after load_dotenv has run)
        supabase_db_url = os.getenv("SUPABASE_DB_URL", "")
        pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
        pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "legal-frameworks-index")
        self.hf_api_key = os.getenv("HF_API_KEY", "")

        try:
            self.BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_LIMIT", 50))
        except ValueError:
            spider.logger.warning("⚠️ Invalid PIPELINE_BATCH_LIMIT detected in environment. Falling back to 50.")
            self.BATCH_SIZE = 50

        # 1. Connect to Supabase Safely
        try:
            connection_string = supabase_db_url.strip('"\'') if supabase_db_url else None
            self.db_conn = psycopg2.connect(connection_string)
            self.db_conn.autocommit = True
            self.db_cursor = self.db_conn.cursor()
            register_vector(self.db_conn)
            spider.logger.info("✅ Direct Connection Established with Supabase.")
        except Exception as e:
            spider.logger.error(f"💥 CLOUD INITIALIZATION FAILURE: Supabase error: {e}. Activating Local Fallback Engine.")
            self.cloud_disabled = True
            return

        # 2. Connect to Pinecone Safely
        try:
            self.pc = Pinecone(api_key=pinecone_api_key)
            existing_indexes = [index_info["name"] for index_info in self.pc.list_indexes()]
            if pinecone_index_name not in existing_indexes:
                spider.logger.info(f"Creating {EMBEDDING_DIMENSION}-d Pinecone index: {pinecone_index_name}")
                self.pc.create_index(
                    name=pinecone_index_name,
                    dimension=EMBEDDING_DIMENSION,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
            self.pinecone_index = self.pc.Index(pinecone_index_name)
            spider.logger.info("✅ Connection Established with Pinecone.")
        except Exception as e:
            spider.logger.warning(f"⚠️ Pinecone network error (caught and ignored): {e}")

        self.is_connected = True
        spider.logger.info("✅ Core Connections Successfully Synchronized.")

    def close_spider(self, spider):
        try:
            if not self.cloud_disabled and self.batch_buffer:
                self._flush_buffer(spider)

            if self.db_cursor:
                self.db_cursor.close()
            if self.db_conn:
                self.db_conn.close()
            spider.logger.info("Cloud sessions closed cleanly.")
        except Exception as e:
            spider.logger.warning(f"⚠️ Safe warning during engine cleanup: {e}")

    def _fetch_embeddings_batch(self, chunks: list[str], spider) -> list[list[float]]:
        """
        Computes 384-dimensional embeddings locally on the CPU 
        using sentence-transformers/all-MiniLM-L6-v2.
        """
        spider.logger.info(f"⚡ Computing local embeddings for {len(chunks)} text chunks...")
        embeddings = self.model.encode(chunks, convert_to_numpy=True).tolist()
        spider.logger.info(
            f"✅ Local Inference Success: Generated {len(embeddings)} "
            f"dense vector representations ({EMBEDDING_DIMENSION}-d)."
        )
        return embeddings

    def process_item(self, item, spider):
        jurisdiction = item.get("jurisdiction", "Unknown")
        sub_jurisdiction = item.get("sub_jurisdiction", "")
        document_type = item.get("document_type", "")
        article_section = item.get("article_section", "")
        source_url = item.get("source_url", "")
        raw_text = item.get("raw_text", "")

        if not raw_text:
            return item

        # Initialize connection engines on the first passing item payload
        self._ensure_connections(spider)

        if self.cloud_disabled:
            self._write_local_fallback(item, spider)
            return item

        soup = BeautifulSoup(raw_text, "html.parser")
        clean_text = soup.get_text(separator="\n\n", strip=True)
        document_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

        try:
            self.db_cursor.execute("SELECT source_hash FROM legal_frameworks WHERE source_url = %s LIMIT 1", (source_url,))
            result = self.db_cursor.fetchone()
            if result and result[0] == document_hash:
                spider.logger.info(f"⏩ STORAGE MATCH: {source_url} is up to date. Skipping parsing.")
                return item
            elif result:
                spider.logger.warning("⚠️ REGULATORY DRIFT DETECTED: Clearing outdated rows.")
                self.db_cursor.execute("DELETE FROM legal_frameworks WHERE source_url = %s", (source_url,))
                self.db_conn.commit()
                self.pinecone_index.delete(filter={"source_url": source_url})
        except Exception as e:
            spider.logger.error(f"Storage evaluation failed: {e}")

        chunks = self._chunk_text(clean_text)
        date_scraped = datetime.now(timezone.utc).isoformat()

        # Batch Fetch Live AI Embeddings via dedicated method
        try:
            all_embeddings = self._fetch_embeddings_batch(chunks, spider)
        except Exception as e:
            spider.logger.error(f"💥 Live AI Embedding fault detected: {e}. Activating Local Fallback Engine.")
            self.cloud_disabled = True
            self._write_local_fallback(item, spider)
            return item

        for i, chunk in enumerate(chunks):
            chunk_id = f"{hashlib.md5(source_url.encode()).hexdigest()}_chunk_{i}"
            vector = all_embeddings[i]

            if i == 0:
                magnitude_sq = sum(v * v for v in vector)
                spider.logger.info(f"🧪 DIAGNOSTIC L2 NORM CHECK: sum(v*v) = {magnitude_sq:.6f}")

            self.batch_buffer.append({
                "id": chunk_id,
                "jurisdiction": jurisdiction,
                "sub_jurisdiction": sub_jurisdiction,
                "document_type": document_type,
                "article_section": article_section,
                "source_url": source_url,
                "chunk_text": chunk,
                "source_hash": document_hash,
                "date_scraped": date_scraped,
                "vector": vector,
                "chunk_index": i
            })

            if len(self.batch_buffer) >= self.BATCH_SIZE:
                self._flush_buffer(spider)

        return item

    def _chunk_text(self, text: str) -> list[str]:
        text = text.replace("\xa0", " ").replace("\u200b", "")
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        min_chars = MIN_TOKENS_PER_CHUNK * CHARS_PER_TOKEN
        max_chars = MAX_TOKENS_PER_CHUNK * CHARS_PER_TOKEN

        paragraphs = text.split("\n\n")
        chunks = []
        buffer = []
        buffer_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) > max_chars:
                if buffer:
                    chunks.append("\n\n".join(buffer))
                    buffer, buffer_len = [], 0

                sentences = re.split(r"(?<=[.!?])\s+", para)
                sent_buf = []
                sent_len = 0
                for sent in sentences:
                    if sent_len + len(sent) > max_chars and sent_buf:
                        chunks.append(" ".join(sent_buf))
                        sent_buf, sent_len = [], 0
                    sent_buf.append(sent)
                    sent_len += len(sent) + 1
                if sent_buf:
                    chunks.append(" ".join(sent_buf))
                continue

            buffer.append(para)
            buffer_len += len(para) + 2

            if buffer_len >= min_chars:
                chunks.append("\n\n".join(buffer))
                buffer, buffer_len = [], 0

        if buffer:
            chunks.append("\n\n".join(buffer))

        return chunks

    def _flush_buffer(self, spider):
        if not self.batch_buffer:
            return

        spider.logger.info(f"Pipeline Synchronizing: Flushing {len(self.batch_buffer)} elements to Cloud Ecosystem.")

        # 1. Supabase Postgres Bulk Insert — try full schema, fall back to legacy
        # ── Attempt A: full schema with sub_jurisdiction ──────────────────────
        insert_full = """
            INSERT INTO legal_frameworks
                (jurisdiction, sub_jurisdiction, document_type, article_section,
                 source_url, chunk_text, source_hash, date_scraped, embedding)
            VALUES %s
        """
        values_full = [(
            b["jurisdiction"],
            b["sub_jurisdiction"],
            b["document_type"],
            b["article_section"],
            b["source_url"],
            b["chunk_text"],
            b["source_hash"],
            b["date_scraped"],
            b["vector"]
        ) for b in self.batch_buffer]

        # ── Fallback: legacy schema without sub_jurisdiction ──────────────────
        insert_legacy = """
            INSERT INTO legal_frameworks
                (jurisdiction, source_url, chunk_text, source_hash, date_scraped, embedding)
            VALUES %s
        """
        values_legacy = [(
            b["jurisdiction"],
            b["source_url"],
            b["chunk_text"],
            b["source_hash"],
            b["date_scraped"],
            b["vector"]
        ) for b in self.batch_buffer]

        try:
            psycopg2.extras.execute_values(self.db_cursor, insert_full, values_full)
            self.db_conn.commit()
            spider.logger.info(
                f"SUCCESS: Bulk inserted {len(self.batch_buffer)} rows to Supabase (full schema)."
            )
        except Exception as e:
            err = str(e).lower()
            if "sub_jurisdiction" in err or "column" in err:
                spider.logger.warning(
                    "sub_jurisdiction column missing — retrying with legacy schema."
                )
                try:
                    self.db_conn.rollback()
                    psycopg2.extras.execute_values(self.db_cursor, insert_legacy, values_legacy)
                    self.db_conn.commit()
                    spider.logger.info(
                        f"SUCCESS: Bulk inserted {len(self.batch_buffer)} rows to Supabase (legacy schema)."
                    )
                except Exception as e2:
                    spider.logger.error(f"Error bulk inserting (legacy schema): {e2}")
                    self.db_conn.rollback()
            else:
                spider.logger.error(f"Error bulk inserting to Supabase: {e}")
                self.db_conn.rollback()

        # 2. Pinecone Multi-Vector Upsert
        try:
            pinecone_vectors = [{
                "id": b["id"],
                "values": b["vector"],
                "metadata": {
                    "jurisdiction": b["jurisdiction"] or "",
                    "sub_jurisdiction": b["sub_jurisdiction"] or "",
                    "document_type": b["document_type"] or "",
                    "article_section": b["article_section"] or "",
                    "source_url": b["source_url"] or "",
                    "chunk_index": b["chunk_index"]
                }
            } for b in self.batch_buffer]

            self.pinecone_index.upsert(vectors=pinecone_vectors)
            spider.logger.info(
                f"SUCCESS: Bulk upserted {len(self.batch_buffer)} vectors to Pinecone Index."
            )
        except Exception as e:
            spider.logger.error(f"Pinecone bulk payload transmission failed: {e}")

        self.batch_buffer.clear()

    def _write_local_fallback(self, item, spider):
        fallback_dir = "./fallback_backups"
        os.makedirs(fallback_dir, exist_ok=True)

        source_url = item.get("source_url", "unknown_url")
        url_hash = hashlib.md5(source_url.encode()).hexdigest()
        filename = os.path.join(fallback_dir, f"fallback_{url_hash}.jsonl")

        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(json.dumps(item) + "\n")
            spider.logger.info(f"💾 Fallback successful: Item written to {filename}")
        except Exception as e:
            spider.logger.error(f"💥 Local fallback engine failed to write: {e}")