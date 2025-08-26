#!/usr/bin/env python3
"""
Analysiert die bereits extrahierten Kontoauszüge mit Q&A via Ollama
"""

import json
import sys
from pathlib import Path
import ollama
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def ask_llm_about_kontoauszug(json_file: str, 
                              ollama_url: str = "https://fs.aiora.rest",
                              model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Analysiert einen Kontoauszug mit spezifischen Fragen
    """
    logger.info(f"Analysiere: {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse vorbereiten
    doc_text = content.get("text", "")[:10000]  # Limitiert auf 10k Zeichen
    
    # Detaillierte Frage
    question = """Analysiere diesen Kontoauszug und beantworte folgende Punkte:
1. Was ist der Anfangssaldo/Startsaldo?
2. Was ist der Endsaldo?
3. Wie viele Transaktionen gibt es insgesamt?
4. Welche Arten von Transaktionen gibt es (z.B. Überweisungen, Wertpapiere, Gebühren)?
5. Welche Anlagen oder Wertpapiere werden erwähnt?
6. Gibt es besondere Transaktionen (z.B. hohe Beträge)?"""
    
    prompt = f"""Du bist ein Finanzanalyst. Analysiere diesen Kontoauszug:

{doc_text}

{question}

Antworte im JSON Format:
{{
    "datei": "{Path(json_file).name}",
    "anfangssaldo": "Betrag und Datum",
    "endsaldo": "Betrag und Datum",
    "anzahl_transaktionen": Zahl,
    "transaktionsarten": ["Liste der Arten"],
    "wertpapiere": ["Liste der gefundenen Wertpapiere/Anlagen"],
    "besondere_transaktionen": ["Liste großer oder wichtiger Transaktionen"],
    "zeitraum": "von-bis",
    "kontonummer": "gefundene Kontonummer"
}}"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende Anfrage an Ollama ({model})...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein präziser Finanzanalyst. Extrahiere exakte Zahlen und Daten aus Kontoauszügen."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={
                "temperature": 0.1,  # Sehr niedrig für faktische Genauigkeit
                "top_p": 0.9
            }
        )
        
        if response and 'message' in response:
            try:
                result = json.loads(response['message']['content'])
                logger.info("✓ Analyse erfolgreich")
                return result
            except json.JSONDecodeError:
                logger.warning("JSON Parsing fehlgeschlagen")
                return {
                    "datei": Path(json_file).name,
                    "fehler": "JSON Parsing Error",
                    "rohantwort": response['message']['content']
                }
    
    except Exception as e:
        logger.error(f"Fehler bei LLM Anfrage: {e}")
        return {
            "datei": Path(json_file).name,
            "fehler": str(e)
        }


def analyze_all_kontoauszuege():
    """
    Analysiert alle vorhandenen Kontoauszug JSON Dateien
    """
    print("\n" + "="*70)
    print("KONTOAUSZUG ANALYSE MIT Q&A")
    print("="*70)
    
    # Finde alle Kontoauszug JSON Dateien
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} Kontoauszüge\n")
    
    # Alle Analysen sammeln
    all_analyses = []
    
    for json_file in json_files:
        print(f"Analysiere {json_file.name}...")
        analysis = ask_llm_about_kontoauszug(str(json_file))
        all_analyses.append(analysis)
        
        # Ergebnis anzeigen
        print("-" * 50)
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            print(f"✓ {analysis.get('datei', json_file.name)}")
            print(f"  Anfangssaldo: {analysis.get('anfangssaldo', 'N/A')}")
            print(f"  Endsaldo: {analysis.get('endsaldo', 'N/A')}")
            print(f"  Transaktionen: {analysis.get('anzahl_transaktionen', 'N/A')}")
            print(f"  Wertpapiere: {', '.join(analysis.get('wertpapiere', []))}")
        print()
    
    # Gesamtanalyse speichern
    output_file = "kontoauszuege_analyse_komplett.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "timestamp": str(Path(json_files[0]).stat().st_mtime) if json_files else None
        }, f, indent=2, ensure_ascii=False)
    
    print("="*70)
    print(f"✅ Analyse abgeschlossen!")
    print(f"📊 Gesamtanalyse gespeichert in: {output_file}")
    print("="*70)


def create_summary_report():
    """
    Erstellt einen zusammenfassenden Bericht
    """
    if not Path("kontoauszuege_analyse_komplett.json").exists():
        print("Führe zuerst die Analyse aus...")
        analyze_all_kontoauszuege()
    
    with open("kontoauszuege_analyse_komplett.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("\n" + "="*70)
    print("ZUSAMMENFASSENDER BERICHT")
    print("="*70)
    
    for analyse in data['analysen']:
        if 'fehler' not in analyse:
            print(f"\n📄 {analyse.get('datei', 'Unbekannt')}")
            print(f"   Kontonummer: {analyse.get('kontonummer', 'N/A')}")
            print(f"   Zeitraum: {analyse.get('zeitraum', 'N/A')}")
            print(f"   Saldo: {analyse.get('anfangssaldo', 'N/A')} → {analyse.get('endsaldo', 'N/A')}")
            print(f"   Anzahl Transaktionen: {analyse.get('anzahl_transaktionen', 'N/A')}")
            
            if analyse.get('transaktionsarten'):
                print(f"   Transaktionsarten:")
                for art in analyse['transaktionsarten']:
                    print(f"     • {art}")
            
            if analyse.get('wertpapiere'):
                print(f"   Wertpapiere/Anlagen:")
                for wp in analyse['wertpapiere']:
                    print(f"     • {wp}")
            
            if analyse.get('besondere_transaktionen'):
                print(f"   Besondere Transaktionen:")
                for trans in analyse['besondere_transaktionen'][:3]:  # Max 3 anzeigen
                    print(f"     • {trans}")


if __name__ == "__main__":
    # Prüfe ob Ollama verfügbar ist
    try:
        client = ollama.Client(host="https://fs.aiora.rest")
        # Teste Verbindung
        print("Teste Ollama Verbindung...")
        client.list()
        print("✓ Ollama verfügbar\n")
    except Exception as e:
        print(f"⚠️  Ollama nicht erreichbar: {e}")
        print("Tipp: Stelle sicher, dass Ollama läuft und ein Modell installiert ist:")
        print("  OLLAMA_HOST=https://fs.aiora.rest ollama pull qwen3:8b")
        sys.exit(1)
    
    # Hauptanalyse ausführen
    analyze_all_kontoauszuege()
    
    # Zusammenfassung anzeigen
    create_summary_report()