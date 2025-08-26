# Docling Document Processor mit SmolDocling VLM

Ein leistungsstarkes Python-Tool zur lokalen Dokumentverarbeitung mit SmolDocling Visual Language Model (VLM) für optimale Layout- und Tabellenerkennung.

## Features

- **Multi-Format Support**: PDF (inkl. Scans), DOCX, XLSX, PPTX, HTML, Markdown, XML, Bilder (PNG/JPEG/TIFF)
- **SmolDocling VLM**: Fortschrittliche visuelle Dokumentanalyse mit 256M-Parameter Modell
- **OCR-Fähigkeiten**: Integrierte OCR über SmolDocling VLM, optional EasyOCR
- **LLM Q&A**: Dokumentbasierte Fragen via Ollama (Llama 3.3, Qwen 3.0)
- **Strukturierte Ausgabe**: JSON oder Markdown Export
- **GPU-Optimiert**: Läuft effizient auf 16GB VRAM GPUs

## Installation

### 1. Repository klonen
```bash
git clone <repository-url>
cd SmolDoclingTest
```

### 2. Python-Umgebung einrichten (empfohlen: Python 3.9+)
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate  # Windows
```

### 3. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 4. SmolDocling Modell Setup
SmolDocling wird automatisch beim ersten Start heruntergeladen (~1GB).

## WICHTIG: Ollama Modelle

### Erforderliche Ollama Modelle

Bevor Sie das Q&A Feature nutzen können, müssen Sie eines der folgenden Modelle herunterladen:

#### Option 1: Qwen 3.0 (Empfohlen - Kleiner und schneller)
```bash
# Qwen3 8B Modell (~4.7GB)
ollama pull qwen3:8b

# Oder kleinere Version (~2GB)
ollama pull qwen3:4b

# Für beste Qualität (~14GB)
ollama pull qwen3:14b
```

#### Option 2: Llama 3.3 (Neueste Version)
```bash
# Llama 3.3 8B (~4.7GB)
ollama pull llama3.3:8b

# Oder größere Version für bessere Qualität (~40GB)
ollama pull llama3.3:70b
```

#### Option 3: Qwen 2.5 Coder (Für technische Dokumente)
```bash
# Spezialisiert auf Code und technische Inhalte (~4GB)
ollama pull qwen2.5-coder:7b
```

### Mit Custom Ollama URL (fs.aiora.rest)

Das Skript verwendet standardmäßig `https://fs.aiora.rest` als Ollama-Endpoint. Falls Sie einen lokalen Ollama-Server verwenden möchten:

```bash
# Lokalen Ollama Server starten
ollama serve

# Dann im Skript mit lokalem Endpoint
python docling_processor.py --file dokument.pdf --ollama_url http://localhost:11434
```

### Verfügbare Modelle prüfen
```bash
# Liste aller installierten Modelle
ollama list

# Modell testen
ollama run qwen3:8b "Test"
```

## Verwendung

### Grundlegende Befehle

#### 1. PDF zu JSON konvertieren
```bash
python docling_processor.py --file beispiel.pdf
```

#### 2. Mit Q&A Funktion
```bash
python docling_processor.py --file dokument.pdf --question "Was ist die Hauptaussage des Dokuments?"
```

#### 3. Markdown Export
```bash
python docling_processor.py --file dokument.pdf --output_format markdown
```

#### 4. Mit spezifischem LLM Modell
```bash
python docling_processor.py --file dokument.pdf \
    --question "Fasse die wichtigsten Punkte zusammen" \
    --model qwen3:8b
```

#### 5. Ausgabe in Datei speichern
```bash
python docling_processor.py --file dokument.pdf \
    --output_format json \
    --output-file ergebnis.json
```

### Erweiterte Optionen

```bash
# SmolDocling VLM deaktivieren (schneller, weniger genau)
python docling_processor.py --file dokument.pdf --no-vlm

# EasyOCR zusätzlich aktivieren
python docling_processor.py --file dokument.pdf --use-easyocr

# Verbose Logging
python docling_processor.py --file dokument.pdf -v

# Alles kombiniert
python docling_processor.py \
    --file komplexes_dokument.pdf \
    --question "Welche Tabellen enthält das Dokument?" \
    --model qwen3:14b \
    --output_format json \
    --output-file analyse.json \
    --verbose
```

### Kommandozeilen-Argumente

| Argument | Kurz | Beschreibung | Default |
|----------|------|--------------|---------|
| `--file` | `-f` | Pfad zur Eingabedatei (required) | - |
| `--output_format` | `-o` | Ausgabeformat: json oder markdown | json |
| `--question` | `-q` | Frage für Q&A Analyse | - |
| `--model` | `-m` | LLM Modell für Q&A | qwen3:latest |
| `--ollama_url` | - | Ollama API URL | https://fs.aiora.rest |
| `--no-vlm` | - | SmolDocling VLM deaktivieren | False |
| `--use-easyocr` | - | EasyOCR zusätzlich verwenden | False |
| `--output-file` | - | Ausgabe in Datei speichern | - |
| `--verbose` | `-v` | Detaillierte Logs | False |

