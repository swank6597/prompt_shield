# Requirements Document

## Introduction

Replace the naive keyword-overlap scoring in `keyword_search.py` with a production-grade two-layer retrieval system. The current implementation uses raw token overlap counting which inflates scores for generic terms, lacks term weighting, and has no semantic understanding. The upgrade introduces a TF-IDF lexical engine with an inverted index for fast deterministic scoring, and a FAISS semantic vector search layer using local embeddings to catch synonym and paraphrase leaks. The goal is to reduce unnecessary LLM calls from ~60% to under 10% of requests while maintaining high accuracy.

## Glossary

- **Lexical_Engine**: The module (`lexical_engine.py`) responsible for building an in-memory inverted index at startup and computing TF-IDF scores for incoming prompts against the knowledge base
- **Semantic_Engine**: The module (`semantic_engine.py`) responsible for embedding prompts and knowledge chunks using a local sentence-transformer model and performing FAISS vector similarity search
- **Pre_Classifier**: The module (`pre_classifier.py`) responsible for deterministic routing decisions that determine whether an LLM call is needed
- **Prompt_Builder**: The module (`prompt_builder.py`) responsible for assembling the system and user prompts sent to the LLM
- **Inverted_Index**: A data structure mapping each token to a list of (document_id, term_frequency) pairs plus a document frequency count
- **TF-IDF_Score**: A normalized score (0.0–1.0) computed as the sum of term frequency multiplied by inverse document frequency for matching terms
- **Verdict**: A three-tier classification output from the Lexical_Engine: PUBLIC, AMBIGUOUS, or ENTERPRISE_LIKELY
- **Hybrid_Score**: A weighted combination of TF-IDF_Score and semantic similarity score (0.4 * lexical + 0.6 * semantic)
- **Knowledge_Base**: The collection of Markdown documents under the `knowledge/` directory loaded by `context_loader.py`
- **FAISS_Index**: A FAISS IndexFlatIP (inner product) index storing normalized embedding vectors for knowledge base chunks
- **Chunk**: A segment of a knowledge document, split on heading boundaries or at approximately 500 characters
- **Context_Loader**: The module (`context_loader.py`) that walks the `knowledge/` directory and loads all Markdown files into memory
- **Legacy_Search**: The existing `keyword_search.py` module that scores documents by raw token overlap count

## Requirements

### Requirement 1: TF-IDF Lexical Engine Initialization

**User Story:** As a system operator, I want the Lexical_Engine to build an inverted index from the Knowledge_Base at startup, so that prompt scoring is fast and deterministic without manual stopword maintenance.

#### Acceptance Criteria

1. WHEN the application starts, THE Lexical_Engine SHALL build an Inverted_Index from all documents loaded by the Context_Loader
2. THE Lexical_Engine SHALL compute IDF values for each token using the formula log(N / df(t)) where N is the total document count and df(t) is the document frequency of token t
3. WHEN a token appears in more than 60% of all documents, THE Lexical_Engine SHALL assign that token a near-zero IDF weight
4. THE Lexical_Engine SHALL complete index construction in under 2 seconds for up to 5000 documents
5. THE Lexical_Engine SHALL consume no more than 5MB of RAM for index storage at 5000 documents

### Requirement 2: TF-IDF Prompt Scoring

**User Story:** As the Pre_Classifier, I want to score prompts against the Knowledge_Base using TF-IDF, so that generic public prompts are distinguished from enterprise-relevant prompts without calling the LLM.

#### Acceptance Criteria

1. WHEN the Lexical_Engine receives a prompt, THE Lexical_Engine SHALL tokenize the prompt, compute TF-IDF scores against the Inverted_Index, and return a normalized TF-IDF_Score between 0.0 and 1.0
2. WHEN the TF-IDF_Score is below the configurable PUBLIC threshold (default 0.15), THE Lexical_Engine SHALL return a Verdict of PUBLIC
3. WHEN the TF-IDF_Score is at or above the configurable ENTERPRISE threshold (default 0.45), THE Lexical_Engine SHALL return a Verdict of ENTERPRISE_LIKELY
4. WHEN the TF-IDF_Score is at or above the PUBLIC threshold and below the ENTERPRISE threshold, THE Lexical_Engine SHALL return a Verdict of AMBIGUOUS
5. THE Lexical_Engine SHALL complete prompt scoring in at most 1 millisecond for a knowledge base of up to 5000 documents
6. THE Lexical_Engine SHALL return the top matching documents and matched terms alongside the TF-IDF_Score and Verdict

