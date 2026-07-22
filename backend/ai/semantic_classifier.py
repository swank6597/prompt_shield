# semantic_classifier.py
# Enterprise Context Intelligence (ECI) analyzer - orchestrates context_loader,
# keyword_search, prompt_builder, and ollama_client, then parses/validates the
# LLM's JSON response against schema.json and returns the structured AnalysisResult.
# Note: this classifier only understands context; it does not decide Allow/Warn/Mask/Block.