## Beispiel-Workflow

### 1. Einfaches Dokument analysieren
```bash
# PDF einlesen und Struktur extrahieren
python docling_processor.py --file bericht.pdf --output-file bericht.json

# Fragen zum Dokument stellen
python docling_processor.py --file bericht.pdf \
    --question "Was sind die Hauptergebnisse?" \
    --model qwen3:8b
```

### 2. Batch-Verarbeitung (Beispiel-Skript)
```python
import subprocess
import json
from pathlib import Path

# Alle PDFs im Ordner verarbeiten
for pdf_file in Path("dokumente").glob("*.pdf"):
    cmd = [
        "python", "docling_processor.py",
        "--file", str(pdf_file),
        "--output_format", "json",
        "--output-file", f"output/{pdf_file.stem}.json"
    ]
    subprocess.run(cmd)
```

### 3. Mit Custom Analyse
```python
from docling_processor import DoclingProcessor

# Processor initialisieren
processor = DoclingProcessor(use_vlm=True, ollama_url="https://fs.aiora.rest")

# Dokument verarbeiten
result = processor.convert_document("dokument.pdf")

# Eigene Analyse
text = processor._extract_text_from_dict(result)
print(f"Dokument hat {len(text)} Zeichen")
print(f"Gefundene Tabellen: {result['metadata']['table_count']}")

# Q&A
answer = processor.ask_question(result, "Zusammenfassung in 3 Sätzen", model="qwen3:8b")
print(answer['antwort'])
```

## JSON Output Struktur

```json
{
  "metadata": {
    "source_file": "dokument.pdf",
    "file_type": ".pdf",
    "processing_pipeline": "SmolDocling VLM",
    "ocr_engine": "SmolDocling VLM",
    "page_count": 10,
    "table_count": 3
  },
  "text": "Extrahierter Dokumenttext...",
  "pages": [...],
  "tables": [...],
  "qa": {
    "frage": "Was ist die Hauptaussage?",
    "antwort": "Die Hauptaussage des Dokuments...",
    "kontext": "Relevanter Textausschnitt...",
    "konfidenz": "hoch"
  }
}
```

## Performance-Tipps

1. **GPU nutzen**: Stellen Sie sicher, dass PyTorch GPU erkennt:
   ```python
   import torch
   print(torch.cuda.is_available())  # Sollte True sein
   ```

2. **Modell-Cache**: SmolDocling wird beim ersten Start gecacht (~1GB)

3. **Batch-Processing**: Für viele Dokumente, nutzen Sie Batch-Verarbeitung

4. **Memory Management**: Bei großen PDFs (>100 Seiten) kann `--no-vlm` helfen

## Troubleshooting

### Ollama Verbindungsfehler
```bash
# Prüfen ob Ollama erreichbar ist
curl https://fs.aiora.rest/api/tags

# Oder lokalen Server nutzen
ollama serve
python docling_processor.py --file test.pdf --ollama_url http://localhost:11434
```

### GPU nicht erkannt
```bash
# CUDA Version prüfen
nvidia-smi

# PyTorch mit CUDA neu installieren
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Out of Memory
```bash
# Kleineres Modell verwenden
python docling_processor.py --file large.pdf --model qwen3:4b

# Oder VLM deaktivieren
python docling_processor.py --file large.pdf --no-vlm
```

## Unterstützte Formate

| Format | Dateityp | SmolDocling VLM | OCR Support |
|--------|----------|-----------------|-------------|
| PDF | .pdf | ✅ Optimal | ✅ Integriert |
| Word | .docx | ✅ Gut | ✅ Bei Bildern |
| Excel | .xlsx | ✅ Tabellen | ✅ Bei Bildern |
| PowerPoint | .pptx | ✅ Layout | ✅ Bei Bildern |
| HTML | .html/.htm | ⚠️ Basic | ❌ |
| Markdown | .md | ⚠️ Basic | ❌ |
| XML | .xml | ⚠️ Basic | ❌ |
| Bilder | .png/.jpg/.tiff | ✅ Direkt | ✅ Voll |

## Lizenz

Dieses Projekt nutzt Open-Source Komponenten:
- Docling: Apache 2.0
- SmolDocling: Apache 2.0
- Ollama: MIT
- EasyOCR: Apache 2.0

## Support

Bei Problemen oder Fragen:
1. Prüfen Sie die Logs mit `--verbose`
2. Stellen Sie sicher, dass alle Dependencies installiert sind
3. Verifizieren Sie die Ollama-Verbindung
4. Prüfen Sie GPU/CUDA Setup für optimale Performance