### Requirement 3: Semantic Embedding and FAISS Index

**User Story:** As a system operator, I want knowledge base documents to be embedded and indexed using a local sentence-transformer model, so that semantic similarity search is available without cloud API calls.

#### Acceptance Criteria

1. WHEN the application starts and no persisted FAISS_Index exists, THE Semantic_Engine SHALL load the configured embedding model (default: all-MiniLM-L6-v2), chunk all Knowledge_Base documents, embed the chunks, and build a FAISS_Index
2. WHEN the application starts and a persisted FAISS_Index exists with matching Knowledge_Base file modification times, THE Semantic_Engine SHALL load the FAISS_Index from disk without re-embedding
3. WHEN Knowledge_Base file modification times have changed since the persisted FAISS_Index was created, THE Semantic_Engine SHALL re-embed the changed documents and rebuild the FAISS_Index
4. THE Semantic_Engine SHALL chunk documents by splitting on Markdown heading boundaries or at approximately the configured chunk size (default: 500 characters)
5. THE Semantic_Engine SHALL persist the FAISS_Index and chunk metadata to the `backend/ai/index/` directory
6. THE Semantic_Engine SHALL run the embedding model entirely on the local CPU without making external network calls

### Requirement 4: Semantic Prompt Search

**User Story:** As the Pre_Classifier, I want to search for semantically similar knowledge chunks given a prompt, so that synonym and paraphrase-based enterprise leaks are detected even when exact keywords differ.

#### Acceptance Criteria

1. WHEN the Semantic_Engine receives a prompt, THE Semantic_Engine SHALL embed the prompt using the configured model and perform a FAISS inner-product search returning the top-k most similar chunks
2. THE Semantic_Engine SHALL return a semantic similarity score between 0.0 and 1.0, the matched chunks, and the source document filenames
3. THE Semantic_Engine SHALL complete prompt embedding and search in under 50 milliseconds on CPU for a knowledge base of up to 5000 chunks

### Requirement 5: Three-Tier Pre-Classifier Routing

**User Story:** As the system, I want the Pre_Classifier to use the Lexical_Engine verdict to route prompts through a three-tier decision, so that only truly ambiguous prompts incur the cost of semantic search or LLM calls.

#### Acceptance Criteria

1. WHEN Presidio detects secrets, THE Pre_Classifier SHALL skip the LLM and return the hard_block decision path, taking priority over all other routing decisions including PII detection and lexical/semantic verdicts
2. WHEN Presidio detects PII only and the Lexical_Engine returns a PUBLIC verdict, THE Pre_Classifier SHALL skip the LLM and return the pii_only decision path
3. WHEN the Lexical_Engine returns a PUBLIC verdict and no PII is detected, THE Pre_Classifier SHALL skip the LLM and return the general_knowledge decision path without precluding semantic processing for enrichment purposes
4. WHEN the Lexical_Engine returns an ENTERPRISE_LIKELY verdict, THE Pre_Classifier SHALL skip the LLM and return the enterprise_detected decision path
5. WHEN the Lexical_Engine returns an AMBIGUOUS verdict, THE Pre_Classifier SHALL invoke the Semantic_Engine and compute the Hybrid_Score

### Requirement 6: Hybrid Scoring for Ambiguous Cases

**User Story:** As the Pre_Classifier, I want to combine lexical and semantic scores into a hybrid score for ambiguous prompts, so that the final routing decision accounts for both exact term matches and semantic similarity.

#### Acceptance Criteria

1. WHEN the Pre_Classifier computes the Hybrid_Score, THE Pre_Classifier SHALL calculate it as (configurable lexical weight, default 0.4) multiplied by TF-IDF_Score plus (configurable semantic weight, default 0.6) multiplied by the semantic similarity score
2. WHEN the Hybrid_Score is below the configurable PUBLIC threshold (default 0.30), including when both lexical and semantic scores are zero, THE Pre_Classifier SHALL skip the LLM and return the semantic_confirmed_public decision path
3. WHEN the Hybrid_Score is at or above the configurable ENTERPRISE threshold (default 0.55), THE Pre_Classifier SHALL skip the LLM and return the semantic_confirmed_enterprise decision path
4. WHEN the Hybrid_Score is at or above the PUBLIC threshold (default 0.30) and below the ENTERPRISE threshold (default 0.55), THE Pre_Classifier SHALL call the LLM and return the true_ambiguity decision path

