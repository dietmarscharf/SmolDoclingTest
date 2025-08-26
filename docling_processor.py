#!/usr/bin/env python3
"""
Docling Document Processor mit SmolDocling VLM Support
Verarbeitet verschiedene Dokumentformate und ermöglicht Q&A via LLM
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import warnings
warnings.filterwarnings("ignore")

# Docling imports
try:
    from docling.document_converter import DocumentConverter, PipelineOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
        TesseractOcrOptions,
        EasyOcrOptions
    )
except ImportError as e:
    print(f"Fehler beim Import von Docling: {e}")
    print("Bitte installieren Sie Docling mit: pip install docling")
    sys.exit(1)

# Ollama import
try:
    import ollama
except ImportError:
    print("Warnung: Ollama Python Client nicht installiert.")
    print("LLM Q&A Funktionalität wird deaktiviert.")
    print("Installation mit: pip install ollama")
    ollama = None

# Optional: EasyOCR import
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    print("Info: EasyOCR nicht verfügbar. SmolDocling VLM wird für OCR verwendet.")

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DoclingProcessor:
    """Hauptklasse für Dokumentverarbeitung mit SmolDocling"""
    
    SUPPORTED_FORMATS = {
        '.pdf': 'PDF Dokument',
        '.docx': 'Word Dokument',
        '.xlsx': 'Excel Tabelle',
        '.pptx': 'PowerPoint Präsentation',
        '.html': 'HTML Dokument',
        '.htm': 'HTML Dokument',
        '.md': 'Markdown Dokument',
        '.xml': 'XML Dokument',
        '.png': 'PNG Bild',
        '.jpg': 'JPEG Bild',
        '.jpeg': 'JPEG Bild',
        '.tiff': 'TIFF Bild',
        '.tif': 'TIFF Bild'
    }
    
    def __init__(self, use_vlm: bool = True, use_easyocr: bool = False, 
                 ollama_url: str = "https://fs.aiora.rest"):
        """
        Initialisiert den Processor
        
        Args:
            use_vlm: SmolDocling VLM verwenden
            use_easyocr: EasyOCR als zusätzliche OCR-Engine
            ollama_url: URL für Ollama API
        """
        self.use_vlm = use_vlm
        self.use_easyocr = use_easyocr and EASYOCR_AVAILABLE
        self.ollama_url = ollama_url
        
        # Pipeline Options konfigurieren
        self.pipeline_options = self._configure_pipeline()
        
        # Document Converter initialisieren
        logger.info(f"Initialisiere DocumentConverter (VLM: {use_vlm})")
        self.converter = DocumentConverter(
            pipeline_options=self.pipeline_options
        )
        
        # Ollama Client setup
        if ollama:
            self.ollama_client = ollama.Client(host=ollama_url)
            logger.info(f"Ollama Client konfiguriert: {ollama_url}")
    
    def _configure_pipeline(self) -> PipelineOptions:
        """Konfiguriert die Processing Pipeline"""
        pipeline_options = PipelineOptions()
        
        # PDF Pipeline mit SmolDocling VLM
        if self.use_vlm:
            pdf_options = PdfPipelineOptions()
            pdf_options.do_ocr = True
            pdf_options.do_table_structure = True
            pdf_options.table_structure_options.mode = TableFormerMode.ACCURATE
            
            # OCR Engine auswählen
            if self.use_easyocr:
                pdf_options.ocr_options = EasyOcrOptions(
                    force_full_page_ocr=True,
                    lang=["de", "en"]  # Deutsch und Englisch
                )
                logger.info("Verwende EasyOCR für zusätzliche OCR-Funktionalität")
            else:
                # SmolDocling als Standard VLM
                logger.info("Verwende SmolDocling VLM für OCR und Layout-Erkennung")
            
            pipeline_options.pdf_options = pdf_options
        
        # Aktiviere Table Recognition
        pipeline_options.do_table_structure = True
        
        return pipeline_options
    
    def validate_file(self, file_path: str) -> Path:
        """
        Validiert die Eingabedatei
        
        Args:
            file_path: Pfad zur Datei
            
        Returns:
            Path Objekt wenn valide
            
        Raises:
            ValueError: Bei ungültiger Datei
        """
        path = Path(file_path)
        
        if not path.exists():
            raise ValueError(f"Datei nicht gefunden: {file_path}")
        
        if not path.is_file():
            raise ValueError(f"Pfad ist keine Datei: {file_path}")
        
        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            supported = ", ".join(self.SUPPORTED_FORMATS.keys())
            raise ValueError(f"Nicht unterstütztes Format: {suffix}\nUnterstützte Formate: {supported}")
        
        logger.info(f"Verarbeite {self.SUPPORTED_FORMATS[suffix]}: {path.name}")
        return path
    
    def convert_document(self, file_path: str) -> Dict[str, Any]:
        """
        Konvertiert ein Dokument mit Docling
        
        Args:
            file_path: Pfad zum Dokument
            
        Returns:
            Konvertiertes Dokument als Dictionary
        """
        path = self.validate_file(file_path)
        
        logger.info(f"Starte Konvertierung mit {'SmolDocling VLM' if self.use_vlm else 'Standard Pipeline'}...")
        
        try:
            # Dokument konvertieren
            result = self.converter.convert(str(path))
            
            # Zu Dictionary exportieren
            doc_dict = result.document.export_to_dict()
            
            # Metadaten hinzufügen
            doc_dict['metadata'] = {
                'source_file': str(path),
                'file_type': path.suffix.lower(),
                'processing_pipeline': 'SmolDocling VLM' if self.use_vlm else 'Standard',
                'ocr_engine': 'EasyOCR' if self.use_easyocr else 'SmolDocling VLM'
            }
            
            # Statistiken
            if 'pages' in doc_dict:
                doc_dict['metadata']['page_count'] = len(doc_dict.get('pages', []))
            
            # Tabellen zählen
            table_count = 0
            if 'tables' in doc_dict:
                table_count = len(doc_dict.get('tables', []))
            doc_dict['metadata']['table_count'] = table_count
            
            logger.info(f"Konvertierung erfolgreich: {doc_dict['metadata'].get('page_count', 0)} Seiten, {table_count} Tabellen")
            
            return doc_dict
            
        except Exception as e:
            logger.error(f"Fehler bei der Konvertierung: {e}")
            raise
    
    def export_as_markdown(self, file_path: str) -> str:
        """
        Exportiert Dokument als Markdown
        
        Args:
            file_path: Pfad zum Dokument
            
        Returns:
            Markdown String
        """
        path = self.validate_file(file_path)
        
        logger.info("Exportiere als Markdown...")
        
        try:
            result = self.converter.convert(str(path))
            markdown = result.document.export_to_markdown()
            
            # Header mit Metadaten hinzufügen
            header = f"# Dokument: {path.name}\n\n"
            header += f"**Format:** {self.SUPPORTED_FORMATS[path.suffix.lower()]}\n"
            header += f"**Verarbeitet mit:** {'SmolDocling VLM' if self.use_vlm else 'Standard Pipeline'}\n\n"
            header += "---\n\n"
            
            return header + markdown
            
        except Exception as e:
            logger.error(f"Fehler beim Markdown Export: {e}")
            raise
    
    def ask_question(self, document_content: Dict[str, Any], question: str, 
                    model: str = "qwen3:latest") -> Dict[str, Any]:
        """
        Stellt eine Frage zum Dokumentinhalt via LLM
        
        Args:
            document_content: Konvertiertes Dokument
            question: Frage zum Dokument
            model: LLM Modell (default: qwen3:latest)
            
        Returns:
            Antwort als Dictionary
        """
        if not ollama:
            return {
                "error": "Ollama nicht verfügbar",
                "message": "Bitte installieren Sie ollama mit: pip install ollama"
            }
        
        logger.info(f"Stelle Frage an LLM ({model}): {question}")
        
        try:
            # Dokument-Text extrahieren
            doc_text = self._extract_text_from_dict(document_content)
            
            # Prompt erstellen
            prompt = f"""Du bist ein hilfreicher Assistent, der Fragen zu Dokumenten beantwortet.
            
