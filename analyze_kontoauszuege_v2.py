#!/usr/bin/env python3
"""
Erweiterte Analyse der Kontoauszüge mit detaillierter Transaktionsextraktion
und Salden-Überprüfung (Version 2)
"""

import json
import sys
import re
from pathlib import Path
import ollama
from typing import Dict, Any, List
import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_german_amount(amount_str: str) -> Decimal:
    """Konvertiert deutschen Betrag zu Decimal"""
    # Entferne EUR und Leerzeichen
    amount_str = amount_str.replace('EUR', '').strip()
    # Deutsche Formatierung: Punkt als Tausender, Komma als Dezimal
    amount_str = amount_str.replace('.', '').replace(',', '.')
    # Minus für negative Beträge
    if amount_str.startswith('-'):
        return Decimal(amount_str)
    return Decimal(amount_str)


def ask_llm_detailed_analysis(json_file: str, 
                              ollama_url: str = "https://fs.aiora.rest",
                              model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Detaillierte Analyse mit Transaktionsextraktion und Saldenprüfung
    """
    logger.info(f"Detaillierte Analyse von: {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse vorbereiten
    doc_text = content.get("text", "")[:15000]  # Mehr Text für detaillierte Analyse
    
    # Erweiterte und präzise Frage
    question = """WICHTIG: Extrahiere ALLE Transaktionen VOLLSTÄNDIG und DETAILLIERT aus diesem Kontoauszug!

Analysiere diesen Kontoauszug sehr genau und beantworte:

1. ANFANGSSALDO: Exakter Betrag und Datum des Anfangssaldos
2. ENDSALDO: Exakter Betrag und Datum des Endsaldos  
3. ALLE TRANSAKTIONEN: Jede einzelne Transaktion mit:
   - Datum
   - Beschreibung/Verwendungszweck
   - Betrag (mit + für Gutschrift, - für Belastung)
   
4. SALDENPRÜFUNG: Berechne ob gilt:
   Anfangssaldo + Summe(alle Transaktionen) = Endsaldo
   Falls nicht, markiere als "FEHLER: Saldo stimmt nicht!"
   
5. WERTPAPIERE: Alle erwähnten Wertpapiere mit WKN/ISIN
6. KONTODETAILS: Kontonummer, Zeitraum, Bank

WICHTIG: Zähle die Transaktionen genau! Prüfe ob alle erfasst sind!
Bei Kontoauszügen gibt es oft einen Kontostand am Anfang (das ist KEIN Anfangssaldo sondern der Stand vom Vormonat).
Der erste Kontostand ist der Anfangssaldo, der letzte Kontostand ist der Endsaldo."""
    
    prompt = f"""Du bist ein sehr präziser Finanzprüfer. Analysiere diesen Kontoauszug EXTREM GENAU:

{doc_text}

{question}

Antworte im JSON Format:
{{
    "datei": "{Path(json_file).name}",
    "kontonummer": "exakte Kontonummer",
    "zeitraum": "von-bis Datum",
    "anfangssaldo": {{
        "betrag": Zahl (nur Zahl, kein Text),
        "datum": "TT.MM.JJJJ",
        "beschreibung": "z.B. Kontostand am..."
    }},
    "endsaldo": {{
        "betrag": Zahl (nur Zahl, kein Text),
        "datum": "TT.MM.JJJJ",
        "beschreibung": "z.B. Kontostand am..."
    }},
    "transaktionen": [
        {{
            "datum": "TT.MM.JJJJ",
            "beschreibung": "vollständige Beschreibung",
            "betrag": Zahl (negativ für Belastungen, positiv für Gutschriften),
            "typ": "Gutschrift/Belastung"
        }}
    ],
    "transaktionen_summe": Zahl (Summe aller Transaktionen),
    "berechneter_endsaldo": Zahl (Anfangssaldo + Transaktionen_summe),
    "saldo_korrekt": true/false,
    "saldo_differenz": Zahl (Endsaldo - berechneter_endsaldo),
    "anzahl_transaktionen": Zahl,
    "wertpapiere": ["Liste mit WKN/Namen"],
    "pruefung_vollstaendig": "OK" oder "FEHLER: Beschreibung"
}}

WICHTIG: Erfasse WIRKLICH ALLE Transaktionen zwischen Anfangs- und Endsaldo!"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende detaillierte Anfrage an Ollama ({model})...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein extrem genauer Finanzprüfer. Erfasse JEDE einzelne Transaktion und prüfe die Salden mathematisch exakt. Gib Beträge IMMER als reine Zahlen ohne Text aus."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={
                "temperature": 0.05,  # Noch niedriger für maximale Genauigkeit
                "top_p": 0.95,
                "num_predict": 4096  # Mehr Token für vollständige Antwort
            }
        )
        
        if response and 'message' in response:
            try:
                result = json.loads(response['message']['content'])
                
                # Nachträgliche Validierung in Python
                try:
                    anfang = Decimal(str(result['anfangssaldo']['betrag']))
                    ende = Decimal(str(result['endsaldo']['betrag']))
                    summe = Decimal(str(result.get('transaktionen_summe', 0)))
                    berechnet = anfang + summe
                    
                    # Korrigiere die Werte
                    result['python_validierung'] = {
                        'anfangssaldo': float(anfang),
                        'transaktionen_summe': float(summe),
                        'berechneter_endsaldo': float(berechnet),
                        'tatsaechlicher_endsaldo': float(ende),
                        'differenz': float(ende - berechnet),
                        'validierung_ok': abs(ende - berechnet) < Decimal('0.01')
                    }
                except Exception as e:
                    result['python_validierung'] = {'fehler': str(e)}
                
                logger.info("✓ Detaillierte Analyse erfolgreich")
                return result
                
            except json.JSONDecodeError:
                logger.warning("JSON Parsing fehlgeschlagen")
                return {
                    "datei": Path(json_file).name,
                    "fehler": "JSON Parsing Error",
                    "rohantwort": response['message']['content'][:500]
                }
    
    except Exception as e:
        logger.error(f"Fehler bei LLM Anfrage: {e}")
        return {
            "datei": Path(json_file).name,
            "fehler": str(e)
        }


