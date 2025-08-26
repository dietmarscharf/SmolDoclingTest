#!/usr/bin/env python3
"""
Vereinfachter PDF Processor für Sparkasse Kontoauszüge
Nutzt pdfplumber für PDF-Extraktion
"""

import json
import sys
from pathlib import Path
import pdfplumber
import ollama
from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_pdf_content(pdf_path: str) -> Dict[str, Any]:
    """Extrahiert Inhalt aus PDF mit pdfplumber"""
    logger.info(f"Verarbeite PDF: {pdf_path}")
    
    result = {
        "file": pdf_path,
        "pages": [],
        "tables": [],
        "text": "",
        "metadata": {}
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Metadaten
            result["metadata"] = {
                "page_count": len(pdf.pages),
                "file_name": Path(pdf_path).name
            }
            
            all_text = []
            
            # Seiten durchgehen
            for i, page in enumerate(pdf.pages):
                page_data = {
                    "page_number": i + 1,
                    "text": "",
                    "tables": []
                }
                
                # Text extrahieren
                text = page.extract_text()
                if text:
                    page_data["text"] = text
                    all_text.append(text)
                
                # Tabellen extrahieren
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        # Tabelle als strukturierte Daten
                        page_data["tables"].append(table)
                        result["tables"].append({
                            "page": i + 1,
                            "data": table
                        })
                
                result["pages"].append(page_data)
            
            # Gesamttext
            result["text"] = "\n\n".join(all_text)
            result["metadata"]["total_characters"] = len(result["text"])
            result["metadata"]["table_count"] = len(result["tables"])
            
            logger.info(f"✓ Erfolgreich extrahiert: {result['metadata']['page_count']} Seiten, {result['metadata']['table_count']} Tabellen")
            
    except Exception as e:
        logger.error(f"Fehler bei PDF-Extraktion: {e}")
        result["error"] = str(e)
    
    return result


def ask_llm_question(content: Dict[str, Any], question: str, 
                     model: str = "qwen3:latest",
                     ollama_url: str = "https://fs.aiora.rest") -> Dict[str, Any]:
    """Stellt eine Frage zum extrahierten Inhalt via Ollama"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        # Kontext vorbereiten (limitiert auf 8000 Zeichen)
        context = content["text"][:8000] if content.get("text") else "Kein Text gefunden"
        
        prompt = f"""Basierend auf diesem Dokument:

{context}

Beantworte folgende Frage:
{question}

Antworte im JSON Format:
{{
    "frage": "{question}",
    "antwort": "Deine Antwort",
    "gefundene_daten": ["relevante Daten aus dem Dokument"]
}}"""
        
        response = client.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            format="json",
            options={"temperature": 0.3}
        )
        
        if response and 'message' in response:
            try:
                return json.loads(response['message']['content'])
            except:
                return {"antwort": response['message']['content']}
    
    except Exception as e:
        logger.error(f"LLM Fehler: {e}")
        return {"error": str(e)}
    
    return {"error": "Keine Antwort erhalten"}


def process_pdf(pdf_path: str, output_path: str, question: Optional[str] = None) -> None:
    """Hauptfunktion für PDF-Verarbeitung"""
    
    # PDF-Inhalt extrahieren
    content = extract_pdf_content(pdf_path)
    
    # Optional: LLM-Frage
    if question:
        logger.info(f"Stelle Frage: {question}")
        qa_result = ask_llm_question(content, question)
        content["qa"] = qa_result
    
    # Speichern
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    
    logger.info(f"✓ Gespeichert: {output_path}")
    print(f"✓ {Path(pdf_path).name} -> {output_path}")


def main():
    # Liste der PDFs
    pdf_files = [
        "/mnt/c/Projects/Sparkasse/docs/Grunddaten/Alle Sparkassenbelege seit 2016/Konto_0021503990-Auszug_2022_0003.pdf",
        "/mnt/c/Projects/Sparkasse/docs/Grunddaten/Alle Sparkassenbelege seit 2016/Konto_0021503990-Auszug_2022_0004.pdf",
        "/mnt/c/Projects/Sparkasse/docs/Grunddaten/Alle Sparkassenbelege seit 2016/Konto_0021503990-Auszug_2022_0005.pdf",
        "/mnt/c/Projects/Sparkasse/docs/Grunddaten/Alle Sparkassenbelege seit 2016/Konto_0021503990-Auszug_2022_0006.pdf",
        "/mnt/c/Projects/Sparkasse/docs/Grunddaten/Alle Sparkassenbelege seit 2016/Konto_0021503990-Auszug_2022_0007.pdf"
    ]
    
    print("="*60)
    print("PDF BATCH PROCESSOR - Sparkasse Kontoauszüge")
    print("="*60)
    
    for pdf_path in pdf_files:
        if Path(pdf_path).exists():
            output_name = f"Konto_Auszug_2022_{Path(pdf_path).stem.split('_')[-1]}_result.json"
            process_pdf(pdf_path, output_name)
        else:
            print(f"❌ Datei nicht gefunden: {pdf_path}")
    
    print("="*60)
    print("✓ Verarbeitung abgeschlossen!")
    print("="*60)


if __name__ == "__main__":
    main()