Hier ist der Inhalt des Dokuments:

{doc_text[:10000]}  # Limitiere auf 10000 Zeichen für Context

Basierend auf diesem Dokument, beantworte bitte folgende Frage:
{question}

Antworte im JSON Format mit folgender Struktur:
{{
    "frage": "{question}",
    "antwort": "Deine detaillierte Antwort hier",
    "kontext": "Relevanter Textausschnitt aus dem Dokument",
    "konfidenz": "hoch/mittel/niedrig"
}}"""
            
            # Anfrage an Ollama
            response = self.ollama_client.chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Du bist ein Experte für Dokumentanalyse. Antworte immer im angeforderten JSON Format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                format="json",
                options={
                    "temperature": 0.3,  # Niedrigere Temperatur für faktische Antworten
                    "top_p": 0.9
                }
            )
            
            # Antwort parsen
            if response and 'message' in response:
                answer_text = response['message']['content']
                try:
                    answer_json = json.loads(answer_text)
                    logger.info("LLM Antwort erfolgreich erhalten")
                    return answer_json
                except json.JSONDecodeError:
                    # Fallback wenn JSON parsing fehlschlägt
                    return {
                        "frage": question,
                        "antwort": answer_text,
                        "kontext": "",
                        "konfidenz": "mittel"
                    }
            
        except Exception as e:
            logger.error(f"Fehler bei LLM Anfrage: {e}")
            return {
                "error": str(e),
                "frage": question,
                "antwort": f"Fehler bei der Verarbeitung: {str(e)}"
            }
    
    def _extract_text_from_dict(self, doc_dict: Dict[str, Any]) -> str:
        """Extrahiert Text aus dem Dokument Dictionary"""
        text_parts = []
        
        # Haupttext extrahieren
        if 'text' in doc_dict:
            text_parts.append(doc_dict['text'])
        
        # Seiten durchgehen
        if 'pages' in doc_dict:
            for page in doc_dict['pages']:
                if 'text' in page:
                    text_parts.append(page['text'])
        
        # Paragraphen
        if 'paragraphs' in doc_dict:
            for para in doc_dict['paragraphs']:
                if 'text' in para:
                    text_parts.append(para['text'])
        
        # Tabellen als Text
        if 'tables' in doc_dict:
            for table in doc_dict['tables']:
                text_parts.append("[Tabelle gefunden]")
                if 'cells' in table:
                    for row in table['cells']:
                        row_text = " | ".join([str(cell.get('text', '')) for cell in row])
                        text_parts.append(row_text)
        
        return "\n\n".join(text_parts)
    
    def process(self, file_path: str, output_format: str = "json", 
               question: Optional[str] = None, model: str = "qwen3:latest") -> Any:
        """
        Hauptverarbeitungsmethode
        
        Args:
            file_path: Pfad zur Eingabedatei
            output_format: Ausgabeformat (json/markdown)
            question: Optionale Frage für Q&A
            model: LLM Modell für Q&A
            
        Returns:
            Verarbeitetes Dokument im gewünschten Format
        """
        try:
            # Dokument verarbeiten
            if output_format.lower() == "markdown":
                result = self.export_as_markdown(file_path)
            else:
                result = self.convert_document(file_path)
            
            # Q&A wenn Frage gestellt wurde
            if question and output_format.lower() == "json":
                qa_result = self.ask_question(result, question, model)
                result['qa'] = qa_result
            
            return result
            
        except Exception as e:
            logger.error(f"Verarbeitungsfehler: {e}")
            raise


def main():
    """Hauptfunktion für CLI"""
    parser = argparse.ArgumentParser(
        description="Docling Document Processor mit SmolDocling VLM Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # PDF konvertieren zu JSON
  python docling_processor.py --file dokument.pdf
  
  # Mit Q&A Funktion
  python docling_processor.py --file dokument.pdf --question "Was ist die Hauptaussage?"
  
  # Als Markdown exportieren
  python docling_processor.py --file dokument.pdf --output_format markdown
  
  # Mit speziellem LLM Modell
  python docling_processor.py --file dokument.pdf --question "Zusammenfassung?" --model llama3.3:latest
        """
    )
    
    parser.add_argument(
        '--file', '-f',
        type=str,
        required=True,
        help='Pfad zur Eingabedatei (PDF, DOCX, XLSX, PPTX, HTML, MD, Bilder)'
    )
    
    parser.add_argument(
        '--output_format', '-o',
        type=str,
        choices=['json', 'markdown'],
        default='json',
        help='Ausgabeformat (default: json)'
    )
    
    parser.add_argument(
        '--question', '-q',
        type=str,
        help='Optionale Frage zum Dokument für Q&A'
    )
    
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='qwen3:latest',
        help='LLM Modell für Q&A (default: qwen3:latest)'
    )
    
    parser.add_argument(
        '--ollama_url',
        type=str,
        default='https://fs.aiora.rest',
        help='Ollama API URL (default: https://fs.aiora.rest)'
    )
    
    parser.add_argument(
        '--no-vlm',
        action='store_true',
        help='SmolDocling VLM deaktivieren'
    )
    
    parser.add_argument(
        '--use-easyocr',
        action='store_true',
        help='EasyOCR als zusätzliche OCR-Engine verwenden'
    )
    
    parser.add_argument(
        '--output-file',
        type=str,
        help='Optionale Ausgabedatei (sonst stdout)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose Logging aktivieren'
    )
    
    args = parser.parse_args()
    
    # Logging Level setzen
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Processor initialisieren
    processor = DoclingProcessor(
        use_vlm=not args.no_vlm,
        use_easyocr=args.use_easyocr,
        ollama_url=args.ollama_url
    )
    
    try:
        # Dokument verarbeiten
        result = processor.process(
            file_path=args.file,
            output_format=args.output_format,
            question=args.question,
            model=args.model
        )
        
        # Ausgabe formatieren
        if args.output_format == 'json':
            output = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            output = result
        
        # Ausgabe schreiben
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"✓ Ausgabe gespeichert in: {args.output_file}")
        else:
            print(output)
        
    except Exception as e:
        logger.error(f"Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()