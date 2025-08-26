# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository implements a document processing pipeline using Docling with SmolDocling VLM (Visual Language Model) for OCR and layout recognition, combined with Ollama LLM integration for Q&A analysis. The project focuses on processing German bank statements (Kontoauszüge) with specific attention to European number formats.

## Key Architecture Components

### 1. Document Processing Pipeline
- **docling_processor.py**: Main entry point using Docling library with SmolDocling VLM (256M parameter model) for visual document analysis
- **simple_pdf_processor.py**: Alternative lightweight processor using pdfplumber for simpler PDF extraction

### 2. Kontoauszug Analysis System (v1-v8)
The project contains 8 iterative versions of bank statement analysis, each improving on specific issues:
- **v1-v3**: Basic extraction and LLM Q&A
- **v4**: Added transaction categorization and valuta dates
- **v5**: Improved balance extraction from documents (not calculated)
- **v6**: Step-by-step extraction logic with validation rules
- **v7**: Fixed LLM summation with explicit instructions
- **v8**: Dual number representation (original string + converted number) for validation

### 3. Critical Number Format Handling
The system must handle German/European number formats correctly:
```python
# German format: "450.105,96" → 450105.96
# The parse_german_amount() function in all analysis scripts handles:
# - Thousand separator: period (.) → remove
# - Decimal separator: comma (,) → convert to period
# - Automatic format detection for mixed inputs
```

## Development Commands

### Setup Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/WSL
pip install -r requirements.txt
```

### Run Document Processing
```bash
# Basic PDF processing with Docling
python docling_processor.py --file document.pdf

# With Q&A analysis
python docling_processor.py --file document.pdf --question "Summarize the document" --model qwen3:8b

# Simple PDF processing (faster, less accurate)
python simple_pdf_processor.py Konto_*.pdf
```

### Run Kontoauszug Analysis
```bash
# Latest version (v8) with dual number representation
python analyze_kontoauszuege_v8.py --model qwen3:8b

# Specific version with different model
python analyze_kontoauszuege_v7.py --model qwen3:30b

# All versions expect JSON files from Docling processing
```

### Ollama Configuration
The project uses Ollama with custom URL `https://fs.aiora.rest` by default. Available models:
- qwen3:8b (recommended for speed)
- qwen3:30b (better accuracy)
- qwen3:14b (balanced)

To use local Ollama:
```bash
ollama serve  # Start local server
python docling_processor.py --file doc.pdf --ollama_url http://localhost:11434
```

## Critical Implementation Details

### LLM Prompt Engineering for German Documents
When processing German bank statements, the LLM must be explicitly instructed about:
1. **Number formats**: Always specify that German format uses period for thousands and comma for decimals
2. **Balance extraction**: End balance must be extracted from document, NOT calculated
3. **Transaction summation**: LLM must sum ALL transactions, not just first/last
4. **Dual representation (v8)**: Request both `betrag_original` (string) and `betrag_nummer` (float)

### Validation Chain
1. **Conversion Validation**: Check if LLM correctly converted German numbers
2. **Balance Validation**: Start balance + sum(transactions) = end balance
3. **Continuity Validation**: End balance of statement N = start balance of statement N+1

### Common Issues and Solutions
- **Wrong number parsing**: LLM returns "405107.75" as string → parse_german_amount() detects format automatically
- **Missing transactions**: Some statements extract 0 transactions → check PDF structure and table detection
- **Summation errors**: LLM sums only first transaction → use explicit examples in prompt showing full summation

## File Structure Patterns

### Input Files
- PDF documents: Original bank statements in `/mnt/c/Projects/Sparkasse/docs/`
- JSON results: Processed by Docling, named `Konto_Auszug_YYYY_NNNN_result.json`

### Output Files
- Analysis results: `kontoauszuege_analyse_komplett_vX.json` for each version
- Individual analyses: `{filename}_vX_analysis.json`

## Testing Approach

The project uses 5 German bank statements (Kontoauszüge 3-7 from 2022) as test data. Success metrics:
1. All 5 balance validations pass
2. Continuity between statements confirmed
3. Conversion errors < 5% of total numbers

## Dependencies and Performance

- **GPU Required**: SmolDocling VLM needs ~4GB VRAM
- **Docling**: Handles document structure extraction
- **Ollama**: LLM inference (network or local)
- **Processing time**: ~30-60s per document with VLM, ~5-10s without