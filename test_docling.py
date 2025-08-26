#!/usr/bin/env python3
"""
Test-Skript für Docling Document Processor
Testet verschiedene Funktionen und Dokumenttypen
"""

import json
import sys
from pathlib import Path
from docling_processor import DoclingProcessor
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_files():
    """Erstellt einfache Testdateien"""
    
    # Test Markdown
    test_md = """# Test Dokument

## Einleitung
Dies ist ein Test-Dokument für den Docling Processor.

## Hauptteil
- Punkt 1: SmolDocling VLM Test
- Punkt 2: OCR Funktionalität
- Punkt 3: LLM Integration

## Tabelle
| Feature | Status | Beschreibung |
|---------|--------|--------------|
| PDF | ✅ | Vollständige Unterstützung |
| OCR | ✅ | Via SmolDocling |
| Q&A | ✅ | Via Ollama |

## Zusammenfassung
Dieses Dokument testet die Grundfunktionen des Processors.
"""
    
    with open("test_document.md", "w", encoding="utf-8") as f:
        f.write(test_md)
    logger.info("✓ test_document.md erstellt")
    
    # Test HTML
    test_html = """<!DOCTYPE html>
<html>
<head><title>Test HTML</title></head>
<body>
    <h1>HTML Test Dokument</h1>
    <p>Dies ist ein Test für HTML Verarbeitung.</p>
    <table>
        <tr><th>Spalte 1</th><th>Spalte 2</th></tr>
        <tr><td>Daten 1</td><td>Daten 2</td></tr>
    </table>
</body>
</html>"""
    
    with open("test_document.html", "w", encoding="utf-8") as f:
        f.write(test_html)
    logger.info("✓ test_document.html erstellt")
    
    return ["test_document.md", "test_document.html"]


def test_basic_conversion():
    """Testet Basis-Konvertierung"""
    print("\n" + "="*60)
    print("TEST 1: Basis-Konvertierung")
    print("="*60)
    
    processor = DoclingProcessor(use_vlm=True)
    
    # Test mit Markdown
    try:
        result = processor.convert_document("test_document.md")
        print("✅ Markdown Konvertierung erfolgreich")
        print(f"   - Metadaten: {result['metadata']}")
        
    except Exception as e:
        print(f"❌ Fehler bei Markdown: {e}")
    
    # Test mit HTML
    try:
        result = processor.convert_document("test_document.html")
        print("✅ HTML Konvertierung erfolgreich")
        print(f"   - Tabellen gefunden: {result['metadata'].get('table_count', 0)}")
        
    except Exception as e:
        print(f"❌ Fehler bei HTML: {e}")


def test_markdown_export():
    """Testet Markdown Export"""
    print("\n" + "="*60)
    print("TEST 2: Markdown Export")
    print("="*60)
    
    processor = DoclingProcessor(use_vlm=False)  # Schneller ohne VLM
    
    try:
        markdown = processor.export_as_markdown("test_document.html")
        print("✅ Markdown Export erfolgreich")
        print("   Erste 200 Zeichen:")
        print("   " + markdown[:200].replace("\n", "\n   "))
        
    except Exception as e:
        print(f"❌ Fehler beim Export: {e}")


def test_llm_qa():
    """Testet LLM Q&A Funktionalität"""
    print("\n" + "="*60)
    print("TEST 3: LLM Q&A Integration")
    print("="*60)
    
    processor = DoclingProcessor(
        use_vlm=False,
        ollama_url="https://fs.aiora.rest"
    )
    
    try:
        # Dokument konvertieren
        doc = processor.convert_document("test_document.md")
        
        # Frage stellen
        question = "Was sind die drei Hauptpunkte im Dokument?"
        print(f"Frage: {question}")
        
        answer = processor.ask_question(
            doc, 
            question,
            model="qwen3:latest"
        )
        
        if "error" in answer:
            print(f"⚠️  LLM nicht verfügbar: {answer['error']}")
            print("   Tipp: Stellen Sie sicher, dass Ollama läuft und das Modell installiert ist:")
            print("   ollama pull qwen3:latest")
        else:
            print("✅ Q&A erfolgreich")
            print(f"   Antwort: {answer.get('antwort', 'Keine Antwort')[:200]}...")
            print(f"   Konfidenz: {answer.get('konfidenz', 'unbekannt')}")
            
    except Exception as e:
        print(f"❌ Fehler bei Q&A: {e}")