### Requirement 7: Updated LLM Context with Semantic Chunks

**User Story:** As a developer, I want the Prompt_Builder to use specific semantic chunks instead of full documents when constructing LLM prompts, so that token usage is reduced and LLM accuracy is improved.

#### Acceptance Criteria

1. WHEN the LLM is called and semantic chunks are available, THE Prompt_Builder SHALL include the relevant semantic chunks (approximately 500 characters each) in the LLM prompt alongside full source documents when both are available
2. WHEN the LLM is called and no semantic chunks are available, THE Prompt_Builder SHALL fall back to using full knowledge documents as retrieved by the legacy approach
3. THE Prompt_Builder SHALL preserve the existing prompt structure (system prompt with schema instructions, user prompt with retrieved knowledge and masked text)

### Requirement 8: Configurable Thresholds via Environment Variables

**User Story:** As a system operator, I want all scoring thresholds, model names, and feature weights to be configurable via environment variables, so that tuning can be done without code changes.

#### Acceptance Criteria

1. THE system SHALL read the following configuration from environment variables with the specified defaults: PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD (0.15), PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD (0.45), PROMPTSHIELD_EMBEDDING_MODEL (all-MiniLM-L6-v2), PROMPTSHIELD_SEMANTIC_CHUNK_SIZE (500), PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT (0.4), PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT (0.6), PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD (0.30), PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD (0.55), PROMPTSHIELD_USE_LEGACY_SEARCH (false)
2. WHEN the configuration values are loaded, THE system SHALL make them available via `config.py` consistent with the existing configuration pattern (dotenv-based with fallback to OS environment variables)

### Requirement 9: Legacy Fallback Support

**User Story:** As a system operator, I want to revert to the old keyword search behavior by toggling an environment variable, so that the system can be rolled back without code changes if the new engines have issues.

#### Acceptance Criteria

1. WHEN PROMPTSHIELD_USE_LEGACY_SEARCH is set to true, THE Pre_Classifier SHALL use the existing `keyword_search.py` module for scoring instead of the Lexical_Engine and Semantic_Engine
2. WHEN PROMPTSHIELD_USE_LEGACY_SEARCH is set to false or not set, THE Pre_Classifier SHALL use the Lexical_Engine and Semantic_Engine for scoring
3. THE system SHALL preserve the existing `keyword_search.py` module without deletion to support the legacy fallback path
4. WHEN neither the Legacy_Search module nor the Lexical_Engine and Semantic_Engine can be loaded due to system errors or missing dependencies, THE system SHALL continue running without search functionality, returning no scoring results rather than crashing

### Requirement 10: Performance and Accuracy Targets

**User Story:** As a system operator, I want the upgraded retrieval system to meet defined performance and accuracy targets, so that response times remain acceptable and classification accuracy improves over the current state.

#### Acceptance Criteria

1. THE system SHALL route fewer than 10% of total requests to the LLM
2. THE system SHALL produce a false positive rate (public prompts incorrectly routed to LLM or flagged as enterprise) of under 2%
3. THE system SHALL produce a false negative rate (enterprise prompts incorrectly classified as safe/public) of under 1%
4. WHILE a request follows a non-LLM decision path, THE system SHALL return a response in under 200 milliseconds
5. WHILE a request follows an LLM decision path, THE system SHALL return a response in under 8 seconds

### Requirement 11: Dependency Management

**User Story:** As a developer, I want the new dependencies (sentence-transformers and faiss-cpu) added to requirements.txt, so that the project can be set up and deployed consistently.

#### Acceptance Criteria

1. THE system SHALL declare sentence-transformers and faiss-cpu as dependencies in `backend/requirements.txt`
2. WHEN the Semantic_Engine loads the embedding model for the first time and the model is not cached locally, THE Semantic_Engine SHALL download the model automatically (approximately 80MB)