def analyze_all_kontoauszuege_v2():
    """
    Version 2: Detaillierte Analyse aller Kontoauszüge mit Transaktionsvalidierung
    """
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V2 - DETAILLIERTE TRANSAKTIONSEXTRAKTION")
    print("="*80)
    
    # Finde alle Kontoauszug JSON Dateien
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} Kontoauszüge für detaillierte Analyse\n")
    
    # Alle Analysen sammeln
    all_analyses = []
    
    for json_file in json_files:
        print(f"\n{'='*60}")
        print(f"Analysiere: {json_file.name}")
        print(f"{'='*60}")
        
        analysis = ask_llm_detailed_analysis(str(json_file))
        all_analyses.append(analysis)
        
        # Detaillierte Ausgabe
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            print(f"\n📊 ERGEBNIS für {analysis.get('datei', json_file.name)}")
            print(f"   Kontonummer: {analysis.get('kontonummer', 'N/A')}")
            print(f"   Zeitraum: {analysis.get('zeitraum', 'N/A')}")
            
            # Salden
            anfang = analysis.get('anfangssaldo', {})
            ende = analysis.get('endsaldo', {})
            print(f"\n💰 SALDEN:")
            print(f"   Anfangssaldo: {anfang.get('betrag', 'N/A')} EUR ({anfang.get('datum', 'N/A')})")
            print(f"   Endsaldo:     {ende.get('betrag', 'N/A')} EUR ({ende.get('datum', 'N/A')})")
            
            # Transaktionen
            trans = analysis.get('transaktionen', [])
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} Stück")
            if trans and len(trans) <= 15:  # Zeige nur wenn nicht zu viele
                for t in trans[:5]:  # Erste 5 anzeigen
                    betrag = t.get('betrag', 0)
                    sign = "+" if betrag > 0 else ""
                    print(f"   {t.get('datum', 'N/A')}: {sign}{betrag} EUR - {t.get('beschreibung', 'N/A')[:50]}...")
                if len(trans) > 5:
                    print(f"   ... und {len(trans)-5} weitere Transaktionen")
            
            # Saldenprüfung
            print(f"\n✅ SALDENPRÜFUNG:")
            print(f"   Summe Transaktionen: {analysis.get('transaktionen_summe', 'N/A')} EUR")
            print(f"   Berechneter Endsaldo: {analysis.get('berechneter_endsaldo', 'N/A')} EUR")
            print(f"   Differenz: {analysis.get('saldo_differenz', 'N/A')} EUR")
            
            if analysis.get('saldo_korrekt'):
                print(f"   ✅ SALDO STIMMT!")
            else:
                print(f"   ⚠️  WARNUNG: Saldo weicht ab!")
            
            # Python-Validierung
            if 'python_validierung' in analysis:
                val = analysis['python_validierung']
                if val.get('validierung_ok'):
                    print(f"   ✅ Python-Validierung: OK")
                else:
                    print(f"   ⚠️  Python-Validierung: Differenz {val.get('differenz', 'N/A')} EUR")
            
            # Wertpapiere
            if analysis.get('wertpapiere'):
                print(f"\n📈 WERTPAPIERE:")
                for wp in analysis['wertpapiere']:
                    print(f"   • {wp}")
    
    # Gesamtanalyse speichern
    output_file = "kontoauszuege_analyse_komplett_v2.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "2.0",
            "beschreibung": "Detaillierte Analyse mit vollständiger Transaktionsextraktion und Saldenprüfung",
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "timestamp": str(Path(json_files[0]).stat().st_mtime) if json_files else None
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print(f"✅ ANALYSE V2 ABGESCHLOSSEN!")
    print(f"📊 Detaillierte Analyse gespeichert in: {output_file}")
    print("="*80)
    
    # Zusammenfassung der Saldenprüfung
    print("\n📋 ZUSAMMENFASSUNG SALDENPRÜFUNG:")
    korrekt = 0
    fehlerhaft = 0
    for analyse in all_analyses:
        if 'fehler' not in analyse:
            if analyse.get('saldo_korrekt') or (analyse.get('python_validierung', {}).get('validierung_ok')):
                korrekt += 1
                print(f"   ✅ {analyse['datei']}: Saldo stimmt")
            else:
                fehlerhaft += 1
                diff = analyse.get('saldo_differenz', analyse.get('python_validierung', {}).get('differenz', 'N/A'))
                print(f"   ⚠️  {analyse['datei']}: Differenz {diff} EUR")
    
    print(f"\n   Gesamt: {korrekt} korrekt, {fehlerhaft} mit Abweichungen")


if __name__ == "__main__":
    # Prüfe ob Ollama verfügbar ist
    try:
        client = ollama.Client(host="https://fs.aiora.rest")
        print("Teste Ollama Verbindung...")
        client.list()
        print("✓ Ollama verfügbar\n")
    except Exception as e:
        print(f"⚠️  Ollama nicht erreichbar: {e}")
        print("Tipp: Stelle sicher, dass Ollama läuft und ein Modell installiert ist:")
        print("  OLLAMA_HOST=https://fs.aiora.rest ollama pull qwen3:8b")
        sys.exit(1)
    
    # Version 2 Analyse ausführen
    analyze_all_kontoauszuege_v2()