def test_pdf_with_ocr():
    """Testet PDF mit OCR (wenn PDF verfügbar)"""
    print("\n" + "="*60)
    print("TEST 4: PDF mit SmolDocling VLM (falls PDF vorhanden)")
    print("="*60)
    
    # Suche nach PDF Dateien
    pdf_files = list(Path(".").glob("*.pdf"))
    
    if not pdf_files:
        print("ℹ️  Keine PDF-Datei gefunden. Überspringe Test.")
        print("   Tipp: Legen Sie eine PDF-Datei im Verzeichnis ab für vollständigen Test")
        return
    
    pdf_file = pdf_files[0]
    print(f"Teste mit: {pdf_file}")
    
    processor = DoclingProcessor(use_vlm=True, use_easyocr=False)
    
    try:
        result = processor.convert_document(str(pdf_file))
        print("✅ PDF Verarbeitung erfolgreich")
        print(f"   - Seiten: {result['metadata'].get('page_count', 0)}")
        print(f"   - Tabellen: {result['metadata'].get('table_count', 0)}")
        print(f"   - Pipeline: {result['metadata'].get('processing_pipeline')}")
        
        # Optional: Speichere Ergebnis
        output_file = f"{pdf_file.stem}_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"   - Ergebnis gespeichert: {output_file}")
        
    except Exception as e:
        print(f"❌ Fehler bei PDF: {e}")


def test_error_handling():
    """Testet Fehlerbehandlung"""
    print("\n" + "="*60)
    print("TEST 5: Fehlerbehandlung")
    print("="*60)
    
    processor = DoclingProcessor()
    
    # Test: Nicht existierende Datei
    try:
        processor.convert_document("nicht_vorhanden.pdf")
        print("❌ Fehlerbehandlung fehlgeschlagen")
    except ValueError as e:
        print(f"✅ Korrekte Fehlerbehandlung: {e}")
    
    # Test: Ungültiges Format
    try:
        # Erstelle ungültige Testdatei
        with open("test.xyz", "w") as f:
            f.write("test")
        processor.convert_document("test.xyz")
        print("❌ Format-Validierung fehlgeschlagen")
    except ValueError as e:
        print(f"✅ Format-Validierung korrekt: {str(e)[:50]}...")
        Path("test.xyz").unlink()  # Aufräumen


def run_all_tests():
    """Führt alle Tests aus"""
    print("\n" + "#"*60)
    print("# DOCLING PROCESSOR TEST SUITE")
    print("#"*60)
    
    # Testdateien erstellen
    print("\nErstelle Testdateien...")
    test_files = create_test_files()
    
    # Tests ausführen
    try:
        test_basic_conversion()
        test_markdown_export()
        test_error_handling()
        test_pdf_with_ocr()
        test_llm_qa()  # Am Ende, da es externe API braucht
        
    finally:
        # Aufräumen
        print("\n" + "="*60)
        print("Aufräumen...")
        for file in test_files:
            try:
                Path(file).unlink()
                print(f"✓ {file} gelöscht")
            except:
                pass
    
    print("\n" + "#"*60)
    print("# TESTS ABGESCHLOSSEN")
    print("#"*60)
    print("\nNächste Schritte:")
    print("1. Installieren Sie ein Ollama Modell für Q&A Tests:")
    print("   ollama pull qwen3:latest")
    print("2. Testen Sie mit einer echten PDF-Datei:")
    print("   python docling_processor.py --file ihre_datei.pdf")
    print("3. Aktivieren Sie Verbose-Mode für Details:")
    print("   python docling_processor.py --file datei.pdf -v")


def quick_test(file_path: str):
    """Schnelltest mit einer spezifischen Datei"""
    print(f"\nSchnelltest mit: {file_path}")
    print("-"*40)
    
    processor = DoclingProcessor(use_vlm=True)
    
    try:
        # Konvertieren
        result = processor.process(
            file_path=file_path,
            output_format="json"
        )
        
        print("✅ Verarbeitung erfolgreich!")
        print(f"Metadaten: {result['metadata']}")
        
        # Mit Frage testen
        result_qa = processor.process(
            file_path=file_path,
            output_format="json",
            question="Was ist der Hauptinhalt dieses Dokuments?",
            model="qwen3:latest"
        )
        
        if 'qa' in result_qa:
            print(f"Q&A Antwort: {result_qa['qa'].get('antwort', 'Keine Antwort')[:200]}...")
        
    except Exception as e:
        print(f"❌ Fehler: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Wenn Datei als Argument übergeben
        quick_test(sys.argv[1])
    else:
        # Vollständige Testsuite
        run_all_tests()